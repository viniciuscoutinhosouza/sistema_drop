import io
import json
import time as time_module
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.cmig import CMIGProduct
from models.integration import MarketplaceAccount
from models.order import Order, OrderItem
from models.product import (
    CatalogProduct,
    CatalogProductImage,
    DropshipperProduct,
    DropshipperProductImage,
    ProductListing,
)
from models.user import User
from models.webhook import WebhookEvent
from services import ml_service as _ml
from services.datetime_br import BR_TZ
from services.file_naming import (
    TIPO_DACE,
    TIPO_DANFE,
    TIPO_ETIQUETA,
    TIPO_NFE,
    order_download_filename,
    slugify_name,
)
from services.financial_service import debit_balance
from services.label_meta import build_orders_label_meta
from services.label_service import ML_CONF_HEADER as _ML_CONF_HEADER
from services.label_service import (
    render_manual_order_label,
    render_manual_order_label_zpl,
    render_shipping_labels_zpl,
)
from services.shipping_mode import classify_logistic_type, label_for_mode

settings = get_settings()
router = APIRouter()

_NFE_CALLBACK = "https%3A%2F%2Fwww.mercadolivre.com.br%2Fvendas%2Fomni%2Flista"


def _ml_nfe_url(order: Order) -> str | None:
    """Return the ML DANFE viewer URL when the order has a 44-digit access key.

    The viewer URL requires the Faturador invoice_id, NOT the platform_order_id.
    nfe_url in the DB stores either:
      - a plain digit string (invoice_id directly, e.g. "5986391161") — preferred
      - a danfe_location path ending in /danfe/{invoice_id}             — legacy
    """
    key = order.nfe_key
    if order.platform == "mercadolivre" and key and str(key).isdigit() and len(str(key)) == 44:
        stored = str(order.nfe_url or "")
        if stored.isdigit():
            invoice_id = stored
        elif "/danfe/" in stored:
            invoice_id = stored.rstrip("/").split("/danfe/")[-1]
        else:
            invoice_id = None
        if invoice_id:
            return (
                f"https://myaccount.mercadolivre.com.br/invoices/api/invoices"
                f"/{invoice_id}/danfe/{key}"
                f"?source=ml&callbackWording=Vendas&callbackUrl={_NFE_CALLBACK}"
            )
    # Fallback: use whatever was stored (older orders or non-ML)
    return order.nfe_url


def _ac_visible_filter(current_user):
    """Predicado SQL de visibilidade de pedidos para usuarios AC.

    AC ve um pedido quando:
      - eh o dropshipper original (dono de conta); OU
      - eh administrador (proprietario ou colaborador) da CMIG do pedido.
    """
    from models.cmig import CMIGAdministrator

    ac_cmigs_subq = select(CMIGAdministrator.cmig_id).where(
        CMIGAdministrator.user_id == current_user.id
    )
    return or_(
        Order.dropshipper_id == current_user.id,
        Order.cmig_id.in_(ac_cmigs_subq),
    )


def _resolve_item_cost_runtime(
    item: OrderItem,
    order: Order,
    dp_map: dict,
    listing_map: dict,
    sku_listing_map: dict,
    ml_item_listing_map: dict,
    catalog_cost_map: dict,
    cmig_cost_map: dict,
    cmig_product_cost_map: dict,
) -> float | None:
    """Resolve custo unitário em runtime a partir dos maps pré-carregados.

    Cascata (espelha order_item_resolver.resolve_order_item_link):
      1) Listing (ml_item_id/sku/dp) com cmig_product_id → cmig_product_cost_map
      2) Listing com catalog_product_id (sem cmig) → catalog_cost_map
      3) catalog_product_id direto no item (ou via dp) → cmig_cost_map (preferido), fallback catalog
    """
    cmig_id = order.cmig_id
    account_id = order.account_id

    # 1) Achar listing
    listing = None
    if item.dropshipper_product_id:
        listing = listing_map.get(item.dropshipper_product_id)
    if not listing and account_id and getattr(item, "ml_item_id", None):
        listing = ml_item_listing_map.get((account_id, item.ml_item_id))
    if not listing and account_id and item.sku:
        listing = sku_listing_map.get((account_id, item.sku))

    if listing:
        if listing.cmig_product_id:
            c = cmig_product_cost_map.get(listing.cmig_product_id)
            if c is not None:
                return float(c)
        if listing.catalog_product_id:
            c = catalog_cost_map.get(listing.catalog_product_id)
            if c is not None:
                return float(c)

    # 3) catalog_product_id direto no item ou via dropshipper
    catalog_id = item.catalog_product_id
    if not catalog_id:
        dp = dp_map.get(item.dropshipper_product_id) if item.dropshipper_product_id else None
        catalog_id = dp.catalog_product_id if dp else None
    if not catalog_id:
        return None
    if cmig_id is not None:
        c = cmig_cost_map.get((cmig_id, catalog_id))
        if c is not None:
            return float(c)
    c = catalog_cost_map.get(catalog_id)
    return float(c) if c is not None else None


def _issuer_type_from_cmig(cmig_info: dict | None) -> str:
    """'cnpj' (emite NF-e), 'cpf' (precisa de DC-e) ou 'unknown'.

    CNPJ tem precedência: se a CMIG tem ambos, opera como PJ (emite NF-e).
    """
    if not cmig_info:
        return "unknown"
    if (cmig_info.get("cnpj") or "").strip():
        return "cnpj"
    if (cmig_info.get("cpf") or "").strip():
        return "cpf"
    return "unknown"


async def _order_issuer_type(db: AsyncSession, order: Order) -> str:
    """Carrega a CMIG do pedido e retorna o tipo fiscal do emissor (cnpj/cpf/unknown)."""
    from models.cmig import CMIG

    if not order.cmig_id:
        return "unknown"
    cmig = (
        await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
    ).scalar_one_or_none()
    if not cmig:
        return "unknown"
    if (cmig.cnpj or "").strip():
        return "cnpj"
    if (cmig.cpf or "").strip():
        return "cpf"
    return "unknown"


# Mensagem padrão quando o ML aguarda a Declaração de Conteúdo (conta CPF, sem NF-e).
_DCE_PENDING_MSG = (
    "Conta pessoa física (CPF) — o Mercado Livre aguarda a Declaração de Conteúdo "
    "Eletrônica (DC-e), não NF-e. Emita a DC-e no painel do Mercado Livre (ou pelo app "
    "DC-e do gov.br) para liberar a etiqueta. Assim que a DC-e for emitida, clique "
    "novamente para imprimir a etiqueta."
)
_UNKNOWN_ISSUER_MSG = (
    "Documento fiscal pendente, mas a CMIG não tem CNPJ nem CPF cadastrado — o sistema "
    "não sabe se deve emitir NF-e (PJ) ou DC-e (PF). Cadastre o CNPJ ou CPF na CMIG."
)


def _ml_dce_emitter_url(order: Order) -> str:
    """Link do emissor de DC-e do PRÓPRIO Mercado Livre (o ML emite a DC-e e libera a etiqueta).

    Decisão 2026-07-09: substitui a emissão própria via SEFAZ (ADR-0017, superseded) — evita
    SEFAZ/ICP-Brasil/certificado. Reconstruído por venda a partir do `platform_order_id`.
    """
    from urllib.parse import quote

    cb = quote("https://www.mercadolivre.com.br/vendas/omni/lista", safe="")
    return (
        "https://www.mercadolivre.com.br/emissor/omni/emitir/dce/sale/SALE_ML_DCE/"
        f"{order.platform_order_id or ''}?source=ml&callbackWording=Vendas&callbackUrl={cb}"
    )


def _serialize_order_list(
    o: Order,
    images_by_catalog: dict,
    dp_map: dict,
    listing_map: dict,
    dp_images: dict,
    sku_listing_map: dict,
    ml_item_listing_map: dict,
    cmig_map: dict | None = None,
    catalog_cost_map: dict | None = None,
    cmig_cost_map: dict | None = None,
    cmig_product_cost_map: dict | None = None,
    local_stock_map: dict | None = None,
    full_per_account_map: dict | None = None,
) -> dict:
    catalog_cost_map = catalog_cost_map or {}
    cmig_cost_map = cmig_cost_map or {}
    cmig_product_cost_map = cmig_product_cost_map or {}
    local_stock_map = local_stock_map or {}
    full_per_account_map = full_per_account_map or {}
    items = []
    for i in o.items:
        dp = dp_map.get(i.dropshipper_product_id) if i.dropshipper_product_id else None
        listing = listing_map.get(i.dropshipper_product_id) if i.dropshipper_product_id else None

        # SKU-based fallback when no DropshipperProduct is linked
        if not listing and i.sku:
            listing = sku_listing_map.get((o.account_id, i.sku))

        # ML item ID fallback — covers items with empty seller_sku
        if not listing and getattr(i, "ml_item_id", None):
            listing = ml_item_listing_map.get((o.account_id, i.ml_item_id))

        # Thumbnail priority: stored thumbnail_url > listing thumbnail > dp image > catalog image
        thumbnail = (
            (i.thumbnail_url or None)
            or (listing.thumbnail if listing and listing.thumbnail else None)
            or dp_images.get(i.dropshipper_product_id)
            or (images_by_catalog.get(i.catalog_product_id) if i.catalog_product_id else None)
            or (
                images_by_catalog.get(listing.catalog_product_id)
                if listing and listing.catalog_product_id
                else None
            )
        )

        # Listing type: gold_special / gold_pro = Premium, rest = Clássico
        listing_type = None
        if listing and listing.listing_type:
            listing_type = listing.listing_type
        elif dp and dp.ml_listing_type:
            listing_type = dp.ml_listing_type

        # FULL: shipping_method (logistic_type) is authoritative for new orders;
        # listing.is_full is used as fallback for old orders where shipping_method was not stored
        is_full = "fulfillment" in (o.shipping_method or "") or (
            bool(listing.is_full) if listing is not None and not o.shipping_method else False
        )

        # Estoque disponível LIVE para o card "disponíveis após esta venda".
        # FULL → FullStock.qty - reserved_qty da conta ML (Fase 1 SSOT).
        # Local → max(0, stock_quantity - reserved_quantity) do produto vinculado.
        # Quando reserva já foi aplicada (status downloaded/paid), o número já reflete
        # o pós-venda; quando não há reserva ainda, este é o estado atual.
        available_local = None
        available_full = None
        if listing is not None:
            ptype = "cmig" if listing.cmig_product_id else (
                "pg" if listing.catalog_product_id else None
            )
            pid = listing.cmig_product_id or listing.catalog_product_id
            if ptype and pid:
                ps, rs = local_stock_map.get((ptype, pid), (None, None))
                if ps is not None:
                    available_local = max(0, ps - (rs or 0))
                if o.account_id:
                    fd = full_per_account_map.get((ptype, pid), {}).get(o.account_id)
                    if fd is not None:
                        available_full = max(
                            0, int(fd.get("qty", 0) or 0) - int(fd.get("reserved_qty", 0) or 0)
                        )

        items.append(
            {
                "id": i.id,
                "sku": i.sku,
                "title": i.title,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price) if i.unit_price else None,
                "image_url": thumbnail,
                "ml_item_id": (dp.ml_item_id if dp else None) or getattr(i, "ml_item_id", None),
                "platform_item_id": listing.platform_item_id if listing else None,
                "permalink": listing.permalink if listing else None,
                "listing_type": listing_type,
                "is_full": is_full,
                "catalog_listing": bool(listing.catalog_listing) if listing else False,
                "free_shipping": bool(listing.free_shipping) if listing else False,
                # available_quantity LIVE: FULL usa FullStock; local usa stock - reserved.
                # Fallback no snapshot do listing apenas se não houver vínculo de produto.
                "available_quantity": (
                    available_full if is_full and available_full is not None
                    else (
                        available_local if available_local is not None
                        else (listing.available_quantity if listing else None)
                    )
                ),
                "available_local": available_local,
                "available_full": available_full,
            }
        )

    shipping_address = {}
    if o.shipping_address:
        try:
            shipping_address = json.loads(o.shipping_address)
        except (ValueError, TypeError):
            pass

    # Financial breakdown: sale - seller_shipping - ml_fee - product_cost = gross_profit
    sale = float(o.sale_amount) if o.sale_amount else None
    buyer_shipping = float(o.buyer_shipping_paid) if o.buyer_shipping_paid is not None else None
    seller_shipping = float(o.seller_shipping_cost) if o.seller_shipping_cost is not None else None
    ml_fee = float(o.platform_fee) if o.platform_fee is not None else None
    ml_fee_pct = (
        float(o.ml_fee_pct)
        if o.ml_fee_pct is not None
        else (round(ml_fee / sale * 100, 2) if (sale and sale > 0 and ml_fee is not None) else None)
    )
    product_cost = float(o.product_cost) if o.product_cost else None
    # Fallback retroativo: pedidos antigos com product_cost vazio (unit_cost não populado
    # no webhook) — recomputa a partir do CMIG/PG vinculado em tempo de resposta.
    if product_cost is None:
        runtime_total = 0.0
        any_resolved = False
        for it in o.items:
            unit = (
                float(it.unit_cost)
                if it.unit_cost is not None
                else _resolve_item_cost_runtime(
                    it, o, dp_map, listing_map, sku_listing_map, ml_item_listing_map,
                    catalog_cost_map, cmig_cost_map, cmig_product_cost_map,
                )
            )
            if unit is not None:
                any_resolved = True
                runtime_total += unit * (it.quantity or 0)
        if any_resolved:
            product_cost = round(runtime_total, 2)

    # Gross profit (only when we have sale + at least the fee component)
    gross_profit = None
    gross_profit_pct = None
    if sale is not None and ml_fee is not None:
        gross_profit = round(
            sale - (seller_shipping or 0) - ml_fee - (product_cost or 0),
            2,
        )
        if sale > 0:
            gross_profit_pct = round(gross_profit / sale * 100, 2)

    # Legacy net for backward compat (sale - shipping - fee, no product_cost)
    legacy_shipping = float(o.shipping_cost) if o.shipping_cost else None
    net = None
    net_pct = None
    if sale is not None and legacy_shipping is not None and ml_fee is not None:
        net = round(sale - legacy_shipping - ml_fee, 2)
        net_pct = round(net / sale * 100, 2) if sale > 0 else None

    cmig_info = (cmig_map or {}).get(o.cmig_id) if o.cmig_id else None
    fiscal_issuer_type = _issuer_type_from_cmig(cmig_info)

    return {
        "id": o.id,
        "cmig_id": o.cmig_id,
        "cmig": cmig_info,
        # Tipo fiscal do emissor: 'cnpj' emite NF-e; 'cpf' precisa de DC-e (Declaração
        # de Conteúdo Eletrônica); 'unknown' quando a CMIG não tem CNPJ nem CPF.
        "fiscal_issuer_type": fiscal_issuer_type,
        "platform": o.platform,
        "platform_order_id": o.platform_order_id,
        "platform_order_ref": o.platform_order_ref,
        "platform_status": o.platform_status,
        "status": o.status,
        "payment_status": o.payment_status,
        "buyer_name": o.buyer_name,
        "buyer_document": o.buyer_document,
        "shipping_address": shipping_address,
        "shipping_method": o.shipping_method,
        "shipping_mode": o.shipping_mode
        or classify_logistic_type(o.shipping_method, o.shipment_id),
        "shipping_mode_label": label_for_mode(
            o.shipping_mode or classify_logistic_type(o.shipping_method, o.shipment_id)
        ),
        "shipment_status": o.shipment_status,
        "tracking_code": o.tracking_code,
        "tracking_url": o.tracking_url,
        "label_url": o.label_url,
        "label_cached_at": o.label_cached_at.isoformat() if o.label_cached_at else None,
        "nfe_url": _ml_nfe_url(o),
        "nfe_key": o.nfe_key,
        "nfe_status": o.nfe_status,
        "dce_status": o.dce_status,
        "shipment_id": o.shipment_id,
        # eShip (WMS) — estado do envio completo (Ordem + NF-e + Etiqueta)
        "eship_order_id": o.eship_order_id,
        "eship_nfe_attached": bool(o.eship_nfe_attached),
        "eship_label_attached": bool(o.eship_label_attached),
        "eship_dispatch_status": o.eship_dispatch_status,
        # A UI precisa do MOTIVO do erro (antes era invisível) e de um sinal confiável de
        # "já enviada" — o eShip pode aceitar a ordem sem devolver id extraível.
        "eship_dispatch_error": o.eship_dispatch_error,
        "eship_enviada": bool(o.eship_order_id)
        or (o.eship_dispatch_status in ("sent", "partial")),
        "estimated_delivery_date": o.estimated_delivery_date.isoformat()
        if o.estimated_delivery_date
        else None,
        "estimated_handling_limit": o.estimated_handling_limit.isoformat()
        if o.estimated_handling_limit
        else None,
        "estimated_delivery_final": o.estimated_delivery_final.isoformat()
        if o.estimated_delivery_final
        else None,
        "order_tags": o.order_tags,
        "sale_amount": sale,
        "buyer_shipping_paid": buyer_shipping,
        "seller_shipping_cost": seller_shipping,
        "ml_fee": ml_fee,
        "ml_fee_pct": ml_fee_pct,
        "product_cost": product_cost,
        "gross_profit": gross_profit,
        "gross_profit_pct": gross_profit_pct,
        # Legacy fields kept for backward compat
        "platform_fee": ml_fee,
        "shipping_cost": legacy_shipping,
        "total_debit": float(o.total_debit) if o.total_debit else None,
        "net_revenue": net,
        "net_pct": net_pct,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "items": items,
    }


@router.get("/cmigs/available")
async def list_available_cmigs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return CMIGs the current user has access to, for the orders filter dropdown.

    - admin: all CMIGs
    - ugo: CMIGs in their warehouse
    - ac: CMIGs they administer
    """
    from models.cmig import CMIG, CMIGAdministrator

    if current_user.role == "admin":
        result = await db.execute(
            select(CMIG).where(CMIG.is_active == True).order_by(CMIG.trade_name)
        )
    elif current_user.role == "ugo":
        if not current_user.warehouse_id:
            return {"items": []}
        result = await db.execute(
            select(CMIG)
            .where(CMIG.warehouse_id == current_user.warehouse_id, CMIG.is_active == True)
            .order_by(CMIG.trade_name)
        )
    elif current_user.role == "ac":
        subq = select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == current_user.id)
        result = await db.execute(
            select(CMIG).where(CMIG.id.in_(subq), CMIG.is_active == True).order_by(CMIG.trade_name)
        )
    else:
        return {"items": []}

    items = [
        {
            "id": c.id,
            "trade_name": c.trade_name,
            "company_name": c.company_name,
            "cnpj": c.cnpj,
        }
        for c in result.scalars().all()
    ]
    return {"items": items}


@router.get("")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    platform: str = None,
    payment_status: str = None,
    shipment_status: str = None,
    shipping_mode: str = None,
    tag: str = None,
    search: str = None,
    date_from: str = None,
    date_to: str = None,
    cmig_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.cmig import CMIG, CMIGAdministrator

    query = select(Order).where(Order.is_hidden == False)

    # Role-based access control on CMIG
    if current_user.role == "ac":
        # AC só vê pedidos próprios
        query = query.where(_ac_visible_filter(current_user))
    elif current_user.role == "ugo":
        # UGO só vê pedidos das CMIGs do seu galpão
        ugo_cmigs_subq = select(CMIG.id).where(CMIG.warehouse_id == current_user.warehouse_id)
        query = query.where(Order.cmig_id.in_(ugo_cmigs_subq))
    # admin / go: acesso total

    # Filtro CMIG explícito (se informado, valida acesso)
    if cmig_id:
        if current_user.role == "ac":
            access_check = await db.execute(
                select(CMIGAdministrator).where(
                    CMIGAdministrator.user_id == current_user.id,
                    CMIGAdministrator.cmig_id == cmig_id,
                )
            )
            if not access_check.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")
        elif current_user.role == "ugo":
            cmig_check = await db.execute(
                select(CMIG).where(
                    CMIG.id == cmig_id, CMIG.warehouse_id == current_user.warehouse_id
                )
            )
            if not cmig_check.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")
        query = query.where(Order.cmig_id == cmig_id)

    if status:
        query = query.where(Order.status == status)
    if platform:
        query = query.where(Order.platform == platform)
    if payment_status:
        query = query.where(Order.payment_status == payment_status)
    if shipment_status:
        query = query.where(Order.shipment_status == shipment_status)
    if shipping_mode:
        query = query.where(Order.shipping_mode == shipping_mode)
    if tag:
        query = query.where(Order.order_tags.ilike(f"%{tag}%"))
    if search:
        # Cliente, número da venda (platform_order_id), SKU e nome do produto.
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Order.buyer_name.ilike(term),
                Order.platform_order_id.ilike(term),
                Order.items.any(
                    or_(OrderItem.sku.ilike(term), OrderItem.title.ilike(term))
                ),
            )
        )

    # Período por data de criação — o dia é do calendário BR (ADR-0013), convertido para
    # UTC (created_at é UTC-aware). Range half-open [início do dia, início do dia seguinte).
    def _parse_day(value: str, field: str) -> datetime:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            raise HTTPException(status_code=422, detail=f"{field} inválida (use AAAA-MM-DD)")

    if date_from:
        d = _parse_day(date_from, "Data inicial")
        from_utc = datetime(d.year, d.month, d.day, tzinfo=BR_TZ).astimezone(UTC)
        query = query.where(Order.created_at >= from_utc)
    if date_to:
        d = _parse_day(date_to, "Data final")
        to_excl = (datetime(d.year, d.month, d.day, tzinfo=BR_TZ) + timedelta(days=1)).astimezone(UTC)
        query = query.where(Order.created_at < to_excl)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()

    query = (
        query.options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    orders = result.scalars().all()

    # Collect IDs for batch loading
    catalog_ids = {i.catalog_product_id for o in orders for i in o.items if i.catalog_product_id}
    dp_ids = {i.dropshipper_product_id for o in orders for i in o.items if i.dropshipper_product_id}

    # Batch: first catalog image per product
    images_by_catalog: dict = {}
    if catalog_ids:
        img_result = await db.execute(
            select(CatalogProductImage)
            .where(CatalogProductImage.product_id.in_(catalog_ids))
            .order_by(CatalogProductImage.sort_order)
        )
        for img in img_result.scalars().all():
            if img.product_id not in images_by_catalog:
                images_by_catalog[img.product_id] = img.url

    # Batch: DropshipperProduct
    dp_map: dict = {}
    if dp_ids:
        dp_result = await db.execute(
            select(DropshipperProduct).where(DropshipperProduct.id.in_(dp_ids))
        )
        for dp in dp_result.scalars().all():
            dp_map[dp.id] = dp

    # Batch: first DropshipperProductImage per product
    dp_images: dict = {}
    if dp_ids:
        dpi_result = await db.execute(
            select(DropshipperProductImage)
            .where(DropshipperProductImage.dropshipper_product_id.in_(dp_ids))
            .order_by(DropshipperProductImage.sort_order)
        )
        for img in dpi_result.scalars().all():
            if img.dropshipper_product_id not in dp_images:
                dp_images[img.dropshipper_product_id] = img.url

    # Batch: first ProductListing per dropshipper_product_id
    listing_map: dict = {}
    if dp_ids:
        listing_result = await db.execute(
            select(ProductListing)
            .where(ProductListing.product_id.in_(dp_ids))
            .order_by(ProductListing.id)
        )
        for lst in listing_result.scalars().all():
            if lst.product_id not in listing_map:
                listing_map[lst.product_id] = lst

    # Batch: SKU-based ProductListing fallback for items with no linked DropshipperProduct
    orphan_skus = {i.sku for o in orders for i in o.items if i.sku and not i.dropshipper_product_id}
    account_ids_set = {o.account_id for o in orders if o.account_id}
    sku_listing_map: dict = {}  # (account_id, sku) -> ProductListing
    if orphan_skus and account_ids_set:
        sku_lst_result = await db.execute(
            select(ProductListing)
            .where(
                ProductListing.sku.in_(orphan_skus),
                ProductListing.account_id.in_(account_ids_set),
            )
            .order_by(ProductListing.id)
        )
        for lst in sku_lst_result.scalars().all():
            key = (lst.account_id, lst.sku)
            if key not in sku_listing_map:
                sku_listing_map[key] = lst

    # Batch: ML item ID fallback — items with no DP link and no SKU (empty seller_sku from ML)
    orphan_ml_ids = {
        i.ml_item_id
        for o in orders
        for i in o.items
        if getattr(i, "ml_item_id", None) and not i.dropshipper_product_id
    }
    ml_item_listing_map: dict = {}  # (account_id, ml_item_id) -> ProductListing
    if orphan_ml_ids and account_ids_set:
        ml_lst_result = await db.execute(
            select(ProductListing)
            .where(
                ProductListing.platform_item_id.in_(orphan_ml_ids),
                ProductListing.account_id.in_(account_ids_set),
            )
            .order_by(ProductListing.id)
        )
        for lst in ml_lst_result.scalars().all():
            key = (lst.account_id, lst.platform_item_id)
            if key not in ml_item_listing_map:
                ml_item_listing_map[key] = lst

    # Extend images_by_catalog with catalog images from SKU and ml_item_id based listings
    extra_listing_catalog_ids = {
        lst.catalog_product_id
        for lst in (*sku_listing_map.values(), *ml_item_listing_map.values())
        if lst.catalog_product_id and lst.catalog_product_id not in images_by_catalog
    }
    if extra_listing_catalog_ids:
        img2_result = await db.execute(
            select(CatalogProductImage)
            .where(CatalogProductImage.product_id.in_(extra_listing_catalog_ids))
            .order_by(CatalogProductImage.sort_order)
        )
        for img in img2_result.scalars().all():
            if img.product_id not in images_by_catalog:
                images_by_catalog[img.product_id] = img.url

    # Batch: CMIG info for all orders (for filter and display)
    cmig_ids = {o.cmig_id for o in orders if o.cmig_id}
    cmig_map: dict = {}
    if cmig_ids:
        cmig_result = await db.execute(select(CMIG).where(CMIG.id.in_(cmig_ids)))
        for c in cmig_result.scalars().all():
            cmig_map[c.id] = {
                "id": c.id,
                "trade_name": c.trade_name,
                "company_name": c.company_name,
                "cnpj": c.cnpj,
                "cpf": c.cpf,
            }

    # Batch: cost maps para fallback de product_cost em pedidos antigos sem unit_cost.
    # catalog_cost_map  → custo do PG (CatalogProduct)
    # cmig_cost_map     → custo do produto CMIG vinculado ao PG (preferido por galpão)
    all_catalog_ids = set(catalog_ids)
    for dp in dp_map.values():
        if dp.catalog_product_id:
            all_catalog_ids.add(dp.catalog_product_id)
    catalog_cost_map: dict = {}
    if all_catalog_ids:
        cp_result = await db.execute(
            select(CatalogProduct.id, CatalogProduct.cost_price).where(
                CatalogProduct.id.in_(all_catalog_ids)
            )
        )
        catalog_cost_map = {cid: cost for cid, cost in cp_result.all() if cost is not None}
    cmig_cost_map: dict = {}
    if cmig_ids and all_catalog_ids:
        cm_result = await db.execute(
            select(CMIGProduct.cmig_id, CMIGProduct.pg_product_id, CMIGProduct.cost_price).where(
                CMIGProduct.cmig_id.in_(cmig_ids),
                CMIGProduct.pg_product_id.in_(all_catalog_ids),
            )
        )
        for cmig_id, pg_id, cost in cm_result.all():
            if cost is not None and pg_id is not None:
                cmig_cost_map[(cmig_id, pg_id)] = cost

    # cmig_product_cost_map → custo por cmig_product_id (para resolução via Listing.cmig_product_id)
    cmig_product_ids = {
        lst.cmig_product_id
        for lst in (
            *listing_map.values(),
            *sku_listing_map.values(),
            *ml_item_listing_map.values(),
        )
        if lst.cmig_product_id
    }
    cmig_product_cost_map: dict = {}
    if cmig_product_ids:
        cpc_result = await db.execute(
            select(CMIGProduct.id, CMIGProduct.cost_price).where(
                CMIGProduct.id.in_(cmig_product_ids)
            )
        )
        cmig_product_cost_map = {cid: cost for cid, cost in cpc_result.all() if cost is not None}

    # Stock map (live): (product_type, product_id) → (physical, reserved). Usado pra calcular
    # "disponível" no card do item no lugar do snapshot cacheado em ProductListing.available_quantity.
    local_catalog_ids = {
        lst.catalog_product_id
        for lst in (
            *listing_map.values(),
            *sku_listing_map.values(),
            *ml_item_listing_map.values(),
        )
        if lst.catalog_product_id and not lst.cmig_product_id
    }
    local_stock_map: dict = {}
    if cmig_product_ids:
        sq_result = await db.execute(
            select(
                CMIGProduct.id,
                CMIGProduct.stock_quantity,
                CMIGProduct.reserved_quantity,
            ).where(CMIGProduct.id.in_(cmig_product_ids))
        )
        for pid, sq, rq in sq_result.all():
            local_stock_map[("cmig", pid)] = (int(sq or 0), int(rq or 0))
    if local_catalog_ids:
        sq_result = await db.execute(
            select(
                CatalogProduct.id,
                CatalogProduct.stock_quantity,
                CatalogProduct.reserved_quantity,
            ).where(CatalogProduct.id.in_(local_catalog_ids))
        )
        for pid, sq, rq in sq_result.all():
            local_stock_map[("pg", pid)] = (int(sq or 0), int(rq or 0))

    # Full stock map (live, Fase 1): {(product_type, product_id): {account_id: {qty, reserved_qty}}}.
    # Fonte canônica: FullStock (tabela). Disponível FULL = qty - reserved_qty.
    from services.stock_view import load_full_per_account_map
    full_per_account_map = await load_full_per_account_map(
        db,
        cmig_ids=cmig_product_ids,
        pg_ids=local_catalog_ids,
        account_ids=account_ids_set,
    )

    return {
        "items": [
            _serialize_order_list(
                o,
                images_by_catalog,
                dp_map,
                listing_map,
                dp_images,
                sku_listing_map,
                ml_item_listing_map,
                cmig_map,
                catalog_cost_map,
                cmig_cost_map,
                cmig_product_cost_map,
                local_stock_map,
                full_per_account_map,
            )
            for o in orders
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.id == order_id)
    if current_user.role in ("ac",):
        query = query.where(_ac_visible_filter(current_user))

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = items_result.scalars().all()

    shipping_address = {}
    if order.shipping_address:
        try:
            shipping_address = json.loads(order.shipping_address)
        except (ValueError, TypeError):
            pass

    # Fallback runtime de product_cost (mesmo padrão do list_orders, mas escopo de 1 pedido)
    stored_pc = float(order.product_cost) if order.product_cost else None
    product_cost_out = stored_pc
    if product_cost_out is None:
        from services.order_item_resolver import resolve_order_item_link
        runtime_total = Decimal("0")
        any_resolved = False
        integration = None
        if order.account_id:
            integration = (
                await db.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
                )
            ).scalar_one_or_none()
        for it in items:
            if it.unit_cost is not None:
                any_resolved = True
                runtime_total += Decimal(str(it.unit_cost)) * (it.quantity or 0)
                continue
            resolved = await resolve_order_item_link(
                db,
                account_id=order.account_id,
                ml_item_id=it.ml_item_id,
                cmig_id=order.cmig_id,
                sku=it.sku,
                dropshipper_id=integration.owner_id if integration else None,
            )
            if resolved.unit_cost is not None:
                any_resolved = True
                runtime_total += resolved.unit_cost * (it.quantity or 0)
        if any_resolved:
            product_cost_out = round(float(runtime_total), 2)

    return {
        "id": order.id,
        "platform": order.platform,
        "platform_order_id": order.platform_order_id,
        "platform_order_ref": order.platform_order_ref,
        "platform_status": order.platform_status,
        "status": order.status,
        "payment_status": order.payment_status,
        "buyer_name": order.buyer_name,
        "buyer_email": order.buyer_email,
        "buyer_document": order.buyer_document,
        "shipping_address": shipping_address,
        "shipping_method": order.shipping_method,
        "shipping_mode": order.shipping_mode
        or classify_logistic_type(order.shipping_method, order.shipment_id),
        "shipping_mode_label": label_for_mode(
            order.shipping_mode
            or classify_logistic_type(order.shipping_method, order.shipment_id)
        ),
        "tracking_code": order.tracking_code,
        "tracking_url": order.tracking_url,
        "label_url": order.label_url,
        "nfe_url": _ml_nfe_url(order),
        "nfe_key": order.nfe_key,
        "nfe_status": order.nfe_status,
        "estimated_delivery_date": order.estimated_delivery_date.isoformat()
        if order.estimated_delivery_date
        else None,
        "sale_amount": float(order.sale_amount) if order.sale_amount else None,
        "product_cost": product_cost_out,
        "platform_fee": float(order.platform_fee) if order.platform_fee else None,
        "shipping_cost": float(order.shipping_cost) if order.shipping_cost else None,
        "total_debit": float(order.total_debit) if order.total_debit else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": i.id,
                "sku": i.sku,
                "title": i.title,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price) if i.unit_price else None,
                "unit_cost": float(i.unit_cost) if i.unit_cost else None,
                "dropshipper_product_id": i.dropshipper_product_id,
                "catalog_product_id": i.catalog_product_id,
                "cmig_product_id": i.cmig_product_id,
                "catalog_source": i.catalog_source,
            }
            for i in items
        ],
    }


@router.get("/{order_id}/debug-cost")
async def debug_cost(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Diagnóstico do cálculo de product_cost de UM pedido.

    Retorna, item a item: vínculos encontrados (DropshipperProduct, CatalogProduct,
    CMIGProduct), o custo de cada fonte, e qual seria escolhido. Útil para
    descobrir por que `product_cost` aparece vazio na tela.
    """
    order = (
        await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items))
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    from services.order_item_resolver import resolve_order_item_link

    integration = None
    if order.account_id:
        integration = (
            await db.execute(
                select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
            )
        ).scalar_one_or_none()

    items_debug = []
    total_runtime = Decimal("0")
    any_resolved = False
    for it in order.items:
        # Lookup via ProductListing (fonte canônica)
        listing = None
        if it.ml_item_id and order.account_id:
            listing = (
                await db.execute(
                    select(ProductListing).where(
                        ProductListing.platform_item_id == it.ml_item_id,
                        ProductListing.account_id == order.account_id,
                    )
                )
            ).scalar_one_or_none()

        # Lookup do helper (resolve em cascata)
        resolved = await resolve_order_item_link(
            db,
            account_id=order.account_id,
            ml_item_id=it.ml_item_id,
            cmig_id=order.cmig_id,
            sku=it.sku,
            dropshipper_id=integration.owner_id if integration else None,
        )

        # Fallbacks armazenados no item para debug
        dp_stored = None
        if it.dropshipper_product_id:
            dp_stored = (
                await db.execute(
                    select(DropshipperProduct).where(DropshipperProduct.id == it.dropshipper_product_id)
                )
            ).scalar_one_or_none()
        catalog_stored = None
        if it.catalog_product_id:
            catalog_stored = (
                await db.execute(
                    select(CatalogProduct).where(CatalogProduct.id == it.catalog_product_id)
                )
            ).scalar_one_or_none()

        chosen_cost = float(resolved.unit_cost) if resolved.unit_cost is not None else None
        runtime = float(it.unit_cost) if it.unit_cost is not None else chosen_cost
        if runtime is not None:
            any_resolved = True
            total_runtime += Decimal(str(runtime)) * (it.quantity or 0)

        items_debug.append({
            "order_item_id": it.id,
            "sku": it.sku,
            "title": it.title,
            "quantity": it.quantity,
            "unit_price": float(it.unit_price) if it.unit_price else None,
            "stored_unit_cost": float(it.unit_cost) if it.unit_cost is not None else None,
            "ml_item_id": it.ml_item_id,
            "stored_dropshipper_product_id": it.dropshipper_product_id,
            "stored_catalog_product_id": it.catalog_product_id,
            "stored_dropshipper_product_found": dp_stored is not None,
            "stored_catalog_product_found": catalog_stored is not None,
            # Resolução via ProductListing
            "listing_found": listing is not None,
            "listing_id": listing.id if listing else None,
            "listing_cmig_product_id": listing.cmig_product_id if listing else None,
            "listing_catalog_product_id": listing.catalog_product_id if listing else None,
            # Resultado do helper
            "resolved_via": resolved.source,
            "resolved_cmig_product_id": resolved.cmig_product.id if resolved.cmig_product else None,
            "resolved_cmig_cost_price": float(resolved.cmig_product.cost_price)
                if resolved.cmig_product and resolved.cmig_product.cost_price is not None else None,
            "resolved_catalog_product_id": resolved.catalog_product.id if resolved.catalog_product else None,
            "resolved_catalog_cost_price": float(resolved.catalog_product.cost_price)
                if resolved.catalog_product and resolved.catalog_product.cost_price is not None else None,
            "chosen_cost": chosen_cost,
            "runtime_unit_cost_used": runtime,
        })

    return {
        "order_id": order.id,
        "cmig_id": order.cmig_id,
        "account_id": order.account_id,
        "stored_product_cost": float(order.product_cost) if order.product_cost else None,
        "computed_product_cost_runtime": round(float(total_runtime), 2) if any_resolved else None,
        "any_item_resolved": any_resolved,
        "items": items_debug,
    }


@router.post("/{order_id}/pay")
async def pay_order(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedidos")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, _ac_visible_filter(current_user))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.payment_status == "paid":
        raise HTTPException(status_code=400, detail="Pedido já está pago")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Pedido cancelado")

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = items_result.scalars().all()
    # Itens CMIG ja sao propriedade da Conta CMIG do vendedor — nao geram debito.
    # Cobra apenas PG (galpao) e itens marketplace sem catalog_source definido.
    chargeable_items = [i for i in items if i.catalog_source != "cmig"]
    product_cost = sum((i.unit_cost or Decimal("0")) * i.quantity for i in chargeable_items)
    platform_fee = Decimal(str(settings.PLATFORM_FEE))
    shipping_cost = Decimal(str(order.shipping_cost or 0))
    total_debit = product_cost + platform_fee + shipping_cost

    if total_debit > 0:
        await debit_balance(
            db,
            dropshipper_id=current_user.id,
            amount=total_debit,
            description=f"Pagamento pedido #{order_id}",
            reference_type="order",
            reference_id=order_id,
        )

    order.payment_status = "paid"
    order.status = "paid"
    order.product_cost = product_cost
    order.platform_fee = platform_fee
    order.shipping_cost = shipping_cost
    order.total_debit = total_debit
    order.paid_at = datetime.now(UTC)
    await db.commit()

    return {
        "message": "Pedido pago com sucesso",
        "total_debit": float(total_debit),
        "new_status": order.status,
    }


@router.put("/{order_id}/shipping-cost")
async def update_shipping_cost(
    order_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("pedidos")),
    db: AsyncSession = Depends(get_db),
):
    """Edita o frete (`shipping_cost`) de um pedido manual ainda nao pago.

    Apos pago, o debito esta consolidado e o frete fica fixo.
    """
    order = (
        await db.execute(
            select(Order).where(Order.id == order_id, _ac_visible_filter(current_user))
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    if order.platform != "manual":
        raise HTTPException(
            status_code=400,
            detail="Edicao de frete disponivel apenas para pedidos manuais",
        )
    if order.payment_status == "paid":
        raise HTTPException(
            status_code=400, detail="Pedido ja pago — frete nao pode mais ser alterado"
        )
    raw = body.get("shipping_cost")
    if raw is None:
        raise HTTPException(status_code=400, detail="shipping_cost obrigatorio")
    try:
        value = Decimal(str(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="shipping_cost invalido") from None
    if value < 0:
        raise HTTPException(status_code=400, detail="shipping_cost deve ser >= 0")

    order.shipping_cost = value
    await db.commit()
    return {
        "id": order.id,
        "shipping_cost": float(order.shipping_cost),
    }


@router.put("/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    valid_statuses = ["label_generated", "label_printed", "separated", "shipped"]
    new_status = body.get("status")
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Status inválido. Permitidos: {valid_statuses}"
        )

    query = select(Order).where(Order.id == order_id)
    if current_user.role in ("ac",):
        query = query.where(_ac_visible_filter(current_user))

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    order.status = new_status
    if new_status == "shipped":
        order.shipped_at = datetime.now(UTC)
    await db.commit()

    if new_status == "shipped":
        try:
            from services.stock_reservation_service import confirm_dispatch
            await confirm_dispatch(db, order)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("confirm_dispatch order=%s: %s", order.id, exc)

    return {"status": order.status}


@router.get("/{order_id}/separation-info")
async def order_separation_info(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detalhes de separação e coleta de um pedido (para os ícones da Gestão de Pedidos).

    Junta os carimbos do pedido (separated_*/dispatched_*) com a gaiola
    (picking_cart_id → cart_number/modo/status) e resolve os nomes dos operadores.
    """
    from models.picking import PickingCart

    order = await _get_order_checked(db, order_id, current_user)

    cart = None
    if order.picking_cart_id:
        cart = (
            await db.execute(select(PickingCart).where(PickingCart.id == order.picking_cart_id))
        ).scalar_one_or_none()

    # Nomes dos operadores em lote
    user_ids = {order.separated_by, order.dispatched_by} - {None}
    names: dict[int, str] = {}
    if user_ids:
        rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        names = {u.id: (u.full_name or u.email) for u in rows}

    def _iso(dt):
        return dt.isoformat() if dt else None

    return {
        "has_gaiola": cart is not None,
        "separated": {
            "at": _iso(order.separated_at),
            "by_name": names.get(order.separated_by),
            "mode": cart.cart_mode if cart else None,
            "cart_number": cart.cart_number if cart else None,
            "cart_status": cart.status if cart else None,
        },
        "dispatched": {
            "at": _iso(order.dispatched_at) or _iso(order.shipped_at),
            "by_name": names.get(order.dispatched_by),
            "cart_number": cart.cart_number if cart else None,
        },
    }


@router.put("/{order_id}/notes")
async def update_order_notes(
    order_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.id == order_id)
    if current_user.role in ("ac",):
        query = query.where(_ac_visible_filter(current_user))

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    order.notes = body.get("notes", "")
    await db.commit()
    return {"ok": True}


@router.post("/{order_id}/hide")
async def hide_order(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedidos")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, _ac_visible_filter(current_user))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    order.is_hidden = True
    await db.commit()
    return {"ok": True}


async def _get_order_checked(db: AsyncSession, order_id: int, current_user: User) -> Order:
    """Fetch order with role-based access check."""
    query = select(Order).where(Order.id == order_id)
    if current_user.role == "ac":
        query = query.where(_ac_visible_filter(current_user))
    elif current_user.role == "go":
        raise HTTPException(status_code=403, detail="GO não tem permissão para esta ação")
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


def _extract_nfe_fields(invoice: dict) -> tuple[str | None, str | None, str | None]:
    """Extract (nfe_key, nfe_status, nfe_url) from an ML invoice dict.

    Handles three response shapes:
    - Faturador: attributes.invoice_key (44 digits), status="authorized"
    - Shipment endpoint: fiscal_key (38 digits), status="approved"
    - Order fiscal_data: access_key/key/number, status="authorized"
    """
    attrs = invoice.get("attributes") or {}
    # Priority: invoice_key (44-digit from Faturador) > fiscal_key > access_key/key/number
    nfe_key = (
        attrs.get("invoice_key")
        or invoice.get("fiscal_key")
        or invoice.get("access_key")
        or invoice.get("key")
        or invoice.get("number")
        or None
    )
    raw_status = invoice.get("status") or None
    # Shipment endpoint returns "approved"; Faturador and order return "authorized"
    nfe_status = "authorized" if raw_status == "approved" else (raw_status or "authorized")
    # When attrs is present it's a Faturador response: top-level "id" is the invoice_id
    # needed for the DANFE viewer URL. Store it as a plain digit string so _ml_nfe_url
    # can detect and use it without any path parsing.
    faturador_id = str(invoice.get("id") or "").strip() if attrs else ""
    nfe_url = (
        faturador_id
        if faturador_id and faturador_id.isdigit()
        else attrs.get("danfe_location")
        or invoice.get("pdf_url")
        or invoice.get("cdg_post")
        or invoice.get("url")
        or None
    )
    return nfe_key, nfe_status, nfe_url


@router.post("/{order_id}/emit-nfe")
async def emit_order_nfe(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Emit NF-e for an ML order via the ML Faturador API."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(
            status_code=400,
            detail="Emissão via Faturador ML disponível apenas para pedidos do Mercado Livre",
        )

    acc_result = await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
    )
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")

    # Conta pessoa física (CPF) não emite NF-e — o ML aguarda a DC-e. Não tentar
    # Faturador (evita o erro enganoso "erro na emissão da NFe").
    if await _order_issuer_type(db, order) == "cpf":
        raise HTTPException(status_code=400, detail=_DCE_PENDING_MSG)

    # Se o status local já indica nota autorizada/em processo, sincroniza o estado
    # real do ML antes de bloquear — o banco pode estar desatualizado.
    if order.nfe_status in ("authorized", "pending", "in_process"):
        try:
            await fetch_and_cache_order_invoices(db, order, account)
        except Exception:
            pass
        return {
            "ok": True,
            "already_existed": True,
            "nfe_status": order.nfe_status,
            "nfe_key": order.nfe_key,
            "nfe_url": _ml_nfe_url(order),
        }

    try:
        ml_order_id = int(order.platform_order_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ID do pedido inválido para emissão de NF-e")

    emit_result = await _ml.emit_nfe(account.access_token, account.platform_user_id, [ml_order_id])
    already_processing = emit_result.get("already_processing", False)

    # Mark as pending immediately so re-clicks are blocked even if fiscal fetch fails
    order.nfe_status = "pending"
    await db.commit()

    # Sync fiscal data: when already_processing use full invoice fetch (most reliable);
    # otherwise best-effort via get_order_fiscal_data.
    try:
        if already_processing:
            await fetch_and_cache_order_invoices(db, order, account)
        else:
            invoice = await _ml.get_order_fiscal_data(
                account.access_token,
                order.platform_order_id,
                seller_id=account.platform_user_id,
                shipment_id=order.shipment_id,
            )
            if invoice:
                order.nfe_key, order.nfe_status, order.nfe_url = _extract_nfe_fields(invoice)
                await db.commit()
    except Exception:
        pass

    return {
        "ok": True,
        "already_existed": already_processing,
        "nfe_status": order.nfe_status,
        "nfe_key": order.nfe_key,
        "nfe_url": _ml_nfe_url(order),
    }


@router.post("/{order_id}/emit-dce")
async def emit_order_dce(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devolve o link do EMISSOR DE DC-e DO PRÓPRIO MERCADO LIVRE para o pedido (conta CPF).

    Decisão 2026-07-09 (supersede ADR-0017): a emissão própria de DC-e via SEFAZ está DORMENTE.
    A DC-e passou a ser emitida pelo emissor omni do próprio ML — o ML emite e libera a etiqueta,
    sem SEFAZ/ICP-Brasil/certificado do nosso lado. Este endpoint apenas reconstrói e devolve o
    link; o front o abre em nova aba. (O código de auto-emissão permanece no repo, desativado.)
    """
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="DC-e disponível apenas para pedidos do Mercado Livre"
        )

    issuer = await _order_issuer_type(db, order)
    if issuer == "cnpj":
        raise HTTPException(
            status_code=400,
            detail="Esta conta tem CNPJ — emita NF-e, não DC-e.",
        )
    if issuer != "cpf":
        raise HTTPException(status_code=400, detail=_UNKNOWN_ISSUER_MSG)

    return {"ok": True, "ml_emitter": True, "emitter_url": _ml_dce_emitter_url(order)}


@router.get("/{order_id}/dace.pdf")
async def get_order_dace(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DACE (PDF) da DC-e autorizada do pedido — regenerado do XML persistido."""
    from models.fiscal import OrderDce
    from services.fiscal.dce.dace import gerar_dace

    order = await _get_order_checked(db, order_id, current_user)
    row = (
        await db.execute(
            select(OrderDce)
            .where(OrderDce.order_id == order.id, OrderDce.status == "authorized")
            .order_by(OrderDce.id.desc())
        )
    ).scalars().first()
    if not row or not row.xml:
        raise HTTPException(status_code=404, detail="DC-e autorizada não encontrada para este pedido")
    pdf = gerar_dace(row.xml, row.protocolo)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="{order_download_filename(TIPO_DACE, "pdf", order=order)}"'
        },
    )


@router.post("/{order_id}/sync-nfe")
async def sync_order_nfe(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pull fresh NF-e data from ML for one order and update local record."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        return {
            "ok": True,
            "nfe_status": order.nfe_status,
            "nfe_key": order.nfe_key,
            "nfe_url": order.nfe_url,
        }

    acc_result = await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
    )
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")

    try:
        invoice = await _ml.get_order_fiscal_data(
            account.access_token,
            order.platform_order_id,
            seller_id=account.platform_user_id,
            shipment_id=order.shipment_id,
        )
    except Exception:
        invoice = {}

    if invoice:
        order.nfe_key, order.nfe_status, order.nfe_url = _extract_nfe_fields(invoice)
        await db.commit()

    return {
        "ok": True,
        "nfe_status": order.nfe_status,
        "nfe_key": order.nfe_key,
        "nfe_url": _ml_nfe_url(order),
    }


@router.post("/{order_id}/confirm-return")
async def confirm_order_return(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedidos")),
    db: AsyncSession = Depends(get_db),
):
    """UGO confirma que o produto físico retornou ao galpão (pedido cancelado pós-despacho).
    O produto sai de awaiting_return_quantity e volta ao estoque disponível.
    """
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.return_status != "awaiting_return":
        raise HTTPException(
            status_code=400,
            detail="Pedido não está aguardando retorno de produto.",
        )

    from services.stock_reservation_service import confirm_pending_return
    await confirm_pending_return(db, order)
    return {"ok": True, "return_status": order.return_status}


@router.get("/awaiting-return")
async def list_orders_awaiting_return(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_menu_permission("pedidos")),
    db: AsyncSession = Depends(get_db),
):
    """Lista pedidos cancelados após despacho que ainda não tiveram o produto confirmado no galpão."""
    from sqlalchemy import func
    query = (
        select(Order)
        .where(Order.return_status == "awaiting_return")
        .order_by(Order.updated_at.desc())
    )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    rows = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    return {
        "items": [
            {
                "id": o.id,
                "platform_order_id": o.platform_order_id,
                "buyer_name": o.buyer_name,
                "shipment_status": o.shipment_status,
                "tracking_code": o.tracking_code,
                "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


_SHIPMENT_HISTORY_LABELS = {
    # status_history events
    "date_handling": {"label": "Em Preparação", "icon": "fa-box-open"},
    "date_ready_to_ship": {"label": "Pronto para Envio", "icon": "fa-dolly"},
    "date_shipped": {"label": "Despachado", "icon": "fa-truck"},
    "date_first_visit": {"label": "Primeira Tentativa de Entrega", "icon": "fa-route"},
    "date_not_delivered": {"label": "Não Entregue", "icon": "fa-exclamation-triangle"},
    "date_delivered": {"label": "Entregue", "icon": "fa-check-circle"},
    "date_returned": {"label": "Devolvido", "icon": "fa-undo"},
    "date_cancelled": {"label": "Cancelado", "icon": "fa-times-circle"},
    "date_first_printed": {"label": "Etiqueta Impressa", "icon": "fa-print"},
}

_SHIPMENT_STATUS_PT = {
    "pending": "Aguardando",
    "handling": "Em Preparação",
    "ready_to_ship": "Pronto para Envio",
    "shipped": "Despachado",
    "delivered": "Entregue",
    "not_delivered": "Não Entregue",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

_SHIPMENT_SUBSTATUS_PT = {
    # pending
    "shipment_paid": "Pagamento Confirmado",
    "buffered": "Em Espera",
    "waiting_for_collection": "Aguardando Coleta",
    # handling
    "regenerating": "Regerando Etiqueta",
    "stale": "Pendente Há Muito Tempo",
    "contact_with_carrier_needed": "Contato com Transportadora Necessário",
    # ready_to_ship
    "ready_to_print": "Pronto para Imprimir",
    "ready_to_pack": "Pronto para Embalar",
    "printed": "Etiqueta Impressa",
    "packed": "Embalado",
    "in_packing_list": "Na Lista de Embalagem",
    "ready_for_pickup": "Pronto para Retirada",
    "in_hub": "No Centro de Distribuição",
    "invoice_pending": "Aguardando NF-e",
    # shipped
    "first_visit": "1ª Tentativa de Entrega",
    "in_transit": "Em Trânsito",
    "in_transfer": "Em Transferência",
    "out_for_delivery": "Saiu para Entrega",
    "arrived": "Chegou no Destino",
    "soon_deliver": "Entrega em Breve",
    "delayed": "Atrasado",
    "second_visit": "2ª Tentativa de Entrega",
    "third_visit": "3ª Tentativa de Entrega",
    "not_visited": "Não Visitado",
    "waiting_for_withdrawal": "Aguardando Retirada",
    "receiver_absent": "Destinatário Ausente",
    "bad_address": "Endereço Incorreto",
    "could_not_be_delivered": "Não Pôde Ser Entregue",
    "retained": "Retido",
    "claimed_me": "Reclamação Aberta",
    "to_review": "Em Revisão",
    "stolen": "Roubado/Furtado",
    "lost": "Extraviado",
    "damaged": "Danificado",
    "forwarded_to_third": "Encaminhado a Terceiro",
    "returning_to_sender": "Retornando ao Remetente",
    "returned_to_origin": "Devolvido à Origem",
    # delivered
    "delivered": "Entregue",
    # not_delivered
    "not_localized": "Não Localizado",
    "not_dispatched": "Não Despachado",
    "rejected_damaged": "Rejeitado por Avaria",
    "rejected_other": "Rejeitado",
    "returned": "Devolvido",
    "destroyed": "Destruído",
    "fraud": "Fraude Detectada",
    "confiscated": "Confiscado",
    # cancelled
    "buyer_cancelled": "Cancelado pelo Comprador",
    "seller_cancelled": "Cancelado pelo Vendedor",
    "system_cancelled": "Cancelado pelo Sistema",
}


def _translate_shipment_event(status: str, substatus: str) -> str:
    """Build a Portuguese label from raw ML status + substatus."""
    parts = []
    if status:
        parts.append(_SHIPMENT_STATUS_PT.get(status, status.replace("_", " ").title()))
    if substatus:
        parts.append(_SHIPMENT_SUBSTATUS_PT.get(substatus, substatus.replace("_", " ").title()))
    return " · ".join(parts) if parts else "Atualização"


def _build_shipment_timeline(shipment: dict, history) -> list[dict]:
    """Combine shipment dates and history events into an ordered timeline."""
    events: list[dict] = []
    seen_dates: set[str] = set()

    # 1. Status history dates from main shipment object (date_handling, date_shipped, etc.)
    status_history = shipment.get("status_history") or {}
    if isinstance(status_history, dict):
        for key, value in status_history.items():
            if not value or not isinstance(value, str):
                continue
            meta = _SHIPMENT_HISTORY_LABELS.get(
                key,
                {"label": key.replace("date_", "").replace("_", " ").title(), "icon": "fa-circle"},
            )
            events.append(
                {
                    "date": value,
                    "label": meta["label"],
                    "icon": meta["icon"],
                    "code": key,
                }
            )
            seen_dates.add(value)

    # 2. Detailed history items from /shipments/{id}/history
    # Endpoint returns either a list or a dict with "history"/"results" key depending on shipment type
    if isinstance(history, list):
        history_items = history
    elif isinstance(history, dict):
        history_items = history.get("history") or history.get("results") or []
    else:
        history_items = []

    for item in history_items:
        if not isinstance(item, dict):
            continue
        date = item.get("date") or item.get("date_created") or item.get("date_created_from")
        status = item.get("status") or ""
        substatus = item.get("substatus") or ""
        if not date or date in seen_dates:
            continue
        events.append(
            {
                "date": date,
                "label": _translate_shipment_event(status, substatus),
                "icon": "fa-circle",
                "code": f"hist_{status}_{substatus}",
            }
        )
        seen_dates.add(date)

    # Sort by date ascending
    events.sort(key=lambda e: e.get("date") or "")
    return events


@router.get("/{order_id}/shipment-tracking")
async def get_shipment_tracking(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch full shipment tracking info from ML: status, dates, history, carrier."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre" or not order.shipment_id:
        return {"ok": False, "detail": "Sem informações de envio para este pedido."}

    account = await _get_account_for_order(db, order)
    if not account.access_token:
        raise HTTPException(status_code=400, detail="Conta sem token válido")

    try:
        shipment = await _ml.get_shipment(
            account.access_token, order.shipment_id, caller_id=account.platform_user_id
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao buscar envio no ML: {e}")

    if not shipment:
        return {"ok": False, "detail": "Envio não encontrado no Mercado Livre."}

    # Fetch history and carrier in parallel-ish (sequential is fine for 2 calls)
    try:
        history = await _ml.get_shipment_history(
            account.access_token, order.shipment_id, caller_id=account.platform_user_id
        )
    except Exception:
        history = {}
    try:
        carrier = await _ml.get_shipment_carrier(
            account.access_token, order.shipment_id, caller_id=account.platform_user_id
        )
    except Exception:
        carrier = {}

    ship_opt = shipment.get("shipping_option") or {}

    def _date_or_str(v):
        if isinstance(v, dict):
            return v.get("date") or v.get("from") or v.get("to")
        return v

    return {
        "ok": True,
        "shipment_id": order.shipment_id,
        "status": shipment.get("status"),
        "substatus": shipment.get("substatus"),
        "logistic_type": shipment.get("logistic_type"),
        "tracking_number": shipment.get("tracking_number"),
        "tracking_method": shipment.get("tracking_method"),
        "mode": shipment.get("mode"),
        "carrier": {
            "name": carrier.get("name") or carrier.get("carrier", {}).get("name"),
            "tracking_url": carrier.get("tracking_url") or carrier.get("url"),
        },
        "estimated": {
            "handling_limit": _date_or_str(ship_opt.get("estimated_handling_limit")),
            "delivery_time": _date_or_str(ship_opt.get("estimated_delivery_time"))
            or _date_or_str(shipment.get("estimated_delivery_time")),
            "delivery_limit": _date_or_str(ship_opt.get("estimated_delivery_limit")),
            "delivery_extended": _date_or_str(ship_opt.get("estimated_delivery_extended")),
            "delivery_final": _date_or_str(ship_opt.get("estimated_delivery_final")),
        },
        "timeline": _build_shipment_timeline(shipment, history),
    }


async def _delete_order(db: AsyncSession, order: Order):
    """Delete an order and all dependent rows, clearing WebhookEvents so marketplace
    pedidos possam ser re-baixados na próxima sincronização.

    Limpa explicitamente o que FKs Oracle não cascateiam:
      - order_items   → DELETE (ORM cascade não é confiável no AsyncSyncSession)
      - stock_movements → DELETE (auditoria do pedido sai junto)
      - invoices.order_id / returns.order_id → SET NULL (preserva NF-e/devolução)
    """
    from models.fiscal import Invoice
    from models.return_ import Return
    from models.stock_movement import StockMovement

    if order.platform_order_id:
        await db.execute(
            sa_delete(WebhookEvent).where(
                WebhookEvent.platform == order.platform,
                WebhookEvent.event_id.like(f"%:{order.platform_order_id}"),
            )
        )
    await db.execute(
        sa_update(Invoice).where(Invoice.order_id == order.id).values(order_id=None)
    )
    await db.execute(
        sa_update(Return).where(Return.order_id == order.id).values(order_id=None)
    )
    await db.execute(sa_delete(StockMovement).where(StockMovement.order_id == order.id))
    await db.execute(sa_delete(OrderItem).where(OrderItem.order_id == order.id))
    await db.execute(sa_delete(Order).where(Order.id == order.id))
    await db.commit()


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.id == order_id)
    if current_user.role == "ac":
        query = query.where(_ac_visible_filter(current_user))
    elif current_user.role == "go":
        raise HTTPException(status_code=403, detail="GO não pode excluir pedidos")

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    await _delete_order(db, order)
    return {"ok": True, "deleted_id": order_id}


@router.post("/bulk-delete")
async def bulk_delete_orders(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "go":
        raise HTTPException(status_code=403, detail="GO não pode excluir pedidos")

    ids = body.get("ids", [])
    if not ids or not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="Lista de IDs inválida")
    if len(ids) > 200:
        raise HTTPException(status_code=400, detail="Máximo de 200 pedidos por operação")

    query = select(Order).where(Order.id.in_(ids))
    if current_user.role == "ac":
        query = query.where(_ac_visible_filter(current_user))

    result = await db.execute(query)
    orders = result.scalars().all()

    deleted = []
    for order in orders:
        await _delete_order(db, order)
        deleted.append(order.id)

    return {"ok": True, "deleted": deleted, "count": len(deleted)}


async def _apply_ml_dates(db: AsyncSession, order: Order, ml_data: dict) -> bool:
    """Update created_at, paid_at and status from a fresh ML order response. Returns True if changed."""
    changed = False
    raw_created = ml_data.get("date_created") or ml_data.get("date_closed")
    if raw_created:
        try:
            new_created = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            local = order.created_at
            if local is not None and local.tzinfo is None:
                local = local.replace(tzinfo=UTC)
            if not local or abs((local - new_created).total_seconds()) > 60:
                order.created_at = new_created
                changed = True
        except Exception:
            pass

    if not order.paid_at:
        for pmt in ml_data.get("payments") or []:
            date_approved = pmt.get("date_approved")
            if date_approved:
                try:
                    order.paid_at = datetime.fromisoformat(
                        str(date_approved).replace("Z", "+00:00")
                    )
                    changed = True
                except Exception:
                    pass
                break
        if not order.paid_at:
            raw_closed = ml_data.get("date_closed")
            if raw_closed:
                try:
                    order.paid_at = datetime.fromisoformat(str(raw_closed).replace("Z", "+00:00"))
                    changed = True
                except Exception:
                    pass

    ml_status = ml_data.get("status")
    if ml_status == "paid" and order.status == "downloaded":
        order.status = "paid"
        order.payment_status = "paid"
        order.platform_status = "paid"
        changed = True
    elif ml_status == "cancelled" and order.status != "cancelled":
        order.status = "cancelled"
        order.platform_status = "cancelled"
        changed = True

    # Refresh ML fees (sale_fee aggregate) from order_items
    from services.webhook_service import _apply_fees_to_order

    if not order.sale_amount:
        try:
            order.sale_amount = Decimal(str(ml_data.get("total_amount") or 0))
        except Exception:
            pass
    prev_fee = order.platform_fee
    _apply_fees_to_order(order, ml_data)
    if order.platform_fee != prev_fee:
        changed = True

    return changed


async def _refresh_shipments(
    db: AsyncSession,
    ml_accounts: list,
    dropshipper_id: int | None = None,
    limit: int = 100,
) -> int:
    """Refresh shipment_status, tracking, dates from ML for orders that need updating.

    Catches:
    - Orders with shipment_id but missing/active shipment_status
    - Orders with NO shipment_id where ML returns one (re-fetches /orders/{id} first)

    When dropshipper_id is given, restricts to that user's orders. Otherwise updates all.
    """
    import asyncio as _asyncio

    from services.webhook_service import _apply_shipment_to_order

    if not ml_accounts:
        return 0
    accounts_map = {a.id: a for a in ml_accounts}

    base_where = [
        Order.platform == "mercadolivre",
        Order.is_hidden == False,
        Order.account_id.in_(list(accounts_map.keys())),
    ]
    if dropshipper_id is not None:
        base_where.append(Order.dropshipper_id == dropshipper_id)

    # Active or missing-data orders that need refresh
    sq = (
        select(Order)
        .where(
            *base_where,
            or_(
                # Has shipment_id but status missing or active
                (Order.shipment_id != None)
                & or_(
                    Order.shipment_status == None,
                    Order.shipment_status.in_(["pending", "handling", "ready_to_ship", "shipped"]),
                    Order.shipment_status.in_(["delivered", "not_delivered", "cancelled"])
                    & (
                        (Order.estimated_delivery_date == None)
                        | (Order.estimated_delivery_final == None)
                    ),
                    # Backfill: pedidos com shipment mas sem modo classificado
                    Order.shipping_mode == None,
                    Order.shipping_mode == "desconhecido",
                ),
                # No shipment_id at all — try to recover from /orders/{id}
                (Order.shipment_id == None) & (Order.status != "cancelled"),
            ),
        )
        .order_by(Order.id.desc())
        .limit(limit)
    )

    ship_orders = (await db.execute(sq)).scalars().all()
    updated = 0
    for order in ship_orders:
        account = accounts_map.get(order.account_id)
        if not account or not account.access_token:
            continue
        try:
            shipment_id = order.shipment_id
            # Recover missing shipment_id from /orders/{id}
            if not shipment_id:
                ml_order = await _ml.get_order(account.access_token, order.platform_order_id)
                shipment_id = (ml_order.get("shipping") or {}).get("id")
                if not shipment_id:
                    continue  # order has no shipment in ML either
                order.shipment_id = str(shipment_id)

            sd = await _ml.get_shipment(
                account.access_token, str(shipment_id), caller_id=account.platform_user_id
            )
            if not sd:
                continue
            costs = {}
            try:
                costs = await _ml.get_shipment_costs(account.access_token, str(shipment_id))
            except Exception:
                pass
            _apply_shipment_to_order(order, sd, costs)
            updated += 1
            # Pedido FULL que chegou a shipped/delivered → baixa o FULL (idempotente).
            # _apply_shipment_to_order não dispara isso sozinho (diferente do webhook).
            if order.shipping_mode == "full" and (order.shipment_status or "") in {"shipped", "delivered"}:
                try:
                    from services.stock_reservation_service import confirm_dispatch
                    await confirm_dispatch(db, order)
                except Exception:
                    pass
        except Exception:
            pass
        await _asyncio.sleep(0.1)

    if updated:
        await db.commit()
    return updated


async def _backfill_product_links(
    db: AsyncSession,
    ml_accounts: list,
    current_user: User,
    limit: int = 300,
) -> int:
    """Resolve vínculo produto↔OrderItem em pedidos que ainda não têm.

    Itera Orders (escopo do usuário) cujos OrderItems estejam sem
    dropshipper_product_id E sem catalog_product_id, e chama o helper
    de resolução via ProductListing. Idempotente.
    """
    from services.webhook_service import _backfill_order_links

    # Subquery: pedidos que têm pelo menos um item sem vínculo
    orphan_subq = (
        select(OrderItem.order_id)
        .where(
            OrderItem.dropshipper_product_id.is_(None),
            OrderItem.catalog_product_id.is_(None),
        )
        .distinct()
    )

    q = (
        select(Order)
        .where(Order.is_hidden == False, Order.id.in_(orphan_subq))
        .order_by(Order.id.desc())
        .limit(limit)
    )
    if current_user.role == "ac":
        q = q.where(_ac_visible_filter(current_user))
    elif current_user.role == "ugo" and current_user.warehouse_id:
        from models.cmig import CMIG
        ugo_cmigs = select(CMIG.id).where(CMIG.warehouse_id == current_user.warehouse_id)
        q = q.where(Order.cmig_id.in_(ugo_cmigs))

    orders = (await db.execute(q)).scalars().all()

    accounts_by_id = {a.id: a for a in ml_accounts}
    fixed = 0
    for o in orders:
        # MarketplaceAccount fictícia só pro helper extrair owner_id; busca real se faltar
        integration = accounts_by_id.get(o.account_id)
        if not integration and o.account_id:
            integration = (
                await db.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id == o.account_id)
                )
            ).scalar_one_or_none()
        try:
            if await _backfill_order_links(db, o, integration):
                fixed += 1
        except Exception:
            continue

    if fixed:
        await db.commit()
    return fixed


async def _backfill_order_dates(
    db: AsyncSession,
    ml_accounts: list,
    current_user: User,
    platform_order_ids: list | None = None,
) -> int:
    """Fix created_at/paid_at for ML orders where SYSTIMESTAMP artifact was stored.

    When platform_order_ids is given (sync-range), fixes those specific orders.
    Otherwise uses heuristic detection (created_at > paid_at or paid_at missing).
    """
    import asyncio as _asyncio

    if not ml_accounts:
        return 0
    accounts_map = {a.id: a for a in ml_accounts}

    if platform_order_ids:
        # Targeted: fix orders in the sync range PLUS any order (any status, including cancelled)
        # that has a wrong date detected via heuristics
        dq = (
            select(Order)
            .where(
                Order.platform == "mercadolivre",
                Order.is_hidden == False,
                Order.account_id.in_(list(accounts_map.keys())),
                or_(
                    Order.platform_order_id.in_([str(i) for i in platform_order_ids]),
                    (Order.paid_at != None) & (Order.created_at > Order.paid_at),
                    (Order.paid_at == None) & (Order.platform_status.in_(["paid", "cancelled"])),
                ),
            )
            .order_by(Order.id.desc())
            .limit(300)
        )
    else:
        # Heuristic only: detect orders with wrong dates regardless of sync range
        dq = (
            select(Order)
            .where(
                Order.platform == "mercadolivre",
                Order.is_hidden == False,
                Order.account_id.in_(list(accounts_map.keys())),
                or_(
                    (Order.paid_at != None) & (Order.created_at > Order.paid_at),
                    (Order.paid_at == None) & (Order.platform_status.in_(["paid", "cancelled"])),
                ),
            )
            .order_by(Order.id.desc())
            .limit(100)
        )

    if current_user.role == "ac":
        dq = dq.where(_ac_visible_filter(current_user))

    dates_orders = (await db.execute(dq)).scalars().all()
    fixed = 0
    for order in dates_orders:
        account = accounts_map.get(order.account_id)
        if not account or not account.access_token:
            continue
        try:
            ml_data = await _ml.get_order(account.access_token, order.platform_order_id)
            if await _apply_ml_dates(db, order, ml_data):
                fixed += 1
        except Exception:
            pass
        await _asyncio.sleep(0.1)
    if fixed:
        await db.commit()
    return fixed


@router.post("/{order_id}/debug-shipping-mode")
async def debug_shipping_mode(
    order_id: int,
    apply: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Diagnostico verboso: testa 4 variantes da chamada /shipments/{id} no ML
    para descobrir por que logistic_type vem null.

    apply=true tambem aplica e commita a primeira variante que funcionou.
    """
    import httpx

    from services.ml_service import ML_API_BASE
    from services.webhook_service import _apply_shipment_to_order

    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Pedido nao e do Mercado Livre")
    if not order.shipment_id:
        return {"ok": False, "reason": "Pedido sem shipment_id no DB"}

    account = await _get_account_for_order(db, order)
    if not account or not account.access_token:
        raise HTTPException(status_code=400, detail="Conta sem access_token")

    sid = str(order.shipment_id)
    seller = account.platform_user_id
    token = account.access_token
    base = f"{ML_API_BASE}/shipments/{sid}"

    variants = [
        {"name": "plain",        "url": base, "params": {}, "extra_headers": {}},
        {"name": "caller_id_q",  "url": base, "params": {"caller.id": str(seller) if seller else ""}, "extra_headers": {}},
        {"name": "x_caller_h",   "url": base, "params": {}, "extra_headers": {"x-caller-id": str(seller) if seller else ""}},
        {"name": "format_new",   "url": base, "params": {}, "extra_headers": {"x-format-new": "true"}},
        {"name": "caller+new",   "url": base, "params": {"caller.id": str(seller) if seller else ""}, "extra_headers": {"x-format-new": "true"}},
    ]

    results = []
    first_full = None
    async with httpx.AsyncClient(timeout=15.0) as client:
        for v in variants:
            headers = {"Authorization": f"Bearer {token}", **v["extra_headers"]}
            try:
                resp = await client.get(v["url"], params=v["params"] or None, headers=headers)
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                lt = body.get("logistic_type")
                results.append({
                    "variant": v["name"],
                    "http_status": resp.status_code,
                    "logistic_type": lt,
                    "status": body.get("status"),
                    "substatus": body.get("substatus"),
                    "mode": body.get("mode"),
                    "shipping_option_present": bool(body.get("shipping_option")),
                    "sender_id": body.get("sender_id") or (body.get("source") or {}).get("user_id"),
                    "receiver_id": body.get("receiver_id"),
                    "error": body.get("error") or body.get("message"),
                    "cause_count": len(body.get("cause") or []),
                })
                if lt and first_full is None:
                    first_full = (v["name"], body)
            except Exception as e:
                results.append({"variant": v["name"], "error_exc": str(e)})

    diag = {
        "ok": True,
        "order_id": order.id,
        "shipment_id": sid,
        "account": {
            "id": account.id,
            "platform_user_id": account.platform_user_id,
            "email": account.email,
            "is_active": account.is_active,
            "token_present": bool(account.access_token),
            "token_prefix": (account.access_token or "")[:8] + "...",
        },
        "db_before": {
            "shipping_method": order.shipping_method,
            "shipping_mode": order.shipping_mode,
            "shipment_status": order.shipment_status,
        },
        "ml_variants": results,
        "first_variant_with_logistic_type": first_full[0] if first_full else None,
    }

    if apply and first_full:
        _apply_shipment_to_order(order, first_full[1])
        await db.commit()
        await db.refresh(order)
        diag["db_after"] = {
            "shipping_method": order.shipping_method,
            "shipping_mode": order.shipping_mode,
            "shipment_status": order.shipment_status,
        }
        diag["applied"] = True

    return diag


@router.post("/refresh-shipping-modes")
async def refresh_shipping_modes(
    limit: int = 300,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Endpoint LEVE: refaz apenas o fetch de shipment para pedidos com shipping_mode
    NULL/desconhecido. Nao roda NF-e sync, nao busca recentes do ML, nao backfill datas.

    Pode ser chamado varias vezes em sequencia ate cobrir todos os pedidos pendentes.
    Retorna {processed, updated, remaining}.
    """
    ml_accs_result = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.owner_id == current_user.id,
            MarketplaceAccount.platform == "mercadolivre",
            MarketplaceAccount.is_active == True,
        )
    )
    ml_accounts = ml_accs_result.scalars().all()
    if not ml_accounts:
        return {"ok": False, "reason": "Sem contas ML ativas"}

    dropshipper_id = current_user.id if current_user.role == "ac" else None
    updated = await _refresh_shipments(
        db,
        ml_accounts,
        dropshipper_id=dropshipper_id,
        limit=limit,
    )

    # Conta quantos ainda faltam (pra usuario saber se precisa rodar mais vezes)
    base_where = [
        Order.platform == "mercadolivre",
        Order.is_hidden == False,
        Order.account_id.in_([a.id for a in ml_accounts]),
        Order.shipment_id != None,
        or_(Order.shipping_mode == None, Order.shipping_mode == "desconhecido"),
    ]
    if dropshipper_id is not None:
        base_where.append(Order.dropshipper_id == dropshipper_id)
    remaining = (
        await db.execute(select(func.count()).select_from(select(Order).where(*base_where).subquery()))
    ).scalar()

    return {
        "ok": True,
        "processed_limit": limit,
        "updated": updated,
        "remaining_unclassified": remaining,
    }


@router.post("/sync")
async def trigger_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate sync for the current user's marketplace accounts (last 7 days) and check pending NF-e."""
    import asyncio

    from tasks.sync_orders import sync_ml_integration, sync_shopee_integration

    date_from = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    now_ts = int(time_module.time())

    ml_accs_result = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.owner_id == current_user.id,
            MarketplaceAccount.platform == "mercadolivre",
            MarketplaceAccount.is_active == True,
        )
    )
    shopee_result = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.owner_id == current_user.id,
            MarketplaceAccount.platform == "shopee",
            MarketplaceAccount.is_active == True,
        )
    )

    ml_accounts = ml_accs_result.scalars().all()

    imported = 0
    ml_order_ids: list[str] = []
    for account in ml_accounts:
        range_orders = await _ml.get_recent_orders(
            account.access_token, account.platform_user_id, date_from, None
        )
        ml_order_ids.extend(str(o.get("id")) for o in range_orders if o.get("id"))
        imported += await sync_ml_integration(db, account, date_from)
    for account in shopee_result.scalars().all():
        imported += await sync_shopee_integration(db, account, now_ts - 7 * 24 * 3600, now_ts)

    # NF-e sync: check pending ML orders for current user's accounts
    nfe_updated = 0
    if ml_accounts:
        accounts_map = {a.id: a for a in ml_accounts}
        from sqlalchemy import and_

        q = (
            select(Order)
            .where(
                Order.platform == "mercadolivre",
                Order.is_hidden == False,
                Order.account_id.in_(list(accounts_map.keys())),
                or_(
                    Order.nfe_status != "authorized",
                    Order.nfe_status == None,
                    # authorized but danfe_location not yet stored in nfe_url
                    and_(
                        Order.nfe_status == "authorized",
                        or_(Order.nfe_url == None, ~Order.nfe_url.contains("/danfe/")),
                    ),
                ),
            )
            .order_by(Order.id.desc())
            .limit(200)
        )
        if current_user.role == "ac":
            q = q.where(_ac_visible_filter(current_user))

        nfe_result = await db.execute(q)
        orders_to_check = nfe_result.scalars().all()

        for order in orders_to_check:
            account = accounts_map.get(order.account_id)
            if not account or not account.access_token:
                continue

            if not order.shipment_id:
                try:
                    ml_order_data = await _ml.get_order(
                        account.access_token, order.platform_order_id
                    )
                    sid = (ml_order_data.get("shipping") or {}).get("id")
                    if sid:
                        order.shipment_id = str(sid)
                except Exception:
                    pass

            try:
                invoice = await _ml.get_order_fiscal_data(
                    account.access_token,
                    order.platform_order_id,
                    seller_id=account.platform_user_id,
                    shipment_id=order.shipment_id,
                )
            except Exception:
                invoice = {}

            if invoice:
                new_key, new_status, new_url = _extract_nfe_fields(invoice)
                if new_key or new_status:
                    order.nfe_key = new_key
                    order.nfe_status = new_status
                    order.nfe_url = new_url
                    nfe_updated += 1

            await asyncio.sleep(0.15)

        if nfe_updated or any(o.shipment_id for o in orders_to_check):
            await db.commit()

    # Shipment status + dates sync: refresh ALL active shipments
    ship_updated = await _refresh_shipments(
        db,
        ml_accounts,
        dropshipper_id=current_user.id if current_user.role == "ac" else None,
        limit=100,
    )

    dates_fixed = await _backfill_order_dates(
        db, ml_accounts, current_user, platform_order_ids=ml_order_ids or None
    )

    # Backfill de vínculos produto↔pedido para pedidos antigos sem vínculo
    # (toda sync varre todos os pedidos do user que ainda têm OrderItem sem produto)
    links_fixed = await _backfill_product_links(db, ml_accounts, current_user)

    return {
        "ok": True,
        "imported": imported,
        "nfe_updated": nfe_updated,
        "ship_updated": ship_updated,
        "dates_fixed": dates_fixed,
        "links_fixed": links_fixed,
    }


@router.post("/sync-range")
async def sync_range(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync orders for a custom date range. Body: {date_from, date_to, platform}."""
    from tasks.sync_orders import sync_ml_integration, sync_shopee_integration

    date_from_str = body.get("date_from")
    date_to_str = body.get("date_to")
    platform = body.get("platform", "all")

    if not date_from_str:
        raise HTTPException(status_code=400, detail="date_from é obrigatório")

    # Validate and normalise dates to ISO format with timezone
    try:
        dt_from = datetime.fromisoformat(date_from_str)
        if dt_from.tzinfo is None:
            # data só-data do filtro = início do dia no horário do BRASIL → UTC
            dt_from = dt_from.replace(tzinfo=BR_TZ).astimezone(UTC)
        date_from_iso = dt_from.isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from inválido — use formato YYYY-MM-DD")

    date_to_iso: str | None = None
    ts_to = int(time_module.time())
    if date_to_str:
        try:
            dt_to = datetime.fromisoformat(date_to_str)
            if dt_to.tzinfo is None:
                # date_to = fim do dia no horário do BRASIL → UTC (não cortar as últimas 3h locais)
                dt_to = dt_to.replace(hour=23, minute=59, second=59, tzinfo=BR_TZ).astimezone(UTC)
            date_to_iso = dt_to.isoformat()
            ts_to = int(dt_to.timestamp())
        except ValueError:
            raise HTTPException(status_code=400, detail="date_to inválido — use formato YYYY-MM-DD")

    ts_from = int(dt_from.timestamp())

    imported = 0
    ml_accounts = []
    ml_order_ids: list[str] = []

    if platform in ("all", "mercadolivre"):
        ml_result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.owner_id == current_user.id,
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
            )
        )
        ml_accounts = ml_result.scalars().all()
        for account in ml_accounts:
            # Collect the ML order IDs in this range for targeted date backfill
            range_orders = await _ml.get_recent_orders(
                account.access_token, account.platform_user_id, date_from_iso, date_to_iso
            )
            ml_order_ids.extend(str(o.get("id")) for o in range_orders if o.get("id"))
            imported += await sync_ml_integration(db, account, date_from_iso, date_to_iso)

    if platform in ("all", "shopee"):
        shopee_result = await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.owner_id == current_user.id,
                MarketplaceAccount.platform == "shopee",
                MarketplaceAccount.is_active == True,
            )
        )
        for account in shopee_result.scalars().all():
            imported += await sync_shopee_integration(db, account, ts_from, ts_to)

    # NF-e sync: check pending ML orders in the synced range
    import asyncio

    nfe_updated = 0
    if ml_accounts:
        accounts_map = {a.id: a for a in ml_accounts}
        from sqlalchemy import and_

        q = (
            select(Order)
            .where(
                Order.platform == "mercadolivre",
                Order.is_hidden == False,
                Order.account_id.in_(list(accounts_map.keys())),
                or_(
                    Order.nfe_status != "authorized",
                    Order.nfe_status == None,
                    and_(
                        Order.nfe_status == "authorized",
                        or_(Order.nfe_url == None, ~Order.nfe_url.contains("/danfe/")),
                    ),
                ),
            )
            .order_by(Order.id.desc())
            .limit(200)
        )
        if current_user.role == "ac":
            q = q.where(_ac_visible_filter(current_user))

        nfe_result = await db.execute(q)
        orders_to_check = nfe_result.scalars().all()

        for order in orders_to_check:
            account = accounts_map.get(order.account_id)
            if not account or not account.access_token:
                continue

            if not order.shipment_id:
                try:
                    ml_order_data = await _ml.get_order(
                        account.access_token, order.platform_order_id
                    )
                    sid = (ml_order_data.get("shipping") or {}).get("id")
                    if sid:
                        order.shipment_id = str(sid)
                except Exception:
                    pass

            try:
                invoice = await _ml.get_order_fiscal_data(
                    account.access_token,
                    order.platform_order_id,
                    seller_id=account.platform_user_id,
                    shipment_id=order.shipment_id,
                )
            except Exception:
                invoice = {}

            if invoice:
                new_key, new_status, new_url = _extract_nfe_fields(invoice)
                if new_key or new_status:
                    order.nfe_key = new_key
                    order.nfe_status = new_status
                    order.nfe_url = new_url
                    nfe_updated += 1

            await asyncio.sleep(0.15)

        if nfe_updated or any(o.shipment_id for o in orders_to_check):
            await db.commit()

    # Targeted backfill: fix dates for all ML orders found in this range
    dates_fixed = await _backfill_order_dates(
        db, ml_accounts, current_user, platform_order_ids=ml_order_ids or None
    )

    # Also refresh shipment status/dates for orders missing it
    ship_updated = await _refresh_shipments(
        db,
        ml_accounts,
        dropshipper_id=current_user.id if current_user.role == "ac" else None,
        limit=100,
    )

    # Backfill de vínculos produto↔pedido
    links_fixed = await _backfill_product_links(db, ml_accounts, current_user)

    return {
        "ok": True,
        "imported": imported,
        "nfe_updated": nfe_updated,
        "dates_fixed": dates_fixed,
        "ship_updated": ship_updated,
        "links_fixed": links_fixed,
        "date_from": date_from_iso,
        "date_to": date_to_iso,
    }


@router.post("/sync-nfe-batch")
async def sync_nfe_batch(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check NF-e status for all pending ML orders.

    For each ML order that is not yet authorized:
    1. If shipment_id is missing, fetch it from GET /orders/{id} and persist it.
    2. Call GET /shipments/{shipment_id}/invoice_data to get the real NF-e status.
    3. Update nfe_key, nfe_status, nfe_url in the database.

    Returns {checked, updated} counts.
    """
    import asyncio

    from sqlalchemy import and_

    q = (
        select(Order)
        .where(
            Order.platform == "mercadolivre",
            Order.is_hidden == False,
            or_(
                Order.nfe_status != "authorized",
                Order.nfe_status == None,
                and_(
                    Order.nfe_status == "authorized",
                    or_(Order.nfe_url == None, ~Order.nfe_url.contains("/danfe/")),
                ),
            ),
        )
        .order_by(Order.id.desc())
        .limit(200)
    )
    if current_user.role == "ac":
        q = q.where(_ac_visible_filter(current_user))

    result = await db.execute(q)
    orders_to_check = result.scalars().all()

    # Load accounts keyed by id for token lookup
    account_ids = {o.account_id for o in orders_to_check if o.account_id}
    acc_result = await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id.in_(account_ids))
    )
    accounts = {a.id: a for a in acc_result.scalars().all()}

    checked = 0
    updated = 0

    for order in orders_to_check:
        account = accounts.get(order.account_id)
        if not account or not account.access_token:
            continue

        checked += 1

        # Step 1: ensure shipment_id is stored
        if not order.shipment_id:
            try:
                ml_order_data = await _ml.get_order(account.access_token, order.platform_order_id)
                sid = (ml_order_data.get("shipping") or {}).get("id")
                if sid:
                    order.shipment_id = str(sid)
            except Exception:
                pass

        # Step 2: check invoice data
        try:
            invoice = await _ml.get_order_fiscal_data(
                account.access_token,
                order.platform_order_id,
                seller_id=account.platform_user_id,
                shipment_id=order.shipment_id,
            )
        except Exception:
            invoice = {}

        if invoice:
            new_key, new_status, new_url = _extract_nfe_fields(invoice)
            if new_key or new_status:
                order.nfe_key = new_key
                order.nfe_status = new_status
                order.nfe_url = new_url
                updated += 1

        # Small pause to respect ML rate limits
        await asyncio.sleep(0.15)

    if updated or any(o.shipment_id for o in orders_to_check):
        await db.commit()

    return {"ok": True, "checked": checked, "updated": updated}


# ─── Invoice endpoints ───────────────────────────────────────────────────────

_INVOICE_TYPE_LABELS = {
    "sale": "Venda",
    "devolution": "Devolução",
    "sale_return": "Retorno de Venda",
    "inbound": "Remessa",
    "inbound_return": "Retorno de Remessa",
    "symbolic_inbound": "Remessa Simbólica",
    "symbolic_inbound_return": "Retorno Simbólico",
    "removal": "Retirada",
    "input": "Alta de Estoque",
    "output": "Baixa de Estoque",
    "correction_letter": "Carta de Correção",
    "cte": "CT-e",
}


def _serialize_invoice(inv: dict) -> dict:
    attrs = inv.get("attributes") or {}
    fiscal = inv.get("fiscal_data") or {}
    t_type = fiscal.get("transaction_type") or ""
    return {
        "id": str(inv.get("id", "")),
        "status": inv.get("status"),
        "transaction_status": inv.get("transaction_status"),
        "invoice_number": inv.get("invoice_number"),
        "invoice_series": inv.get("invoice_series"),
        "issued_date": inv.get("issued_date"),
        "amount": inv.get("amount"),
        "transaction_type": t_type,
        "transaction_type_label": _INVOICE_TYPE_LABELS.get(
            t_type, t_type.replace("_", " ").title()
        ),
        "transaction_type_description": fiscal.get("transaction_type_description"),
        "invoice_key": attrs.get("invoice_key"),
        "xml_location": attrs.get("xml_location"),
        "danfe_location": attrs.get("danfe_location"),
        "errors": inv.get("errors") or [],
    }


async def _get_account_for_order(db, order: Order):
    acc_result = await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
    )
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")
    return account


async def fetch_and_cache_order_invoices(db, order: Order, account) -> list[dict]:
    """Busca no ML todas as NF-e de um pedido (venda + notas de referência, ex.:
    Retorno Simbólico de pedidos Full), persiste nfe_status/nfe_key/nfe_url e
    cacheia a lista completa em order.nfe_invoices_json. Retorna a lista
    serializada. Reutilizado pela tela Fiscal>Saídas (sync de NF-e do ML).
    """
    invoices: list[dict] = []
    main = await _ml.get_invoices_by_order(
        account.access_token, account.platform_user_id, order.platform_order_id
    )
    if main:
        invoices.append(_serialize_invoice(main))
        # Persistir o status real da NF-e no pedido. Para pedidos Full o ML
        # emite a nota automaticamente, então o vendedor nunca clica em
        # "Emitir NF-e" e o nfe_status local ficava preso em vazio.
        try:
            new_key, new_status, new_url = _extract_nfe_fields(main)
            if new_status and (
                order.nfe_status != new_status
                or (new_key and order.nfe_key != new_key)
                or (new_url and order.nfe_url != new_url)
            ):
                order.nfe_status = new_status
                if new_key:
                    order.nfe_key = new_key
                if new_url:
                    order.nfe_url = new_url
        except Exception as e:
            print(f"[orders] failed to persist nfe status order={order.id}: {e}")
        # Notas de referência (cadeia Fulfillment — inclui o Retorno Simbólico)
        attrs = main.get("attributes") or {}
        refs = attrs.get("reference_invoices") or []
        if isinstance(refs, list):
            for ref in refs:
                ref_id = str(ref.get("id") if isinstance(ref, dict) else ref)
                if ref_id:
                    ref_inv = await _ml.get_invoice_by_id(
                        account.access_token, account.platform_user_id, ref_id
                    )
                    if ref_inv:
                        invoices.append(_serialize_invoice(ref_inv))

    # Cache da lista completa — usado pela tela Fiscal>Saídas sem refazer
    # chamadas ao ML por pedido.
    try:
        snapshot = json.dumps(invoices, ensure_ascii=False) if invoices else None
        if snapshot != order.nfe_invoices_json:
            order.nfe_invoices_json = snapshot
        await db.commit()
    except Exception as e:
        print(f"[orders] failed to cache nfe invoices order={order.id}: {e}")
    return invoices


@router.get("/{order_id}/invoices")
async def list_order_invoices(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all NF-e invoices for an ML order, including reference invoices."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        return {"invoices": []}

    account = await _get_account_for_order(db, order)
    invoices = await fetch_and_cache_order_invoices(db, order, account)

    return {
        "invoices": invoices,
        "nfe_status": order.nfe_status,
        "nfe_key": order.nfe_key,
        "nfe_url": _ml_nfe_url(order),
    }


@router.get("/{order_id}/invoices/{invoice_id}/xml")
async def download_invoice_xml(
    order_id: int,
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download XML of an invoice, proxied through our backend with ML auth."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Somente pedidos do Mercado Livre")

    account = await _get_account_for_order(db, order)
    path = f"/users/{account.platform_user_id}/invoices/documents/xml/{invoice_id}/authorized"
    content, _ = await _ml.fetch_invoice_file(account.access_token, path)

    return Response(
        content=content,
        media_type="application/xml",
        headers={
            "Content-Disposition":
                f'attachment; filename="{order_download_filename(TIPO_NFE, "xml", order=order)}"'
        },
    )


# Cache de etiquetas FORA de static/ — o PDF do ML tem nome+endereço do comprador (LGPD);
# servido só pelos endpoints autenticados (nunca por URL pública). Ver ADR-0015 (mesmo padrão do XML).
_LABELS_DIR = Path(__file__).resolve().parent.parent / "private_labels"


async def _emit_nfe_for_label(order: Order, account, db) -> None:
    """Emite a NF-e de um pedido cujo envio está aguardando nota (invoice_pending).

    Best-effort: se a NF-e já estiver em andamento, não reemite. Reaproveita o
    mesmo fluxo de emit_order_nfe.
    """
    if order.nfe_status in ("authorized", "pending", "in_process"):
        return
    try:
        ml_order_id = int(order.platform_order_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ID do pedido inválido para emissão de NF-e")
    await _ml.emit_nfe(account.access_token, account.platform_user_id, [ml_order_id])
    order.nfe_status = "pending"
    try:
        await db.commit()
    except Exception as e:
        print(f"[orders] failed to mark nfe pending order={order.id}: {e}")


async def _ml_label_fmt_bytes(
    db: AsyncSession, order: Order, current_user: User, fmt: str, refresh: bool = False
) -> bytes:
    """Bytes da etiqueta OFICIAL do ML de um pedido no formato pedido (pdf|zpl2).

    - Serve do cache em disco ({shipment_id}.{ext}) quando disponível.
    - No zpl2 anexa a etiqueta de CONFERÊNCIA (SKU/nome/qtd) — o cache guarda só o ML puro.
    - Levanta HTTPException nos estados inválidos (sem envio, Full, envio pendente,
      invoice_pending, cancelado). O `_emit_nfe_for_label` é idempotente (não reemite).
    """
    if not order.shipment_id:
        raise HTTPException(status_code=400, detail="Pedido sem envio — não é possível gerar etiqueta")
    if order.shipping_method and "fulfillment" in order.shipping_method:
        raise HTTPException(
            status_code=400,
            detail="Pedido Full — a logística é gerenciada pelo Mercado Livre, não há etiqueta para o vendedor imprimir",
        )
    if order.shipment_status in ("cancelled",):
        raise HTTPException(status_code=400, detail="Envio cancelado — etiqueta indisponível")

    ext = "zpl" if fmt == "zpl2" else "pdf"
    cache_path = _LABELS_DIR / f"{order.shipment_id}.{ext}"

    async def _with_conf(pure_content: bytes) -> bytes:
        """No ZPL anexa a conferência de produto (montada do banco, nunca cacheada)."""
        if fmt != "zpl2":
            return pure_content
        try:
            meta = await build_orders_label_meta(db, [order])
            conf = render_shipping_labels_zpl(meta, header_label=_ML_CONF_HEADER)
            if conf:
                return pure_content + b"\n" + conf
        except Exception as e:  # noqa: BLE001 — conferência é opcional, não perde o rótulo
            print(f"[orders] falha ao anexar conferência ZPL order={order.id}: {e}")
        return pure_content

    # Try cache first (unless forced refresh)
    if not refresh and cache_path.exists() and order.label_cached_at:
        return await _with_conf(cache_path.read_bytes())

    # Cache miss or forced refresh — fetch from ML
    if order.shipment_status in ("pending", None, ""):
        raise HTTPException(
            status_code=400,
            detail="Envio ainda não está pronto — aguarde o pagamento ser aprovado e o ML preparar a etiqueta",
        )

    account = await _get_account_for_order(db, order)
    if not account.access_token:
        raise HTTPException(status_code=400, detail="Conta sem token válido")

    # Buscar shipment fresco do ML para detectar Full (logistic_type) e
    # NF-e pendente (substatus invoice_pending) com dados atualizados.
    try:
        shipment = await _ml.get_shipment(
            account.access_token, order.shipment_id, caller_id=account.platform_user_id
        )
    except Exception:
        shipment = {}

    if shipment:
        # Backfill de logistic_type e status quando o ML divergir do que temos
        fresh_logistic = shipment.get("logistic_type")
        fresh_status = shipment.get("status")
        changed = False
        if fresh_logistic and fresh_logistic != order.shipping_method:
            order.shipping_method = fresh_logistic
            order.shipping_mode = classify_logistic_type(fresh_logistic, order.shipment_id)
            changed = True
        if fresh_status and fresh_status != order.shipment_status:
            order.shipment_status = fresh_status
            changed = True
        if changed:
            try:
                await db.commit()
            except Exception as e:
                print(
                    f"[orders] failed to backfill shipment fields shipment={order.shipment_id}: {e}"
                )

        # Pedido Full — etiqueta é gerenciada pelo ML, não há o que imprimir
        if "fulfillment" in (shipment.get("logistic_type") or ""):
            raise HTTPException(
                status_code=400,
                detail="Pedido Full — a logística é gerenciada pelo Mercado Livre, não há etiqueta para o vendedor imprimir",
            )

        # Documento fiscal pendente — o que o ML aguarda depende do emissor:
        # CNPJ → NF-e (emite via Faturador); CPF → DC-e (Declaração de Conteúdo).
        if shipment.get("substatus") == "invoice_pending":
            issuer = await _order_issuer_type(db, order)
            if issuer == "cnpj":
                await _emit_nfe_for_label(order, account, db)
                raise HTTPException(
                    status_code=400,
                    detail="NF-e enviada para emissão automaticamente — assim que for autorizada (alguns instantes) clique novamente para gerar a etiqueta.",
                )
            if issuer == "cpf":
                raise HTTPException(status_code=400, detail=_DCE_PENDING_MSG)
            raise HTTPException(status_code=400, detail=_UNKNOWN_ISSUER_MSG)

    # Rede de segurança: se o pré-fetch falhou, o erro bruto do ML ainda revela
    # pedidos Full / NF-e pendente.
    try:
        content, _ctype = await _ml.get_shipment_label(account.access_token, order.shipment_id, fmt)
    except HTTPException as e:
        msg = str(e.detail or "")
        if "is FF" in msg or "fulfillment" in msg.lower():
            if order.shipping_method != "fulfillment":
                order.shipping_method = "fulfillment"
                order.shipping_mode = classify_logistic_type("fulfillment", order.shipment_id)
                try:
                    await db.commit()
                except Exception:
                    pass
            raise HTTPException(
                status_code=400,
                detail="Pedido Full — a logística é gerenciada pelo Mercado Livre, não há etiqueta para o vendedor imprimir",
            )
        if "invoice_pending" in msg:
            issuer = await _order_issuer_type(db, order)
            if issuer == "cnpj":
                await _emit_nfe_for_label(order, account, db)
                raise HTTPException(
                    status_code=400,
                    detail="NF-e enviada para emissão automaticamente — assim que for autorizada (alguns instantes) clique novamente para gerar a etiqueta.",
                )
            if issuer == "cpf":
                raise HTTPException(status_code=400, detail=_DCE_PENDING_MSG)
            raise HTTPException(status_code=400, detail=_UNKNOWN_ISSUER_MSG)
        raise

    # Persist to disk + mark cached_at (cacheia só o conteúdo PURO do ML)
    try:
        _LABELS_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        order.label_cached_at = datetime.now(UTC)
        await db.commit()
    except Exception as e:
        print(f"[orders] failed to cache label shipment={order.shipment_id}: {e}")

    return await _with_conf(content)


@router.get("/{order_id}/label")
async def get_order_shipping_label(
    order_id: int,
    fmt: str = Query("pdf", regex="^(pdf|zpl2)$"),
    refresh: bool = Query(False, description="Força re-download do ML mesmo se já houver cache"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Etiqueta OFICIAL do ML (PDF ou ZPL2). Servida `inline`.

    PDF: shipping label + declaração de conteúdo + identificação do produto.
    ZPL: rótulo de envio do ML + etiqueta de conferência (SKU/nome/qtd) anexada.
    """
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Etiqueta disponível apenas para pedidos do Mercado Livre"
        )
    content = await _ml_label_fmt_bytes(db, order, current_user, fmt, refresh)
    # A etiqueta ZPL é gravada com extensão .txt (o conteúdo continua ZPL puro, text/plain) —
    # muitos leitores/impressoras esperam .txt e o eShip recusa o tipo .zpl no anexo.
    ext = "txt" if fmt == "zpl2" else "pdf"
    media_type = "text/plain" if fmt == "zpl2" else "application/pdf"
    filename = order_download_filename(TIPO_ETIQUETA, ext, order=order)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# Teto de segurança do ZIP de etiquetas em lote (cada pedido = até 2 chamadas ML no pior caso).
_LABELS_ZIP_MAX = 25


async def _order_label_pair(
    db: AsyncSession, order: Order, current_user: User, refresh: bool = False
) -> tuple[bytes | None, bytes | None]:
    """(pdf, zpl) da etiqueta do pedido — ML ou manual. Levanta HTTPException se indisponível.

    - Manual: usa a checagem de acesso CANÔNICA do manual (`_load_manual_label_data`), não o
      filtro genérico de pedidos, e renderiza PDF+ZPL internos.
    - ML: reusa `_ml_label_fmt_bytes` para cada formato (cache por extensão; sem reemitir NF-e).
    """
    if order.platform == "manual":
        # Import tardio: evita acoplamento de import entre os routers.
        from routers.manual_orders import _load_manual_label_data

        _o, items, cmig, items_meta = await _load_manual_label_data(order.id, current_user, db)
        pdf = render_manual_order_label(order=_o, items=items, cmig=cmig, items_meta=items_meta)
        zpl = render_manual_order_label_zpl(order=_o, items=items, cmig=cmig, items_meta=items_meta)
        return pdf, zpl
    if order.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Etiqueta indisponível para esta origem de pedido")
    pdf = await _ml_label_fmt_bytes(db, order, current_user, "pdf", refresh)
    zpl = await _ml_label_fmt_bytes(db, order, current_user, "zpl2", refresh)
    return pdf, zpl


def _zip_label_files(files: list[tuple[str, bytes]], warnings: list[str]) -> bytes:
    """Empacota (nome, bytes) num ZIP; anexa _avisos.txt quando há falhas parciais."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
        if warnings:
            z.writestr("_avisos.txt", "\n".join(warnings))
    return buf.getvalue()


@router.get("/{order_id}/label.zip")
async def get_order_label_zip(
    order_id: int,
    refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ZIP com a etiqueta em PDF **e** ZPL de UM pedido (ML ou manual). Download direto."""
    order = await _get_order_checked(db, order_id, current_user)
    pdf, zpl = await _order_label_pair(db, order, current_user, refresh)
    files: list[tuple[str, bytes]] = []
    if pdf:
        files.append((order_download_filename(TIPO_ETIQUETA, "pdf", order=order), pdf))
    if zpl:
        # ZPL gravado como .txt (conteúdo ZPL puro) — ver GET /{id}/label.
        files.append((order_download_filename(TIPO_ETIQUETA, "txt", order=order), zpl))
    zip_name = order_download_filename(TIPO_ETIQUETA, "zip", order=order)
    return Response(
        content=_zip_label_files(files, []),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.post("/labels.zip")
async def get_orders_labels_zip(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ZIP com as etiquetas (PDF+ZPL) de VÁRIOS pedidos marcados. Body: {order_ids: [...]}.

    Falha por pedido não derruba o lote — vira uma linha em `_avisos.txt`.
    """
    ids = body.get("order_ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=422, detail="Informe order_ids (lista de IDs de pedido)")
    ids = list(dict.fromkeys(ids))  # dedup preservando ordem
    if len(ids) > _LABELS_ZIP_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"Máximo de {_LABELS_ZIP_MAX} pedidos por ZIP — selecione menos pedidos.",
        )

    files: list[tuple[str, bytes]] = []
    warnings: list[str] = []
    pedidos_ok: list[Order] = []   # pedidos que renderam pelo menos uma etiqueta
    for oid in ids:
        try:
            order = await _get_order_checked(db, int(oid), current_user)
        except HTTPException:
            warnings.append(f"Pedido {oid}: sem acesso ou inexistente.")
            continue
        try:
            pdf, zpl = await _order_label_pair(db, order, current_user)
        except HTTPException as e:
            warnings.append(f"Pedido {order.id} ({order.buyer_name or 's/ nome'}): {e.detail}")
            continue
        if pdf:
            files.append((order_download_filename(TIPO_ETIQUETA, "pdf", order=order), pdf))
        if zpl:
            # ZPL gravado como .txt (conteúdo ZPL puro) — ver GET /{id}/label.
            files.append((order_download_filename(TIPO_ETIQUETA, "txt", order=order), zpl))
        if pdf or zpl:
            pedidos_ok.append(order)

    if not files:
        raise HTTPException(
            status_code=404,
            detail=("Nenhuma etiqueta disponível para os pedidos selecionados. "
                    + " | ".join(warnings))[:400],
        )
    zip_name = await _batch_labels_zip_name(db, pedidos_ok)
    return Response(
        content=_zip_label_files(files, warnings),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


async def _batch_labels_zip_name(db: AsyncSession, pedidos: list[Order]) -> str:
    """Nome do ZIP em lote: `Etiquetas_<CMIG>_<qtd>-pedidos_<data-hora>.zip`.

    A CMIG vem dos pedidos incluídos (só as que renderam etiqueta). Vários CMIGs → "varias".
    A data/hora é a da criação do ZIP, no fuso local (America/Sao_Paulo, ADR-0013).
    """
    from datetime import datetime

    from models.cmig import CMIG

    cmig_ids = list(dict.fromkeys(o.cmig_id for o in pedidos if o.cmig_id))
    if len(cmig_ids) == 1:
        nome = (
            await db.execute(select(CMIG.trade_name, CMIG.company_name).where(CMIG.id == cmig_ids[0]))
        ).first()
        cmig_slug = slugify_name(
            (nome[0] or nome[1]) if nome else None, maxlen=40, fallback="cmig"
        )
    elif len(cmig_ids) > 1:
        cmig_slug = "varias"
    else:
        cmig_slug = "cmig"

    data_hora = datetime.now(BR_TZ).strftime("%d-%m-%Y_%Hh%M")
    return f"Etiquetas_{cmig_slug}_{len(pedidos)}-pedidos_{data_hora}.zip"


@router.get("/{order_id}/invoices/{invoice_id}/danfe")
async def download_invoice_danfe(
    order_id: int,
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download/view DANFE PDF, proxied through our backend with ML auth."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Somente pedidos do Mercado Livre")

    account = await _get_account_for_order(db, order)
    path = f"/users/{account.platform_user_id}/invoices/sites/MLB/documents/danfe/{invoice_id}"
    content, _ = await _ml.fetch_invoice_file(account.access_token, path)

    return Response(
        content=content,
        media_type="application/pdf",
        # inline: browser abre diretamente (para imprimir); use attachment para forçar download
        headers={
            "Content-Disposition":
                f'inline; filename="{order_download_filename(TIPO_DANFE, "pdf", order=order)}"'
        },
    )

"""Logística Shopee (BR) — Fase 4: despacho (ship_order) + etiqueta + rastreio.

Sequência BR: NF-e validada (Fase 3) → get_shipping_parameter → ship_order (síncrono) →
create_shipping_document (assíncrono) → poll get_shipping_document_result → download (PDF) →
tracking. Ramo 100% Shopee — NÃO toca o ML nem a tela de Separação (picking é só ML).

RBAC: operação de expedição → require_menu_permission("separacao"). O gate de NF-e validada é
pré-condição de DADO (revalidada na Shopee), não RBAC.
"""
from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.user import User
from routers.shopee_fiscal import _shopee_order  # resolve pedido Shopee + conta (RBAC) + token
from services import shopee_service

router = APIRouter()

_LABELS_DIR = Path(__file__).resolve().parent.parent / "private_labels"
_SHIPPED_STATES = {"shipped", "delivered"}
_DOC_POLL_TRIES = 4
_DOC_POLL_DELAY = 1.5  # s — poll curto no request; se não ficar pronto, reentrante ("clique de novo")


async def _ensure_invoice_validated(order, token, shop_id, db: AsyncSession) -> None:
    """Revalida na Shopee que a NF-e foi validada (invoice_data preenchido) — não confia só no
    flag local. Promove `shopee_invoice_status=validated` e falha alto se ainda não validada."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order.platform_order_id], optional_fields="invoice_data,order_status")
    inv = (dets[0].get("invoice_data") if dets else None) or {}
    if inv.get("number") or inv.get("access_key"):
        if order.shopee_invoice_status != "validated":
            order.shopee_invoice_status = "validated"
            await db.commit()
        return
    raise HTTPException(
        status_code=400,
        detail="A NF-e ainda não foi validada pela Shopee (SEFAZ). Anexe/valide a nota (Fiscal → "
               "Anexar NF-e) antes de despachar — no BR o envio só é liberado com a nota validada.",
    )


async def _package_number(token, shop_id, order_sn) -> str | None:
    """Busca fresco o package_number (obrigatório se multipacote). None p/ pacote único."""
    dets = await shopee_service.get_order_detail(
        token, shop_id, [order_sn], optional_fields="package_list,order_status")
    pkgs = (dets[0].get("package_list") if dets else None) or []
    return (pkgs[0].get("package_number") if pkgs else None) or None


def _normalize_label(raw: bytes) -> tuple[bytes, str, str]:
    """Normaliza a etiqueta CRUA da Shopee → (bytes, media_type, ext). O formato varia por canal:
    PDF direto; ZIP com PDF dentro; ou ZIP com ZPL (ex.: Shopee Xpress BR, que só entrega ZPL
    térmico — `thermal_zpl_shipping_label.txt`). Para ZPL servimos o arquivo p/ impressora térmica
    (não fingimos PDF). Nunca estoura — formato desconhecido cai como ZPL/binário."""
    if raw[:4] == b"%PDF":
        return raw, "application/pdf", "pdf"
    if raw[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
            names = z.namelist()
            if names:
                data = z.read(names[0])
                if data[:4] == b"%PDF":
                    return data, "application/pdf", "pdf"
                return data, "application/octet-stream", "zpl"
        except zipfile.BadZipFile:
            pass
    return raw, "application/octet-stream", "zpl"


@router.post("/orders/{order_id}/ship")
async def ship(
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Despacha o pedido Shopee (rede própria). Gate: NF-e validada. Reentrante (409 se já expedido)."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    if order.shipment_status in _SHIPPED_STATES:
        raise HTTPException(status_code=409, detail="Pedido já despachado")
    await _ensure_invoice_validated(order, token, account.shop_id, db)

    param = await shopee_service.get_shipping_parameter(token, account.shop_id, order.platform_order_id)
    try:
        block = shopee_service.build_ship_block(param)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pkg = await _package_number(token, account.shop_id, order.platform_order_id)
    await shopee_service.ship_order(token, account.shop_id, order.platform_order_id,
                                    package_number=pkg, block=block)

    # Status fresco → vocabulário do sistema (não grava cru).
    dets = await shopee_service.get_order_detail(
        token, account.shop_id, [order.platform_order_id], optional_fields="order_status")
    st = shopee_service.map_shopee_shipment_status(dets[0].get("order_status") if dets else None) \
        or "ready_to_ship"
    order.shipment_status = st
    await db.commit()
    return {"order_id": order.id, "shipment_status": st, "shipped": True}


@router.get("/orders/{order_id}/label")
async def label(
    order_id: int,
    refresh: bool = Query(False),
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Etiqueta (PDF) do pedido Shopee. Usa o PONTO ÚNICO `resolve_label_pdf` (create COM
    tracking_number → poll READY → download) pedindo `NORMAL_AIR_WAYBILL` = PDF humano imprimível
    (o THERMAL vem ZPL-em-ZIP). Cache em `private_labels/` (fora de `static/` — PII). Poll curto;
    se ainda gerando devolve 202 (clique de novo)."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    _LABELS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _LABELS_DIR / f"shopee_{order.id}.pdf"

    # Cache válido só se for REALMENTE um PDF (magic %PDF). O mesmo caminho é compartilhado com o
    # eShip, que grava ZPL/ZIP (THERMAL); servir esse cache como PDF entregaria lixo (CRITICAL
    # apontado na auditoria). Se não começar com %PDF, regera.
    if not refresh and order.label_cached_at and cache_path.exists():
        cached = cache_path.read_bytes()
        if cached[:4] == b"%PDF":
            return Response(cached, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="etiqueta-{order.id}.pdf"'})

    # Pede NORMAL_AIR_WAYBILL (PDF onde o canal oferecer); canais só-ZPL (Shopee Xpress BR)
    # devolvem ZPL mesmo assim — tratado em _normalize_label.
    raw = await shopee_service.resolve_label_pdf(
        token, account.shop_id, order.platform_order_id,
        doc_type="NORMAL_AIR_WAYBILL", tries=_DOC_POLL_TRIES, delay=_DOC_POLL_DELAY,
    )
    if raw is None:
        return Response(status_code=202,
                        content='{"status":"processing","detail":"Etiqueta ainda em geração — clique novamente em instantes."}',
                        media_type="application/json")
    data, media, ext = _normalize_label(raw)
    if media == "application/pdf":
        cache_path.write_bytes(data)  # só cacheia PDF (o .pdf do cache; ZPL serve direto)
        order.label_cached_at = datetime.now(UTC)
        await db.commit()
        disp = f'inline; filename="etiqueta-{order.id}.pdf"'
    else:
        disp = f'attachment; filename="etiqueta-{order.id}.{ext}"'  # ZPL térmico → download
    return Response(data, media_type=media, headers={"Content-Disposition": disp})


@router.get("/orders/{order_id}/fees")
async def fees(
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Custos Shopee do pedido (escrow): comissão + taxas + FRETE. Grava platform_fee +
    buyer_shipping_paid + seller_shipping_cost (mesmo helper do sync automático — sem divergência)."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    income = await shopee_service.get_escrow_detail(token, account.shop_id, order.platform_order_id)
    fee = shopee_service.seller_platform_fee(income)
    if shopee_service.apply_escrow_to_order(order, income):
        await db.commit()
    return {
        "order_id": order.id,
        "platform_fee": fee,
        "buyer_shipping_paid": order.buyer_shipping_paid,
        "seller_shipping_cost": order.seller_shipping_cost,
        "commission_fee": income.get("commission_fee"),
        "service_fee": income.get("service_fee"),
        "seller_transaction_fee": income.get("seller_transaction_fee"),
        "escrow_amount": income.get("escrow_amount"),          # líquido do vendedor
        "buyer_total_amount": income.get("buyer_total_amount"),  # o que o comprador pagou
        "order_selling_price": income.get("order_selling_price"),
    }


@router.get("/orders/{order_id}/tracking")
async def tracking(
    order_id: int,
    current_user: User = Depends(require_menu_permission("separacao")),
    db: AsyncSession = Depends(get_db),
):
    """Rastreio do pedido Shopee: código + histórico. Atualiza tracking_code/shipment_status."""
    order, account, token = await _shopee_order(order_id, current_user, db)
    osn = order.platform_order_id
    tn = await shopee_service.get_tracking_number(token, account.shop_id, osn)
    info = await shopee_service.get_tracking_info(token, account.shop_id, osn)

    code = tn.get("tracking_number") or tn.get("last_mile_tracking_number")
    changed = False
    if code and code != order.tracking_code:
        order.tracking_code = code
        changed = True
    st = shopee_service.map_shopee_shipment_status(info.get("logistics_status"))
    if st and st != order.shipment_status:
        order.shipment_status = st
        changed = True
    if changed:
        await db.commit()
    return {
        "order_id": order.id,
        "tracking_code": order.tracking_code,
        "logistics_status": info.get("logistics_status"),
        "shipment_status": order.shipment_status,
        "historico": info.get("tracking_info") or [],
    }

import json
import time as time_module
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete, or_
from sqlalchemy.orm import selectinload
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from database import get_db
from dependencies import get_current_user, get_active_ac
from models.user import User
from models.order import Order, OrderItem
from models.webhook import WebhookEvent
from models.integration import MarketplaceAccount
from models.product import (
    CatalogProductImage,
    DropshipperProduct,
    DropshipperProductImage,
    ProductListing,
)
from services.financial_service import debit_balance
from services.notification_service import create_notification
from services import ml_service as _ml
from config import get_settings

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


def _serialize_order_list(
    o: Order,
    images_by_catalog: dict,
    dp_map: dict,
    listing_map: dict,
    dp_images: dict,
    sku_listing_map: dict,
    ml_item_listing_map: dict,
    cmig_map: dict | None = None,
) -> dict:
    items = []
    for i in o.items:
        dp = dp_map.get(i.dropshipper_product_id) if i.dropshipper_product_id else None
        listing = listing_map.get(i.dropshipper_product_id) if i.dropshipper_product_id else None

        # SKU-based fallback when no DropshipperProduct is linked
        if not listing and i.sku:
            listing = sku_listing_map.get((o.account_id, i.sku))

        # ML item ID fallback — covers items with empty seller_sku
        if not listing and getattr(i, 'ml_item_id', None):
            listing = ml_item_listing_map.get((o.account_id, i.ml_item_id))

        # Thumbnail priority: stored thumbnail_url > listing thumbnail > dp image > catalog image
        thumbnail = (
            (i.thumbnail_url or None)
            or (listing.thumbnail if listing and listing.thumbnail else None)
            or dp_images.get(i.dropshipper_product_id)
            or (images_by_catalog.get(i.catalog_product_id) if i.catalog_product_id else None)
            or (images_by_catalog.get(listing.catalog_product_id) if listing and listing.catalog_product_id else None)
        )

        # Listing type: gold_special / gold_pro = Premium, rest = Clássico
        listing_type = None
        if listing and listing.listing_type:
            listing_type = listing.listing_type
        elif dp and dp.ml_listing_type:
            listing_type = dp.ml_listing_type

        # FULL: shipping_method (logistic_type) is authoritative for new orders;
        # listing.is_full is used as fallback for old orders where shipping_method was not stored
        is_full = (
            "fulfillment" in (o.shipping_method or "")
            or (bool(listing.is_full) if listing is not None and not o.shipping_method else False)
        )

        items.append({
            "id": i.id,
            "sku": i.sku,
            "title": i.title,
            "quantity": i.quantity,
            "unit_price": float(i.unit_price) if i.unit_price else None,
            "image_url": thumbnail,
            "ml_item_id": (dp.ml_item_id if dp else None) or getattr(i, 'ml_item_id', None),
            "platform_item_id": listing.platform_item_id if listing else None,
            "permalink": listing.permalink if listing else None,
            "listing_type": listing_type,
            "is_full": is_full,
            "catalog_listing": bool(listing.catalog_listing) if listing else False,
            "free_shipping": bool(listing.free_shipping) if listing else False,
            "available_quantity": listing.available_quantity if listing else None,
        })

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
    ml_fee_pct = float(o.ml_fee_pct) if o.ml_fee_pct is not None else (
        round(ml_fee / sale * 100, 2) if (sale and sale > 0 and ml_fee is not None) else None
    )
    product_cost = float(o.product_cost) if o.product_cost is not None else None

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

    return {
        "id": o.id,
        "cmig_id": o.cmig_id,
        "cmig": cmig_info,
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
        "shipment_status": o.shipment_status,
        "tracking_code": o.tracking_code,
        "tracking_url": o.tracking_url,
        "label_url": o.label_url,
        "label_cached_at": o.label_cached_at.isoformat() if o.label_cached_at else None,
        "nfe_url": _ml_nfe_url(o),
        "nfe_key": o.nfe_key,
        "nfe_status": o.nfe_status,
        "shipment_id": o.shipment_id,
        "estimated_delivery_date": o.estimated_delivery_date.isoformat() if o.estimated_delivery_date else None,
        "estimated_handling_limit": o.estimated_handling_limit.isoformat() if o.estimated_handling_limit else None,
        "estimated_delivery_final": o.estimated_delivery_final.isoformat() if o.estimated_delivery_final else None,
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
        result = await db.execute(select(CMIG).where(CMIG.is_active == True).order_by(CMIG.trade_name))
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
            select(CMIG)
            .where(CMIG.id.in_(subq), CMIG.is_active == True)
            .order_by(CMIG.trade_name)
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
    tag: str = None,
    search: str = None,
    cmig_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.cmig import CMIG, CMIGAdministrator

    query = select(Order).where(Order.is_hidden == False)

    # Role-based access control on CMIG
    if current_user.role == "ac":
        # AC só vê pedidos próprios
        query = query.where(Order.dropshipper_id == current_user.id)
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
                select(CMIG).where(CMIG.id == cmig_id, CMIG.warehouse_id == current_user.warehouse_id)
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
    if tag:
        query = query.where(Order.order_tags.ilike(f"%{tag}%"))
    if search:
        query = query.where(Order.buyer_name.ilike(f"%{search}%"))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()

    query = (
        query
        .options(selectinload(Order.items))
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
    orphan_skus = {
        i.sku for o in orders for i in o.items
        if i.sku and not i.dropshipper_product_id
    }
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
        i.ml_item_id for o in orders for i in o.items
        if getattr(i, 'ml_item_id', None) and not i.dropshipper_product_id
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
            cmig_map[c.id] = {"id": c.id, "trade_name": c.trade_name, "company_name": c.company_name, "cnpj": c.cnpj}

    return {
        "items": [
            _serialize_order_list(o, images_by_catalog, dp_map, listing_map, dp_images, sku_listing_map, ml_item_listing_map, cmig_map)
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
        query = query.where(Order.dropshipper_id == current_user.id)

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
        "tracking_code": order.tracking_code,
        "tracking_url": order.tracking_url,
        "label_url": order.label_url,
        "nfe_url": _ml_nfe_url(order),
        "nfe_key": order.nfe_key,
        "nfe_status": order.nfe_status,
        "estimated_delivery_date": order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None,
        "sale_amount": float(order.sale_amount) if order.sale_amount else None,
        "product_cost": float(order.product_cost) if order.product_cost else None,
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
            }
            for i in items
        ],
    }


@router.post("/{order_id}/pay")
async def pay_order(
    order_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.dropshipper_id == current_user.id)
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
    product_cost = sum(
        (i.unit_cost or Decimal("0")) * i.quantity for i in items
    )
    platform_fee = Decimal(str(settings.PLATFORM_FEE))
    shipping_cost = Decimal(str(order.shipping_cost or 0))
    total_debit = product_cost + platform_fee + shipping_cost

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
    order.paid_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "message": "Pedido pago com sucesso",
        "total_debit": float(total_debit),
        "new_status": order.status,
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
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {valid_statuses}")

    query = select(Order).where(Order.id == order_id)
    if current_user.role in ("ac",):
        query = query.where(Order.dropshipper_id == current_user.id)

    result = await db.execute(query)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    order.status = new_status
    if new_status == "shipped":
        order.shipped_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": order.status}


@router.put("/{order_id}/notes")
async def update_order_notes(
    order_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.id == order_id)
    if current_user.role in ("ac",):
        query = query.where(Order.dropshipper_id == current_user.id)

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
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.dropshipper_id == current_user.id)
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
        query = query.where(Order.dropshipper_id == current_user.id)
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
        faturador_id if faturador_id and faturador_id.isdigit()
        else attrs.get("danfe_location")
        or invoice.get("pdf_url") or invoice.get("cdg_post") or invoice.get("url")
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
        raise HTTPException(status_code=400, detail="Emissão via Faturador ML disponível apenas para pedidos do Mercado Livre")
    if order.nfe_status in ("authorized", "pending", "in_process"):
        raise HTTPException(status_code=400, detail=f"NF-e já em processamento (status: {order.nfe_status})")

    acc_result = await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
    )
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")

    try:
        ml_order_id = int(order.platform_order_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ID do pedido inválido para emissão de NF-e")

    await _ml.emit_nfe(account.access_token, account.platform_user_id, [ml_order_id])

    # Mark as pending immediately so re-clicks are blocked even if fiscal fetch fails
    order.nfe_status = "pending"
    await db.commit()

    # Fetch updated fiscal data — best-effort, failure leaves status as "pending"
    try:
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
        pass  # User can sync manually

    return {
        "ok": True,
        "nfe_status": order.nfe_status,
        "nfe_key": order.nfe_key,
        "nfe_url": _ml_nfe_url(order),
    }


@router.post("/{order_id}/sync-nfe")
async def sync_order_nfe(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pull fresh NF-e data from ML for one order and update local record."""
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        return {"ok": True, "nfe_status": order.nfe_status, "nfe_key": order.nfe_key, "nfe_url": order.nfe_url}

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
    "pending":       "Aguardando",
    "handling":      "Em Preparação",
    "ready_to_ship": "Pronto para Envio",
    "shipped":       "Despachado",
    "delivered":     "Entregue",
    "not_delivered": "Não Entregue",
    "cancelled":     "Cancelado",
    "returned":      "Devolvido",
}

_SHIPMENT_SUBSTATUS_PT = {
    # pending
    "shipment_paid":          "Pagamento Confirmado",
    "buffered":               "Em Espera",
    "waiting_for_collection": "Aguardando Coleta",
    # handling
    "regenerating":           "Regerando Etiqueta",
    "stale":                  "Pendente Há Muito Tempo",
    "contact_with_carrier_needed": "Contato com Transportadora Necessário",
    # ready_to_ship
    "ready_to_print":         "Pronto para Imprimir",
    "ready_to_pack":          "Pronto para Embalar",
    "printed":                "Etiqueta Impressa",
    "packed":                 "Embalado",
    "in_packing_list":        "Na Lista de Embalagem",
    "ready_for_pickup":       "Pronto para Retirada",
    "in_hub":                 "No Centro de Distribuição",
    "invoice_pending":        "Aguardando NF-e",
    # shipped
    "first_visit":            "1ª Tentativa de Entrega",
    "in_transit":             "Em Trânsito",
    "in_transfer":            "Em Transferência",
    "out_for_delivery":       "Saiu para Entrega",
    "arrived":                "Chegou no Destino",
    "soon_deliver":           "Entrega em Breve",
    "delayed":                "Atrasado",
    "second_visit":           "2ª Tentativa de Entrega",
    "third_visit":            "3ª Tentativa de Entrega",
    "not_visited":            "Não Visitado",
    "waiting_for_withdrawal": "Aguardando Retirada",
    "receiver_absent":        "Destinatário Ausente",
    "bad_address":            "Endereço Incorreto",
    "could_not_be_delivered": "Não Pôde Ser Entregue",
    "retained":               "Retido",
    "claimed_me":             "Reclamação Aberta",
    "to_review":              "Em Revisão",
    "stolen":                 "Roubado/Furtado",
    "lost":                   "Extraviado",
    "damaged":                "Danificado",
    "forwarded_to_third":     "Encaminhado a Terceiro",
    "returning_to_sender":    "Retornando ao Remetente",
    "returned_to_origin":     "Devolvido à Origem",
    # delivered
    "delivered":              "Entregue",
    # not_delivered
    "not_localized":          "Não Localizado",
    "not_dispatched":         "Não Despachado",
    "rejected_damaged":       "Rejeitado por Avaria",
    "rejected_other":         "Rejeitado",
    "returned":               "Devolvido",
    "destroyed":              "Destruído",
    "fraud":                  "Fraude Detectada",
    "confiscated":            "Confiscado",
    # cancelled
    "buyer_cancelled":        "Cancelado pelo Comprador",
    "seller_cancelled":       "Cancelado pelo Vendedor",
    "system_cancelled":       "Cancelado pelo Sistema",
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
            events.append({
                "date": value,
                "label": meta["label"],
                "icon": meta["icon"],
                "code": key,
            })
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
        events.append({
            "date": date,
            "label": _translate_shipment_event(status, substatus),
            "icon": "fa-circle",
            "code": f"hist_{status}_{substatus}",
        })
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
        shipment = await _ml.get_shipment(account.access_token, order.shipment_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao buscar envio no ML: {e}")

    if not shipment:
        return {"ok": False, "detail": "Envio não encontrado no Mercado Livre."}

    # Fetch history and carrier in parallel-ish (sequential is fine for 2 calls)
    try:
        history = await _ml.get_shipment_history(account.access_token, order.shipment_id)
    except Exception:
        history = {}
    try:
        carrier = await _ml.get_shipment_carrier(account.access_token, order.shipment_id)
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
            "delivery_time": _date_or_str(ship_opt.get("estimated_delivery_time")) or _date_or_str(shipment.get("estimated_delivery_time")),
            "delivery_limit": _date_or_str(ship_opt.get("estimated_delivery_limit")),
            "delivery_extended": _date_or_str(ship_opt.get("estimated_delivery_extended")),
            "delivery_final": _date_or_str(ship_opt.get("estimated_delivery_final")),
        },
        "timeline": _build_shipment_timeline(shipment, history),
    }


async def _delete_order(db: AsyncSession, order: Order):
    """Delete an order and its items, and clear WebhookEvents so it can be re-downloaded."""
    # Clear WebhookEvents for this order so the next sync re-downloads it
    await db.execute(
        sa_delete(WebhookEvent).where(
            WebhookEvent.platform == order.platform,
            WebhookEvent.event_id.like(f"%:{order.platform_order_id}"),
        )
    )
    db.delete(order)
    await db.commit()


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.id == order_id)
    if current_user.role == "ac":
        query = query.where(Order.dropshipper_id == current_user.id)
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
        query = query.where(Order.dropshipper_id == current_user.id)

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
                local = local.replace(tzinfo=timezone.utc)
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
                    order.paid_at = datetime.fromisoformat(str(date_approved).replace("Z", "+00:00"))
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
                (Order.shipment_id != None) & or_(
                    Order.shipment_status == None,
                    Order.shipment_status.in_(["pending", "handling", "ready_to_ship", "shipped"]),
                    Order.shipment_status.in_(["delivered", "not_delivered", "cancelled"]) & (
                        (Order.estimated_delivery_date == None)
                        | (Order.estimated_delivery_final == None)
                    ),
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

            sd = await _ml.get_shipment(account.access_token, str(shipment_id))
            if not sd:
                continue
            costs = {}
            try:
                costs = await _ml.get_shipment_costs(account.access_token, str(shipment_id))
            except Exception:
                pass
            _apply_shipment_to_order(order, sd, costs)
            updated += 1
        except Exception:
            pass
        await _asyncio.sleep(0.1)

    if updated:
        await db.commit()
    return updated


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
        dq = dq.where(Order.dropshipper_id == current_user.id)

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


@router.post("/sync")
async def trigger_sync(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate sync for the current user's marketplace accounts (last 60 min) and check pending NF-e."""
    import asyncio
    from tasks.sync_orders import sync_ml_integration, sync_shopee_integration

    date_from = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
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
    for account in ml_accounts:
        imported += await sync_ml_integration(db, account, date_from)
    for account in shopee_result.scalars().all():
        imported += await sync_shopee_integration(db, account, now_ts - 3600, now_ts)

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
            q = q.where(Order.dropshipper_id == current_user.id)

        nfe_result = await db.execute(q)
        orders_to_check = nfe_result.scalars().all()

        for order in orders_to_check:
            account = accounts_map.get(order.account_id)
            if not account or not account.access_token:
                continue

            if not order.shipment_id:
                try:
                    ml_order_data = await _ml.get_order(account.access_token, order.platform_order_id)
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

    dates_fixed = await _backfill_order_dates(db, ml_accounts, current_user)

    return {"ok": True, "imported": imported, "nfe_updated": nfe_updated, "ship_updated": ship_updated, "dates_fixed": dates_fixed}


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
            dt_from = dt_from.replace(tzinfo=timezone.utc)
        date_from_iso = dt_from.isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from inválido — use formato YYYY-MM-DD")

    date_to_iso: str | None = None
    ts_to = int(time_module.time())
    if date_to_str:
        try:
            dt_to = datetime.fromisoformat(date_to_str)
            if dt_to.tzinfo is None:
                # date_to is end-of-day
                dt_to = dt_to.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
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

    # Targeted backfill: fix dates for all ML orders found in this range
    dates_fixed = await _backfill_order_dates(db, ml_accounts, current_user, platform_order_ids=ml_order_ids or None)

    # Also refresh shipment status/dates for orders missing it
    ship_updated = await _refresh_shipments(
        db,
        ml_accounts,
        dropshipper_id=current_user.id if current_user.role == "ac" else None,
        limit=100,
    )

    return {
        "ok": True,
        "imported": imported,
        "dates_fixed": dates_fixed,
        "ship_updated": ship_updated,
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
        q = q.where(Order.dropshipper_id == current_user.id)

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
        "transaction_type_label": _INVOICE_TYPE_LABELS.get(t_type, t_type.replace("_", " ").title()),
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

    invoices = []
    main = await _ml.get_invoices_by_order(
        account.access_token, account.platform_user_id, order.platform_order_id
    )
    if main:
        invoices.append(_serialize_invoice(main))
        # Collect any reference invoices (Fulfillment chain)
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

    return {"invoices": invoices}


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
        headers={"Content-Disposition": f'attachment; filename="NFe_{invoice_id}.xml"'},
    )


_LABELS_DIR = Path(__file__).resolve().parent.parent / "static" / "labels"


@router.get("/{order_id}/label")
async def get_order_shipping_label(
    order_id: int,
    fmt: str = Query("pdf", regex="^(pdf|zpl2)$"),
    refresh: bool = Query(False, description="Força re-download do ML mesmo se já houver cache"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and return the official ML shipping label.

    Strategy:
    - First request: fetch from ML, save to disk, mark label_cached_at, return.
    - Subsequent requests: serve from disk (always available, even when ML rate-limits or token expires).
    - Pass ?refresh=true to force re-download.

    PDF includes: shipping label + content declaration + product identification.
    """
    order = await _get_order_checked(db, order_id, current_user)
    if order.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Etiqueta disponível apenas para pedidos do Mercado Livre")
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
    media_type = "text/plain" if fmt == "zpl2" else "application/pdf"
    filename = f"etiqueta_{order.platform_order_id}_{order.shipment_id}.{ext}"
    cache_path = _LABELS_DIR / f"{order.shipment_id}.{ext}"

    # Try cache first (unless forced refresh)
    if not refresh and cache_path.exists() and order.label_cached_at:
        content = cache_path.read_bytes()
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    # Cache miss or forced refresh — fetch from ML
    if order.shipment_status in ("pending", None, ""):
        raise HTTPException(
            status_code=400,
            detail="Envio ainda não está pronto — aguarde o pagamento ser aprovado e o ML preparar a etiqueta",
        )

    account = await _get_account_for_order(db, order)
    if not account.access_token:
        raise HTTPException(status_code=400, detail="Conta sem token válido")

    content, ctype = await _ml.get_shipment_label(account.access_token, order.shipment_id, fmt)

    # Persist to disk + mark cached_at
    try:
        _LABELS_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        order.label_cached_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as e:
        print(f"[orders] failed to cache label shipment={order.shipment_id}: {e}")

    return Response(
        content=content,
        media_type=ctype,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
        headers={"Content-Disposition": f'inline; filename="DANFE_{invoice_id}.pdf"'},
    )

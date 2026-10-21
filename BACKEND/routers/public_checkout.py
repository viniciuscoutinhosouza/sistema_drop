"""Checkout PÚBLICO da venda manual (Fase 3, ADR-0033) — SEM JWT.

Acesso só pelo token opaco do próprio pedido (`orders.public_token`). O cliente vê o pedido,
ajusta a quantidade de itens já existentes (0 = remover) e paga via ASAAS (reusa o ponto único
`charge_service`). Mexer num item com desconto (`unit_price < list_price`) marca
`needs_price_review` e BLOQUEIA o pagamento até o operador re-analisar o preço — "falhar alto".

Superfície mínima e escopada ao token: não expõe catálogo, não deixa adicionar produto novo,
não revela dados de outros pedidos nem o CPF completo do comprador.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.cmig import CMIGProductImage
from models.order import Order, OrderItem
from models.product import CatalogProductImage

router = APIRouter()

# Teto de quantidade — evita estourar NUMBER(15,2) do total (500 num endpoint público).
MAX_ITEM_QTY = 100000


def _mask_name(name: str | None) -> str:
    """Primeiro nome + inicial do sobrenome (não vaza o nome completo numa URL pública)."""
    parts = (name or "").strip().split()
    if not parts:
        return "Cliente"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def _item_view(it: OrderItem, images: dict[int, str] | None = None) -> dict:
    unit = Decimal(str(it.unit_price or 0))
    lst = Decimal(str(it.list_price)) if it.list_price is not None else None
    return {
        "id": it.id,
        "title": it.title,
        "sku": it.sku,
        "quantity": it.quantity,
        "unit_price": float(unit),
        "list_price": float(lst) if lst is not None else None,
        "has_discount": bool(lst is not None and unit < lst),
        "line_total": float(unit * (it.quantity or 0)),
        # Foto do produto (página do cliente): CMIG via cmig_product_images, PG via
        # catalog_product_images — primária primeiro. None se o produto não tem imagem.
        "image_url": (images or {}).get(it.id),
    }


async def _resolve_item_images(db: AsyncSession, order: Order) -> dict[int, str]:
    """`{order_item_id: url da imagem principal}`. Resolve por `catalog_source`: item CMIG usa a
    imagem do CMIGProduct; item PG usa a do CatalogProduct. Primária (is_primary) → menor sort_order.
    Imagem de produto não é dado sensível — ok expor na página pública."""
    cmig_ids = {i.cmig_product_id for i in order.items if i.catalog_source == "cmig" and i.cmig_product_id}
    pg_ids = {i.catalog_product_id for i in order.items if i.catalog_source != "cmig" and i.catalog_product_id}
    cmig_img: dict[int, str] = {}
    pg_img: dict[int, str] = {}
    if cmig_ids:
        rows = (await db.execute(
            select(CMIGProductImage)
            .where(CMIGProductImage.cmig_product_id.in_(cmig_ids))
            .order_by(CMIGProductImage.is_primary.desc(), CMIGProductImage.sort_order)
        )).scalars().all()
        for r in rows:
            cmig_img.setdefault(r.cmig_product_id, r.url)
    if pg_ids:
        rows = (await db.execute(
            select(CatalogProductImage)
            .where(CatalogProductImage.product_id.in_(pg_ids))
            .order_by(CatalogProductImage.is_primary.desc(), CatalogProductImage.sort_order)
        )).scalars().all()
        for r in rows:
            pg_img.setdefault(r.product_id, r.url)
    out: dict[int, str] = {}
    for i in order.items:
        if i.catalog_source == "cmig" and i.cmig_product_id in cmig_img:
            out[i.id] = cmig_img[i.cmig_product_id]
        elif i.catalog_product_id in pg_img:
            out[i.id] = pg_img[i.catalog_product_id]
    return out


async def _live_charge_view(db: AsyncSession, order: Order) -> dict | None:
    from services import charge_service

    c = await charge_service.get_live_charge(db, order.id)
    if not c:
        return None
    return {
        "status": c.status,
        "billing_type": c.billing_type,
        "value": float(c.value or 0),
        "invoice_url": c.invoice_url,
        "bank_slip_url": c.bank_slip_url,
        "pix_payload": c.pix_payload,
    }


def _serialize_public(order: Order, charge: dict | None, images: dict[int, str] | None = None) -> dict:
    from services import charge_service

    items = sorted(order.items, key=lambda x: x.id)
    shipping = float(order.shipping_cost or 0)
    items_total = sum(float(Decimal(str(i.unit_price or 0)) * (i.quantity or 0)) for i in items)
    charge_paid = bool(charge and (charge.get("status") or "").upper() in charge_service.PAID_CHARGE)
    return {
        "buyer_name": _mask_name(order.buyer_name),
        "items": [_item_view(i, images) for i in items],
        "items_total": round(items_total, 2),
        "shipping_cost": shipping,
        "total": round(items_total + shipping, 2),
        "payment_status": order.payment_status,
        "needs_price_review": bool(order.needs_price_review),
        "editable": order.payment_status != "paid" and not charge_paid,
        "charge": charge,
    }


async def _load_by_token(token: str, db: AsyncSession) -> Order:
    # Token opaco de alta entropia; rejeita formatos óbvios curtos sem tocar o banco.
    if not token or len(token) < 20:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    order = (
        await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.public_token == token, Order.platform == "manual")
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    return order


def _recompute_totals(order: Order) -> None:
    sale = Decimal("0")
    cost = Decimal("0")
    for it in order.items:
        sale += Decimal(str(it.unit_price or 0)) * (it.quantity or 0)
        cost += Decimal(str(it.unit_cost or 0)) * (it.quantity or 0)
    order.sale_amount = sale
    order.product_cost = cost


@router.get("/checkout/{token}")
async def public_get_checkout(token: str, db: AsyncSession = Depends(get_db)):
    order = await _load_by_token(token, db)
    return _serialize_public(
        order, await _live_charge_view(db, order), await _resolve_item_images(db, order)
    )


@router.patch("/checkout/{token}/items/{item_id}")
async def public_edit_item(
    token: str, item_id: int, body: dict, db: AsyncSession = Depends(get_db)
):
    """Cliente ajusta a quantidade de um item existente (0 = remover). Só itens já no pedido."""
    from services import charge_service

    order = await _load_by_token(token, db)
    if order.payment_status == "paid":
        raise HTTPException(status_code=409, detail="Pedido ja pago - nao pode ser alterado")
    live = await charge_service.get_live_charge(db, order.id)
    if live and (live.status or "").upper() in charge_service.PAID_CHARGE:
        raise HTTPException(status_code=409, detail="Pagamento ja confirmado - nao pode ser alterado")

    item = next((i for i in order.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado neste pedido")

    try:
        new_qty = int(body.get("quantity"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="quantidade invalida") from None
    if new_qty < 0 or new_qty > MAX_ITEM_QTY:
        raise HTTPException(status_code=400, detail="quantidade invalida")

    had_discount = item.list_price is not None and Decimal(str(item.unit_price or 0)) < Decimal(
        str(item.list_price)
    )
    changed = new_qty != (item.quantity or 0)

    if new_qty == 0:
        if len([i for i in order.items if i.id != item_id]) == 0:
            raise HTTPException(status_code=400, detail="O pedido precisa ter ao menos um item")
        order.items.remove(item)
        db.delete(item)
    else:
        item.quantity = new_qty

    # Re-análise de desconto: mexeu em item com desconto → operador precisa reavaliar o preço
    # antes de liberar o pagamento (ADR-0033). Item sem desconto apenas recalcula o total.
    if changed and had_discount:
        order.needs_price_review = True

    _recompute_totals(order)
    await db.commit()
    # Cobrança viva com valor agora divergente não pode continuar pagável (ADR-0033): cancela,
    # para o cliente cair no botão "Pagar" e gerar uma cobrança com o novo total.
    await charge_service.cancel_live_stale_charge(db, order)
    # Recarrega (expire_on_commit=True zera os atributos pós-commit; evita lazy-load async).
    fresh = await _load_by_token(token, db)
    return _serialize_public(
        fresh, await _live_charge_view(db, fresh), await _resolve_item_images(db, fresh)
    )


@router.post("/checkout/{token}/pay")
async def public_pay(token: str, body: dict | None = None, db: AsyncSession = Depends(get_db)):
    """Gera (ou reusa) a cobrança ASAAS do pedido. Bloqueia se aguarda re-análise de preço."""
    from services import charge_service

    body = body or {}
    order = await _load_by_token(token, db)
    if order.payment_status == "paid":
        raise HTTPException(status_code=409, detail="Pedido ja esta pago")
    if order.needs_price_review:
        raise HTTPException(
            status_code=409,
            detail="O vendedor precisa revisar o preco apos a alteracao dos itens. "
            "Tente novamente em instantes.",
        )
    await charge_service.get_or_create_charge(
        db, order, billing_type=body.get("billing_type") or "UNDEFINED"
    )
    # Recarrega (get_or_create commita; expire_on_commit=True zera os atributos → evita lazy-load async).
    fresh = await _load_by_token(token, db)
    return _serialize_public(
        fresh, await _live_charge_view(db, fresh), await _resolve_item_images(db, fresh)
    )

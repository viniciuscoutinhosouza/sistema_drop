"""Montagem de metadados de etiqueta (SKU/EAN/título) por pedido.

Fonte ÚNICA compartilhada entre a Separação e o endpoint de etiqueta de Pedidos. Resolve o
produto base de cada OrderItem mesmo quando o item vincula só pelo anúncio (via
`resolve_order_item_link`) — sem isso, pedidos ML por-anúncio sairiam com EAN/nome vazios.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG, CMIGProduct
from models.order import Order, OrderItem
from models.product import CatalogProduct
from services.order_item_resolver import resolve_order_item_link


def _base_from_cmig(cp: CMIGProduct, item: OrderItem) -> dict:
    return {
        "kind": "cmig", "product_id": cp.id, "sku": cp.sku_cmig or item.sku,
        "ean": cp.ean or "", "title": cp.title or item.title,
        "is_composite": bool(cp.is_composite),
    }


def _base_from_pg(pg: CatalogProduct, item: OrderItem) -> dict:
    return {
        "kind": "pg", "product_id": pg.id, "sku": pg.sku or item.sku,
        "ean": pg.ean or "", "title": pg.title or item.title,
        "is_composite": bool(pg.is_composite),
    }


async def resolve_item_base(db: AsyncSession, item: OrderItem, order: Order | None = None) -> dict:
    """Resolve o produto base de um OrderItem (PG ou CMIG).

    1) Vínculo direto no item (cmig_product_id / catalog_product_id).
    2) Fallback canônico via ProductListing/DP/SKU (resolve_order_item_link) usando
       o contexto do pedido — cobre pedidos ML vinculados só pelo anúncio.
    """
    if item.cmig_product_id:
        cp = (
            await db.execute(select(CMIGProduct).where(CMIGProduct.id == item.cmig_product_id))
        ).scalar_one_or_none()
        if cp:
            return _base_from_cmig(cp, item)
    if item.catalog_product_id:
        pg = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.id == item.catalog_product_id))
        ).scalar_one_or_none()
        if pg:
            return _base_from_pg(pg, item)

    if order is not None:
        link = await resolve_order_item_link(
            db,
            account_id=order.account_id,
            ml_item_id=getattr(item, "ml_item_id", None),
            cmig_id=order.cmig_id,
            sku=item.sku,
            dropshipper_id=order.dropshipper_id,
        )
        if link.cmig_product:
            return _base_from_cmig(link.cmig_product, item)
        if link.catalog_product:
            return _base_from_pg(link.catalog_product, item)

    return {
        "kind": None, "product_id": None, "sku": item.sku or "",
        "ean": "", "title": item.title or "", "is_composite": False,
    }


async def build_orders_label_meta(db: AsyncSession, orders: list[Order]) -> list[dict]:
    """Monta orders_meta p/ render_shipping_labels[_zpl] (1 volume por OrderItem)."""
    out: list[dict] = []
    for order in orders:
        items = (
            await db.execute(
                select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
            )
        ).scalars().all()
        cmig = None
        if order.cmig_id:
            cmig = (
                await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
            ).scalar_one_or_none()
        metas = []
        for it in items:
            base = await resolve_item_base(db, it, order)
            metas.append({"ean": base.get("ean") or "", "title": base.get("title") or it.title})
        out.append({"order": order, "items": items, "cmig": cmig, "items_meta": metas})
    return out

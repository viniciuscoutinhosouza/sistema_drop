"""Reconstrução de histórico de movimentação de estoque.

Agrega itens de NFe (entrada/saída) e pedidos de marketplace
(`shipment_status IN ('shipped','delivered')`) e computa o split de cada
pedido entre estoque CMIG e estoque PG conforme a regra:

- Se o CMIGProduct tem `pg_product_id` (vínculo com PG):
  pedido debita CMIG enquanto `projected_cmig > 0`; overflow vai pra PG.
- Se não há vínculo PG: tudo debita CMIG (mesmo negativando).

`CMIGProduct.stock_quantity` e `CatalogProduct.stock_quantity` NÃO são
alterados — esta camada é puramente reporting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG, CMIGProduct
from models.fiscal import Invoice, InvoiceItem
from models.order import Order, OrderItem
from models.person import Person
from models.product import CatalogProduct, ProductListing

RESERVED_STATUSES = ("handling", "ready_to_ship")
DEFINITIVE_STATUSES = ("shipped", "delivered")
SHIPPED_STATUSES = RESERVED_STATUSES + DEFINITIVE_STATUSES  # todos contam pra estoque


@dataclass
class StockEvent:
    """Um evento que afeta (ou poderia afetar) o estoque de um produto."""

    date: datetime
    source: Literal["nfe_in", "nfe_out", "order"]
    direction: Literal["in", "out"]  # pra 'order' sempre 'out'
    qty: int
    qty_to_cmig: int = 0
    qty_to_pg: int = 0

    # metadados — populados conforme o tipo
    invoice_id: Optional[int] = None
    invoice_number: Optional[int] = None
    invoice_serie: Optional[int] = None
    invoice_status: Optional[str] = None
    order_id: Optional[int] = None
    order_platform: Optional[str] = None
    order_platform_id: Optional[str] = None
    order_shipment_status: Optional[str] = None
    order_has_invoice: bool = False
    order_invoice_finalized: bool = False
    # Classificação semântica (apenas para source='order')
    is_reserved: bool = False     # handling | ready_to_ship
    is_definitive: bool = False   # shipped  | delivered
    person_name: Optional[str] = None
    item_description: Optional[str] = None
    item_sku: Optional[str] = None
    item_ean: Optional[str] = None
    item_ml_item_id: Optional[str] = None  # ID do anúncio no marketplace (MLB...)
    cmig_product_id: Optional[int] = None
    cmig_product_sku: Optional[str] = None
    cmig_product_title: Optional[str] = None
    cmig_id: Optional[int] = None
    cmig_name: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if hasattr(self.date, "isoformat") else self.date
        return d


async def _fetch_nfe_events_for_cmig_product(
    cmig_product: CMIGProduct, db: AsyncSession
) -> list[StockEvent]:
    """NFes finalizadas/autorizadas tocando este CMIGProduct."""
    product_ean = (cmig_product.ean or "").strip()
    item_match = [InvoiceItem.cmig_product_id == cmig_product.id]
    if product_ean:
        item_match.append(
            and_(InvoiceItem.cmig_product_id.is_(None), InvoiceItem.ean == product_ean)
        )

    stmt = (
        select(InvoiceItem, Invoice, Person.name.label("person_name"))
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .outerjoin(Person, Person.id == Invoice.person_id)
        .where(
            and_(
                Invoice.cmig_id == cmig_product.cmig_id,
                Invoice.stock_updated == True,  # noqa: E712
                Invoice.status.in_(("authorized", "finalized")),
                or_(*item_match),
            )
        )
    )

    rows = (await db.execute(stmt)).all()
    events: list[StockEvent] = []
    for item, inv, person_name in rows:
        m_date = inv.exit_date or inv.issue_date
        if m_date is None:
            continue
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        is_in = inv.direction == "in"
        events.append(
            StockEvent(
                date=m_date,
                source="nfe_in" if is_in else "nfe_out",
                direction="in" if is_in else "out",
                qty=qty,
                qty_to_cmig=qty,
                qty_to_pg=0,
                invoice_id=inv.id,
                invoice_number=inv.nfe_number,
                invoice_serie=inv.serie,
                invoice_status=inv.status,
                person_name=person_name,
                item_description=item.description,
                item_sku=item.sku,
                item_ean=item.ean,
                cmig_product_id=cmig_product.id,
                cmig_product_sku=cmig_product.sku_cmig,
                cmig_product_title=cmig_product.title,
                cmig_id=cmig_product.cmig_id,
            )
        )
    return events


async def _fetch_order_events_for_cmig_product(
    cmig_product: CMIGProduct, db: AsyncSession
) -> list[StockEvent]:
    """Pedidos de marketplace `shipped`/`delivered` que tocam este CMIGProduct.

    Matching em cascata (qualquer um casa):
    1) Via ProductListing.cmig_product_id (pelo ml_item_id + account_id)
    2) Via OrderItem.sku = product.sku_cmig
    3) Via OrderItem.catalog_product_id = product.pg_product_id (se houver vínculo)
    """
    listing_match = exists().where(
        and_(
            ProductListing.platform_item_id == OrderItem.ml_item_id,
            ProductListing.account_id == Order.account_id,
            ProductListing.cmig_product_id == cmig_product.id,
        )
    )
    sku_match = (
        OrderItem.sku == cmig_product.sku_cmig if cmig_product.sku_cmig else None
    )
    pg_match = (
        OrderItem.catalog_product_id == cmig_product.pg_product_id
        if cmig_product.pg_product_id
        else None
    )

    or_clauses = [listing_match]
    if sku_match is not None:
        or_clauses.append(sku_match)
    if pg_match is not None:
        or_clauses.append(pg_match)

    # Carrega a CMIG pra ter o nome
    stmt = (
        select(OrderItem, Order, CMIG.company_name.label("cmig_name"))
        .join(Order, Order.id == OrderItem.order_id)
        .outerjoin(CMIG, CMIG.id == Order.cmig_id)
        .where(
            and_(
                Order.cmig_id == cmig_product.cmig_id,
                Order.shipment_status.in_(SHIPPED_STATUSES),
                or_(*or_clauses),
            )
        )
    )

    rows = (await db.execute(stmt)).all()
    events: list[StockEvent] = []
    for item, order, cmig_name in rows:
        m_date = order.shipped_at or order.created_at
        if m_date is None:
            continue
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        has_invoice = bool(order.invoice_id)
        # `order_invoice_finalized` populado depois por `_resolve_order_invoice_status`.
        shipment_status = order.shipment_status or ""
        events.append(
            StockEvent(
                date=m_date,
                source="order",
                direction="out",
                qty=qty,
                qty_to_cmig=0,  # preenchido no replay
                qty_to_pg=0,    # idem
                order_id=order.id,
                order_platform=order.platform,
                order_platform_id=order.platform_order_id,
                order_shipment_status=shipment_status,
                order_has_invoice=has_invoice,
                order_invoice_finalized=False,
                is_reserved=shipment_status in RESERVED_STATUSES,
                is_definitive=shipment_status in DEFINITIVE_STATUSES,
                person_name=order.buyer_name,
                item_description=item.title,
                item_sku=item.sku,
                item_ml_item_id=item.ml_item_id,
                cmig_product_id=cmig_product.id,
                cmig_product_sku=cmig_product.sku_cmig,
                cmig_product_title=cmig_product.title,
                cmig_id=cmig_product.cmig_id,
                cmig_name=cmig_name,
            )
        )

    return events


async def _resolve_order_invoice_status(
    events: list[StockEvent], db: AsyncSession
) -> None:
    """Para cada evento de pedido com invoice_id, marca se a invoice está finalizada/autorizada.

    Determina se o pedido conta como 'reservado' (não finalizado) ou 'consumado' (NFe pronta).
    """
    order_ids = {e.order_id for e in events if e.source == "order" and e.order_id}
    if not order_ids:
        return
    rows = (
        await db.execute(
            select(Order.id, Invoice.status)
            .join(Invoice, Invoice.id == Order.invoice_id)
            .where(Order.id.in_(order_ids))
        )
    ).all()
    status_by_order: dict[int, str] = {oid: status for oid, status in rows}
    for e in events:
        if e.source == "order" and e.order_id in status_by_order:
            inv_status = status_by_order[e.order_id]
            e.order_has_invoice = True
            e.order_invoice_finalized = inv_status in ("authorized", "finalized")


def _apply_split_replay(
    events: list[StockEvent], cmig_product: CMIGProduct, current_nfe_balance: int
) -> int:
    """Replay cronológico computando qty_to_cmig / qty_to_pg de cada order event.

    Retorna o saldo CMIG-NFe-only no ponto de partida (initial NFe balance =
    `current_nfe_balance` revertendo todas as NFes do `events`).

    Mutates `events` in place: para cada `source == 'order'` setamos qty_to_cmig/qty_to_pg.
    """
    # Calcula o saldo NFe-only no início: parte de current e reverte todas as NFes.
    # (Inverso do que se faria propagando do início para o atual.)
    nfe_only_initial = current_nfe_balance
    for e in events:
        if e.source == "nfe_in":
            nfe_only_initial -= e.qty
        elif e.source == "nfe_out":
            nfe_only_initial += e.qty
    # Agora replay forward — incluindo orders pra ajustar projected_cmig.
    has_pg = cmig_product.pg_product_id is not None
    projected = nfe_only_initial
    for e in events:
        if e.source == "nfe_in":
            projected += e.qty
            e.qty_to_cmig = e.qty
            e.qty_to_pg = 0
        elif e.source == "nfe_out":
            projected -= e.qty
            e.qty_to_cmig = e.qty
            e.qty_to_pg = 0
        elif e.source == "order":
            if not has_pg:
                e.qty_to_cmig = e.qty
                e.qty_to_pg = 0
            else:
                taken = max(0, min(e.qty, projected))
                e.qty_to_cmig = taken
                e.qty_to_pg = e.qty - taken
            projected -= e.qty_to_cmig
    return nfe_only_initial


async def replay_stock_events_for_cmig_product(
    cmig_product: CMIGProduct, db: AsyncSession
) -> tuple[list[StockEvent], int]:
    """Retorna eventos cronologicamente ordenados com split CMIG/PG já computado,
    junto com o saldo NFe-only inicial (antes do primeiro evento).
    """
    nfe_events = await _fetch_nfe_events_for_cmig_product(cmig_product, db)
    order_events = await _fetch_order_events_for_cmig_product(cmig_product, db)
    await _resolve_order_invoice_status(order_events, db)

    events = nfe_events + order_events
    events.sort(key=lambda e: e.date)

    current_nfe_balance = int(cmig_product.stock_quantity or 0)
    nfe_only_initial = _apply_split_replay(events, cmig_product, current_nfe_balance)
    return events, nfe_only_initial


async def replay_stock_events_for_pg_product(
    pg_product: CatalogProduct, db: AsyncSession
) -> tuple[list[StockEvent], list[CMIGProduct]]:
    """Itera CMIGProducts vinculados ao PG, replaya cada um, concatena e ordena.

    O frontend filtra `qty_to_pg > 0` pra mostrar só overflow.
    """
    linked_cmigs = (
        await db.execute(
            select(CMIGProduct).where(CMIGProduct.pg_product_id == pg_product.id)
        )
    ).scalars().all()

    all_events: list[StockEvent] = []
    for cp in linked_cmigs:
        events, _ = await replay_stock_events_for_cmig_product(cp, db)
        all_events.extend(events)

    all_events.sort(key=lambda e: e.date)
    return all_events, list(linked_cmigs)

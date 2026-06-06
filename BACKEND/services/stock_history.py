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

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG, CMIGProduct
from models.fiscal import Invoice, InvoiceItem
from models.order import Order, OrderItem
from models.person import Person
from models.product import CatalogProduct, CatalogProductComponent, ProductListing

RESERVED_STATUSES = ("handling", "ready_to_ship")
DEFINITIVE_STATUSES = ("shipped", "delivered")
SHIPPED_STATUSES = RESERVED_STATUSES + DEFINITIVE_STATUSES  # todos contam pra estoque


def local_order_clause():
    """Predicado: pedido que debita o estoque LOCAL (galpão / PG / CMIG).

    Pedidos FULL (shipping_mode='full') NÃO debitam o galpão — o produto já saiu
    do galpão na NF-e de transferência para o CNPJ FULL (evento nfe_out) e a venda
    é baixada do FullStock por `full_stock_service.apply_full_order_shipped`. Contar
    o pedido FULL aqui causaria DUPLA baixa do galpão.

    NULL / 'desconhecido' são tratados como LOCAL (mantidos), pois só excluímos o
    que sabemos ser FULL. Usado por todas as fontes de evento de pedido que
    alimentam o cálculo canônico de estoque local.
    """
    return func.coalesce(Order.shipping_mode, "") != "full"


@dataclass
class StockEvent:
    """Um evento que afeta (ou poderia afetar) o estoque de um produto."""

    date: datetime
    source: Literal["nfe_in", "nfe_out", "order", "adjustment"]
    direction: Literal["in", "out"]  # pra 'order' sempre 'out'
    qty: int
    qty_to_cmig: int = 0
    qty_to_pg: int = 0

    # metadados — populados conforme o tipo
    item_id: int | None = None  # InvoiceItem.id (pra dedup quando agregamos várias fontes)
    invoice_id: int | None = None
    invoice_number: int | None = None
    invoice_serie: int | None = None
    invoice_status: str | None = None
    # True se essa NFe-out tem Order.invoice_id apontando pra ela.
    # No novo modelo, NFe-out vinculada a pedido NÃO debita estoque
    # (o pedido já contou). Default False = NFe-out autônoma.
    invoice_linked_to_order: bool = False
    order_id: int | None = None
    order_platform: str | None = None
    order_platform_id: str | None = None
    order_shipment_status: str | None = None
    order_has_invoice: bool = False
    order_invoice_finalized: bool = False
    # Classificação semântica (apenas para source='order')
    is_reserved: bool = False     # handling | ready_to_ship
    is_definitive: bool = False   # shipped  | delivered
    person_name: str | None = None
    item_description: str | None = None
    item_sku: str | None = None
    item_ean: str | None = None
    item_ml_item_id: str | None = None  # ID do anúncio no marketplace (MLB...)
    cmig_product_id: int | None = None
    cmig_product_sku: str | None = None
    cmig_product_title: str | None = None
    cmig_id: int | None = None
    cmig_name: str | None = None
    # Classificação visual (M3): "direct_pg" | "overflow_cmig" | "cmig" | "kit_component" | "nfe_direct_pg"
    origin_kind: str | None = None
    # M5 — Auditoria (apenas quando source='adjustment')
    adjustment_kind: str | None = None  # manual_override | recompute | batch_recompute
    adjustment_reason: str | None = None
    adjustment_user_name: str | None = None
    adjustment_old: int | None = None
    adjustment_new: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if hasattr(self.date, "isoformat") else self.date
        return d


async def _fetch_nfe_events_for_cmig_product(
    cmig_product: CMIGProduct, db: AsyncSession
) -> list[StockEvent]:
    """NFes finalizadas/autorizadas tocando este CMIGProduct.

    Match em cascata:
    - `cmig_product_id` direto (items explicitamente CMIG).
    - Por EAN para items legacy SEM cmig_product_id, EXCLUINDO items que são
      explicitamente PG (source_type='pg'). Sem esse filtro, items PG cujo EAN
      coincide com um CMIG seriam puxados indevidamente pro histórico CMIG.
    """
    product_ean = (cmig_product.ean or "").strip()
    item_match = [InvoiceItem.cmig_product_id == cmig_product.id]
    if product_ean:
        item_match.append(
            and_(
                InvoiceItem.cmig_product_id.is_(None),
                InvoiceItem.ean == product_ean,
                # Items PG têm seu próprio caminho (_fetch_direct_pg_events).
                # Aqui aceitamos apenas legacy (NULL) e source='cmig'.
                or_(
                    InvoiceItem.source_type.is_(None),
                    InvoiceItem.source_type != "pg",
                ),
            )
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
    # Pré-computa quais invoices estão vinculadas a algum pedido (Order.invoice_id),
    # para aplicar a regra "NFe-out vinculada a pedido NÃO debita" no replay.
    invoice_ids_out = [
        inv.id for _, inv, _ in rows if inv.direction == "out"
    ]
    linked_invoice_ids: set[int] = set()
    if invoice_ids_out:
        linked_rows = (
            await db.execute(
                select(Order.invoice_id)
                .where(Order.invoice_id.in_(invoice_ids_out))
                .distinct()
            )
        ).all()
        linked_invoice_ids = {row[0] for row in linked_rows if row[0]}

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
                item_id=item.id,
                invoice_id=inv.id,
                invoice_number=inv.nfe_number,
                invoice_serie=inv.serie,
                invoice_status=inv.status,
                invoice_linked_to_order=(not is_in) and (inv.id in linked_invoice_ids),
                person_name=person_name,
                item_description=item.description,
                item_sku=item.sku,
                item_ean=item.ean,
                cmig_product_id=cmig_product.id,
                cmig_product_sku=cmig_product.sku_cmig,
                cmig_product_title=cmig_product.title,
                cmig_id=cmig_product.cmig_id,
                origin_kind="nfe_cmig",
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
                local_order_clause(),  # exclui pedidos FULL (baixa só do FullStock)
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
                item_id=item.id,
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
                origin_kind="cmig",
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
    status_by_order: dict[int, str] = dict(rows)
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
    # Calcula o saldo NFe-only no início: parte de current e reverte todas as NFes
    # que efetivamente moveram estoque (NFe-out linked_to_order não conta).
    nfe_only_initial = current_nfe_balance
    for e in events:
        if e.source == "nfe_in":
            nfe_only_initial -= e.qty
        elif e.source == "nfe_out" and not e.invoice_linked_to_order:
            nfe_only_initial += e.qty
    # Replay forward.
    has_pg = cmig_product.pg_product_id is not None
    projected = nfe_only_initial
    for e in events:
        if e.source == "nfe_in":
            projected += e.qty
            e.qty_to_cmig = e.qty
            e.qty_to_pg = 0
        elif e.source == "nfe_out":
            if e.invoice_linked_to_order:
                # NFe-out vinculada a pedido NÃO debita (pedido é fonte canonical)
                e.qty_to_cmig = 0
                e.qty_to_pg = 0
                continue
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

    # M5: ajustes manuais (informativo, não afetam o replay)
    adjustments = await _fetch_manual_adjustments("cmig", cmig_product.id, db)
    if adjustments:
        events.extend(adjustments)
        events.sort(key=lambda e: e.date)

    return events, nfe_only_initial


async def _fetch_direct_pg_events(
    pg_product: CatalogProduct, db: AsyncSession
) -> list[StockEvent]:
    """NFe items com source_type='pg' que casam com este PG por SKU ou EAN.

    Esses items NÃO vêm via nenhum CMIGProduct vinculado — são entradas/saídas
    diretas em PG (vínculo via SKU/EAN, não via FK).
    """
    sku = (pg_product.sku or "").strip()
    ean = (pg_product.ean or "").strip()

    # FK direta tem prioridade; SKU/EAN como fallback para itens legados
    match_clauses = [InvoiceItem.catalog_product_id == pg_product.id]
    if sku:
        match_clauses.append(and_(InvoiceItem.catalog_product_id.is_(None), InvoiceItem.sku == sku))
    if ean:
        match_clauses.append(and_(InvoiceItem.catalog_product_id.is_(None), InvoiceItem.ean == ean))
    if len(match_clauses) == 1 and not sku and not ean:
        return []

    stmt = (
        select(InvoiceItem, Invoice, Person.name.label("person_name"))
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .outerjoin(Person, Person.id == Invoice.person_id)
        .where(
            and_(
                InvoiceItem.source_type == "pg",
                Invoice.stock_updated == True,  # noqa: E712
                Invoice.status.in_(("authorized", "finalized")),
                or_(*match_clauses),
            )
        )
    )

    rows = (await db.execute(stmt)).all()
    # Pré-computa invoices vinculadas a pedido (mesma regra dos CMIG events)
    invoice_ids_out = [inv.id for _, inv, _ in rows if inv.direction == "out"]
    linked_invoice_ids: set[int] = set()
    if invoice_ids_out:
        linked_rows = (
            await db.execute(
                select(Order.invoice_id)
                .where(Order.invoice_id.in_(invoice_ids_out))
                .distinct()
            )
        ).all()
        linked_invoice_ids = {row[0] for row in linked_rows if row[0]}

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
                qty_to_cmig=0,
                qty_to_pg=qty,  # vai 100% pra PG (não passa por CMIG)
                item_id=item.id,
                invoice_id=inv.id,
                invoice_number=inv.nfe_number,
                invoice_linked_to_order=(not is_in) and (inv.id in linked_invoice_ids),
                invoice_serie=inv.serie,
                invoice_status=inv.status,
                person_name=person_name,
                item_description=item.description,
                item_sku=item.sku,
                item_ean=item.ean,
                origin_kind="nfe_direct_pg",
            )
        )
    return events


async def _fetch_direct_pg_order_events(
    pg_product: CatalogProduct, db: AsyncSession
) -> list[StockEvent]:
    """Pedidos com OrderItem.catalog_product_id == pg.id em shipped/delivered/handling/ready_to_ship,
    SEM CMIGProduct na CMIG do pedido capaz de contar (mesma regra de exclusão do balanço).

    Esses pedidos não passam por CMIG (vínculo direto via catalog_product_id)
    e antes ficavam invisíveis no histórico do PG. Eles vão 100% pro saldo do PG.

    Regra de exclusão mantida idêntica à de `calculate_pg_product_stock` para
    evitar dupla contagem: olhamos apenas sku_cmig e pg_product_id (não listing),
    pois listing_match dentro de EXISTS aninhado gera cartesian join em SQLAlchemy.
    Na prática, se há ProductListing.cmig_product_id apontando para algum CMIG
    daquela CMIG, esse CMIG geralmente tem sku_cmig ou pg_product_id capazes
    de bater na mesma condição.
    """
    has_cmig_match = exists().where(
        and_(
            CMIGProduct.cmig_id == Order.cmig_id,
            or_(
                CMIGProduct.sku_cmig == OrderItem.sku,
                CMIGProduct.pg_product_id == OrderItem.catalog_product_id,
            ),
        )
    )

    stmt = (
        select(OrderItem, Order)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                OrderItem.catalog_product_id == pg_product.id,
                Order.shipment_status.in_(SHIPPED_STATUSES),
                local_order_clause(),  # exclui pedidos FULL (baixa só do FullStock)
                ~has_cmig_match,
            )
        )
    )

    rows = (await db.execute(stmt)).all()
    events: list[StockEvent] = []
    for item, order in rows:
        m_date = order.shipped_at or order.created_at
        if m_date is None:
            continue
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        shipment_status = order.shipment_status or ""
        events.append(
            StockEvent(
                date=m_date,
                source="order",
                direction="out",
                qty=qty,
                qty_to_cmig=0,
                qty_to_pg=qty,  # 100% debita do PG (sem CMIG intermediário)
                item_id=item.id,
                order_id=order.id,
                order_platform=order.platform,
                order_platform_id=order.platform_order_id,
                order_shipment_status=shipment_status,
                order_has_invoice=bool(order.invoice_id),
                order_invoice_finalized=False,
                is_reserved=shipment_status in RESERVED_STATUSES,
                is_definitive=shipment_status in DEFINITIVE_STATUSES,
                person_name=order.buyer_name,
                item_description=item.title,
                item_sku=item.sku,
                item_ml_item_id=item.ml_item_id,
                origin_kind="direct_pg",
            )
        )
    return events


async def _fetch_kit_component_events(
    pg_product: CatalogProduct, db: AsyncSession
) -> list[StockEvent]:
    """Pedidos vendendo um KIT do qual este PG é componente.

    Para cada pedido shipped/delivered/handling/ready_to_ship cujo OrderItem
    aponta para um CatalogProduct composto (kit), e cujos componentes incluem
    este `pg_product`, gera 1 StockEvent com:
      qty = OrderItem.quantity * CatalogProductComponent.quantity

    Esses pedidos são contados no balanço via `kit_usage` em
    `calculate_pg_product_stock` (caminho 3) — aqui só geramos a visualização
    para a tabela do modal.
    """
    KitAlias = CatalogProduct
    stmt = (
        select(OrderItem, Order, KitAlias, CatalogProductComponent.quantity.label("comp_qty"))
        .join(Order, Order.id == OrderItem.order_id)
        .join(
            CatalogProductComponent,
            CatalogProductComponent.composite_id == OrderItem.catalog_product_id,
        )
        .join(KitAlias, KitAlias.id == OrderItem.catalog_product_id)
        .where(
            and_(
                CatalogProductComponent.component_id == pg_product.id,
                Order.shipment_status.in_(SHIPPED_STATUSES),
                local_order_clause(),  # exclui kits vendidos via FULL
            )
        )
    )
    rows = (await db.execute(stmt)).all()
    events: list[StockEvent] = []
    for item, order, kit, comp_qty in rows:
        m_date = order.shipped_at or order.created_at
        if m_date is None:
            continue
        oi_qty = int(item.quantity or 0)
        cq = int(comp_qty or 0)
        effective_qty = oi_qty * cq
        if effective_qty <= 0:
            continue
        shipment_status = order.shipment_status or ""
        events.append(
            StockEvent(
                date=m_date,
                source="order",
                direction="out",
                qty=effective_qty,
                qty_to_cmig=0,
                qty_to_pg=effective_qty,  # consumo 100% do componente
                item_id=item.id,
                order_id=order.id,
                order_platform=order.platform,
                order_platform_id=order.platform_order_id,
                order_shipment_status=shipment_status,
                order_has_invoice=bool(order.invoice_id),
                order_invoice_finalized=False,
                is_reserved=shipment_status in RESERVED_STATUSES,
                is_definitive=shipment_status in DEFINITIVE_STATUSES,
                person_name=order.buyer_name,
                # Mostra qual kit consumiu o componente
                item_description=f"Kit: {kit.title}",
                item_sku=item.sku,
                item_ml_item_id=item.ml_item_id,
                origin_kind="kit_component",
            )
        )
    return events


async def _fetch_manual_adjustments(
    product_type: str, product_id: int, db: AsyncSession
) -> list[StockEvent]:
    """Carrega entries de `stock_manual_adjustments` para auditoria visual.

    Esses eventos são puramente INFORMATIVOS — não afetam o running balance
    (já estão refletidos no cache stock_quantity).
    """
    from models.stock_adjustment import StockManualAdjustment
    from models.user import User

    rows = (
        await db.execute(
            select(StockManualAdjustment, User.full_name)
            .outerjoin(User, User.id == StockManualAdjustment.user_id)
            .where(
                and_(
                    StockManualAdjustment.product_type == product_type,
                    StockManualAdjustment.product_id == product_id,
                )
            )
            .order_by(StockManualAdjustment.created_at)
        )
    ).all()

    events: list[StockEvent] = []
    for adj, user_name in rows:
        delta = int(adj.delta or 0)
        events.append(
            StockEvent(
                date=adj.created_at,
                source="adjustment",
                direction="in" if delta >= 0 else "out",
                qty=abs(delta),
                qty_to_cmig=0,
                qty_to_pg=0,  # informativo, não conta no running balance
                origin_kind=adj.adjustment_kind,
                adjustment_kind=adj.adjustment_kind,
                adjustment_reason=adj.reason,
                adjustment_user_name=user_name,
                adjustment_old=int(adj.old_value or 0),
                adjustment_new=int(adj.new_value or 0),
            )
        )
    return events


async def replay_stock_events_for_pg_product(
    pg_product: CatalogProduct, db: AsyncSession
) -> tuple[list[StockEvent], list[CMIGProduct]]:
    """Agrega eventos do PG: NFes dos CMIGProducts vinculados + NFes diretas em PG
    + pedidos diretos no PG (sem CMIG intermediário).

    O frontend filtra `qty_to_pg > 0` pra mostrar overflow e NFes diretas.
    """
    linked_cmigs = (
        await db.execute(
            select(CMIGProduct).where(CMIGProduct.pg_product_id == pg_product.id)
        )
    ).scalars().all()

    all_events: list[StockEvent] = []
    seen_item_ids: set[int] = set()  # dedup por InvoiceItem.id (não por invoice)
    for cp in linked_cmigs:
        events, _ = await replay_stock_events_for_cmig_product(cp, db)
        for e in events:
            if e.item_id is not None and e.item_id in seen_item_ids:
                continue
            # No contexto PG, pedidos vindos via replay CMIG são "overflow"
            if e.source == "order" and e.qty_to_pg > 0:
                e.origin_kind = "overflow_cmig"
            all_events.append(e)
            if e.item_id is not None:
                seen_item_ids.add(e.item_id)

    # NFes diretas em PG (source_type='pg' com match por SKU/EAN do PG, sem CMIG resolvido)
    direct_pg = await _fetch_direct_pg_events(pg_product, db)
    for e in direct_pg:
        if e.item_id is not None and e.item_id in seen_item_ids:
            continue
        all_events.append(e)
        if e.item_id is not None:
            seen_item_ids.add(e.item_id)

    # Pedidos diretos no PG (sem CMIG capaz de contar) — debitam 100% do PG.
    # Dedup separado: OrderItem.id pode colidir com InvoiceItem.id (são tabelas distintas)
    direct_orders = await _fetch_direct_pg_order_events(pg_product, db)
    seen_order_item_ids: set[int] = set()
    for e in direct_orders:
        if e.item_id is not None and e.item_id in seen_order_item_ids:
            continue
        all_events.append(e)
        if e.item_id is not None:
            seen_order_item_ids.add(e.item_id)

    # Kit component events — pedidos que vendem kits cujo componente é este PG
    kit_events = await _fetch_kit_component_events(pg_product, db)
    for e in kit_events:
        # Dedup com direct_orders pelo OrderItem.id
        if e.item_id is not None and e.item_id in seen_order_item_ids:
            continue
        all_events.append(e)
        if e.item_id is not None:
            seen_order_item_ids.add(e.item_id)

    # M5: Auditoria de ajustes manuais (informativo)
    adjustments = await _fetch_manual_adjustments("pg", pg_product.id, db)
    all_events.extend(adjustments)

    all_events.sort(key=lambda e: e.date)
    return all_events, list(linked_cmigs)

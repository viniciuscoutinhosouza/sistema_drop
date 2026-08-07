"""
Stock reservation service — movimentações transacionais de estoque.

Todas as funções são idempotentes: verificam stock_movements antes de agir.

Camadas de estoque:
  stock_quantity              : estoque físico no galpão
  reserved_quantity           : reservado por pedidos ativos (baixados/pagos/em preparo)
  awaiting_return_quantity    : pedido cancelado pós-despacho, produto ainda em trânsito
  pending_validation_quantity : devolução recebida, aguardando inspeção do operador
  unfit_quantity              : reprovado na inspeção

available_quantity (computed) = stock_quantity - reserved_quantity
"""

import logging

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from models.cmig import CMIGProduct, CMIGProductVariant
from models.full_stock import FullStock
from models.order import Order, OrderItem
from models.product import CatalogProduct, CatalogProductVariant
from models.return_ import Return
from models.stock_movement import StockMovement

logger = logging.getLogger(__name__)

# Status de envio que indicam que o produto já saiu do galpão
_DISPATCHED_STATUSES = {"shipped", "delivered", "in_transit", "out_for_delivery", "first_visit"}

# Status de pedido internos que indicam produto já saiu
_DISPATCHED_ORDER_STATUSES = {"shipped", "delivered"}


def _order_was_dispatched(order: Order) -> bool:
    return (
        (order.shipment_status or "") in _DISPATCHED_STATUSES
        or (order.status or "") in _DISPATCHED_ORDER_STATUSES
    )


async def _already_has_movement(db: AsyncSession, order_id: int, movement_type: str) -> bool:
    result = await db.execute(
        select(StockMovement).where(
            StockMovement.order_id == order_id,
            StockMovement.movement_type == movement_type,
        )
    )
    return result.scalar_one_or_none() is not None


async def _already_has_return_movement(
    db: AsyncSession, return_id: int, movement_type: str
) -> bool:
    result = await db.execute(
        select(StockMovement).where(
            StockMovement.return_id == return_id,
            StockMovement.movement_type == movement_type,
        )
    )
    return result.scalar_one_or_none() is not None


def _log(db: AsyncSession, *, product_type: str, product_id: int, order_id=None,
         return_id=None, movement_type: str, qty: int, field: str, delta: int,
         created_by=None) -> None:
    db.add(StockMovement(
        product_type=product_type,
        product_id=product_id,
        order_id=order_id,
        return_id=return_id,
        movement_type=movement_type,
        qty=qty,
        field_affected=field,
        delta=delta,
        created_by=created_by,
    ))


async def _get_order_items(db: AsyncSession, order: Order) -> list[OrderItem]:
    result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    return result.scalars().all()


# ─── Reserva FULL (Fase 1) ────────────────────────────────────────────────────
# Pedido FULL baixado: debita full_stock.reserved_qty da conta correspondente.
# NÃO toca galpão local. Liberado quando shipped/cancelled.

async def _adjust_full_reserved(
    db: AsyncSession,
    *,
    product_type: str,
    product_id: int,
    account_id: int,
    delta: int,
) -> bool:
    """Ajusta full_stock.reserved_qty. Cria linha com qty=0 se delta>0 e não existir."""
    row = (
        await db.execute(
            select(FullStock).where(
                FullStock.product_type == product_type,
                FullStock.product_id == product_id,
                FullStock.marketplace_account_id == account_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.reserved_qty = max(0, int(row.reserved_qty or 0) + delta)
        return True
    if delta > 0:
        db.add(
            FullStock(
                product_type=product_type,
                product_id=product_id,
                marketplace_account_id=account_id,
                qty=0,
                reserved_qty=delta,
            )
        )
        return True
    return False


async def _apply_full_reservation(
    db: AsyncSession, order: Order, movement_type: str, sign: int
) -> None:
    """Loop comum pra reservar (sign=+1) ou liberar (sign=-1) FULL por pedido."""
    if not order.account_id:
        logger.warning("FULL %s: order %s sem account_id", movement_type, order.id)
        return
    from services.full_stock_service import resolve_full_product

    items = await _get_order_items(db, order)
    for item in items:
        qty = item.quantity or 1
        # FULL pertence à conta CMIG → resolve preferindo o CMIG product do anúncio.
        ptype, pid = await resolve_full_product(db, order, item)
        if not ptype:
            continue
        delta = sign * qty
        ok = await _adjust_full_reserved(
            db,
            product_type=ptype,
            product_id=pid,
            account_id=order.account_id,
            delta=delta,
        )
        if ok:
            _log(
                db,
                product_type=ptype,
                product_id=pid,
                order_id=order.id,
                movement_type=movement_type,
                qty=qty,
                field="full_stock_reserved",
                delta=delta,
            )


# ─── Reserva ──────────────────────────────────────────────────────────────────

async def _kit_components(db: AsyncSession, catalog_product_id: int, qty: int):
    """Se o produto for COMPOSTO, devolve [(component_id, qtd_total), ...]; senão None.

    ADR-0023: kit não tem estoque próprio. Reserva, liberação e baixa têm de atingir os
    COMPONENTES — reservar no kit deixava o componente anunciando unidades já vendidas
    (janela de oversell entre a venda e o despacho)."""
    from models.product import CatalogProductComponent

    prod = (
        await db.execute(
            select(CatalogProduct).where(CatalogProduct.id == catalog_product_id)
        )
    ).scalar_one_or_none()
    if prod is None or not prod.is_composite:
        return None
    comps = (
        await db.execute(
            select(CatalogProductComponent).where(
                CatalogProductComponent.composite_id == catalog_product_id
            )
        )
    ).scalars().all()
    return [(c.component_id, qty * max(int(c.quantity or 1), 1)) for c in comps if c.component_id]


async def _kit_components_cmig(db: AsyncSession, cmig_product_id: int, qty: int):
    """Se o CMIGProduct for COMPOSTO, devolve [(tipo, id, qtd_total), ...] com tipo
    'cmig' ou 'pg'; senão None. ADR-0023 — mesma razão do `_kit_components` do PG: sem
    isto a venda de kit CMIG deixava os componentes anunciando unidades já vendidas."""
    from models.cmig import CMIGProductComponent

    prod = (
        await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
    ).scalar_one_or_none()
    if prod is None or not prod.is_composite:
        return None
    comps = (
        await db.execute(
            select(CMIGProductComponent).where(
                CMIGProductComponent.composite_id == cmig_product_id
            )
        )
    ).scalars().all()
    out = []
    for c in comps:
        fator = qty * max(int(c.quantity or 1), 1)
        if c.cmig_product_id:
            out.append(("cmig", c.cmig_product_id, fator))
        elif c.catalog_product_id:
            out.append(("pg", c.catalog_product_id, fator))
    return out


async def reserve_stock(db: AsyncSession, order: Order) -> None:
    """Pedido baixado (downloaded) → reserva o estoque dos produtos vinculados.

    - shipping_mode='full': reserva full_stock.reserved_qty da conta ML.
    - demais modos: reserva CatalogProduct/CMIGProduct.reserved_quantity local.
    Idempotente: skip se já há movimento 'reserve' ou 'full_reserve' para o order.
    """
    if order.status == "cancelled":
        return
    if order.shipping_mode == "full":
        if await _already_has_movement(db, order.id, "full_reserve"):
            return
        await _apply_full_reservation(db, order, movement_type="full_reserve", sign=+1)
        try:
            await db.commit()
        except Exception as exc:
            logger.error("reserve_stock FULL order=%s: %s", order.id, exc)
        return
    if await _already_has_movement(db, order.id, "reserve"):
        return

    items = await _get_order_items(db, order)
    # Ids tocados — inclui os COMPONENTES quando o item é kit. Alimenta o push de estoque
    # no fim: reservar muda o disponível (estoque − reservado), então os anúncios do
    # componente E dos kits que o usam têm de ser reavaliados na hora, não só no ciclo
    # de 30 min (regra do dono: recalcular a cada movimentação).
    _pg_ids: set[int] = set()
    _cmig_ids: set[int] = set()
    for item in items:
        qty = item.quantity or 1
        reserved = False

        if item.catalog_product_id:
            kit = await _kit_components(db, item.catalog_product_id, qty)
            alvos = kit if kit is not None else [(item.catalog_product_id, qty)]
            for _pid, _q in alvos:
                await db.execute(
                    update(CatalogProduct)
                    .where(CatalogProduct.id == _pid)
                    .values(reserved_quantity=CatalogProduct.reserved_quantity + _q)
                )
                _log(db, product_type="pg", product_id=_pid,
                     order_id=order.id, movement_type="reserve", qty=_q,
                     field="reserved_quantity", delta=_q)
                _pg_ids.add(_pid)
            reserved = True

            if item.catalog_variant_id and item.catalog_source == "pg":
                await db.execute(
                    update(CatalogProductVariant)
                    .where(CatalogProductVariant.id == item.catalog_variant_id)
                    .values(reserved_quantity=CatalogProductVariant.reserved_quantity + qty)
                )
                _log(db, product_type="variant_pg", product_id=item.catalog_variant_id,
                     order_id=order.id, movement_type="reserve", qty=qty,
                     field="reserved_quantity", delta=qty)

        if item.cmig_product_id and not reserved:
            _kit = await _kit_components_cmig(db, item.cmig_product_id, qty)
            _alvos = _kit if _kit is not None else [("cmig", item.cmig_product_id, qty)]
            for _tp, _pid, _q in _alvos:
                _M = CMIGProduct if _tp == "cmig" else CatalogProduct
                await db.execute(
                    update(_M).where(_M.id == _pid)
                    .values(reserved_quantity=_M.reserved_quantity + _q)
                )
                _log(db, product_type=_tp, product_id=_pid,
                     order_id=order.id, movement_type="reserve", qty=_q,
                     field="reserved_quantity", delta=_q)
                (_cmig_ids if _tp == "cmig" else _pg_ids).add(_pid)

            if item.catalog_variant_id and item.catalog_source == "cmig":
                await db.execute(
                    update(CMIGProductVariant)
                    .where(CMIGProductVariant.id == item.catalog_variant_id)
                    .values(reserved_quantity=CMIGProductVariant.reserved_quantity + qty)
                )
                _log(db, product_type="variant_cmig", product_id=item.catalog_variant_id,
                     order_id=order.id, movement_type="reserve", qty=qty,
                     field="reserved_quantity", delta=qty)

    try:
        await db.commit()
        # Propaga na hora: reservar/liberar muda o DISPONÍVEL (estoque − reservado), e o
        # `stock_sync_service` expande componente → kits, então o anúncio do kit e o do
        # componente são reavaliados juntos. Sem isto a mudança só apareceria no ciclo de
        # 30 min (regra do dono: recalcular a cada movimentação de kit ou componente).
        if _pg_ids or _cmig_ids:
            from services.stock_sync_service import schedule_push

            schedule_push(_cmig_ids, _pg_ids)
    except Exception as exc:
        logger.error("reserve_stock order=%s: %s", order.id, exc)


# ─── Liberação de reserva (cancelamento antes do despacho) ───────────────────

async def release_reservation(db: AsyncSession, order: Order) -> None:
    """Pedido cancelado ANTES de ser despachado → libera a reserva.

    - shipping_mode='full': libera full_stock.reserved_qty da conta ML.
    - demais modos: libera reserved_quantity local (galpão).
    """
    if order.shipping_mode == "full":
        if await _already_has_movement(db, order.id, "full_unreserve"):
            return
        await _apply_full_reservation(db, order, movement_type="full_unreserve", sign=-1)
        try:
            await db.commit()
        except Exception as exc:
            logger.error("release_reservation FULL order=%s: %s", order.id, exc)
        return
    if await _already_has_movement(db, order.id, "unreserve"):
        return

    items = await _get_order_items(db, order)
    _pg_ids: set[int] = set()
    _cmig_ids: set[int] = set()
    for item in items:
        qty = item.quantity or 1
        released = False

        if item.catalog_product_id:
            kit = await _kit_components(db, item.catalog_product_id, qty)
            alvos = kit if kit is not None else [(item.catalog_product_id, qty)]
            for _pid, _q in alvos:
                await db.execute(
                    update(CatalogProduct)
                    .where(CatalogProduct.id == _pid)
                    .values(reserved_quantity=CatalogProduct.reserved_quantity - _q)
                )
                _log(db, product_type="pg", product_id=_pid,
                     order_id=order.id, movement_type="unreserve", qty=_q,
                     field="reserved_quantity", delta=-_q)
                _pg_ids.add(_pid)
            released = True

            if item.catalog_variant_id and item.catalog_source == "pg":
                await db.execute(
                    update(CatalogProductVariant)
                    .where(CatalogProductVariant.id == item.catalog_variant_id)
                    .values(reserved_quantity=CatalogProductVariant.reserved_quantity - qty)
                )
                _log(db, product_type="variant_pg", product_id=item.catalog_variant_id,
                     order_id=order.id, movement_type="unreserve", qty=qty,
                     field="reserved_quantity", delta=-qty)

        if item.cmig_product_id and not released:
            _kit = await _kit_components_cmig(db, item.cmig_product_id, qty)
            _alvos = _kit if _kit is not None else [("cmig", item.cmig_product_id, qty)]
            for _tp, _pid, _q in _alvos:
                _M = CMIGProduct if _tp == "cmig" else CatalogProduct
                await db.execute(
                    update(_M).where(_M.id == _pid)
                    .values(reserved_quantity=_M.reserved_quantity - _q)
                )
                _log(db, product_type=_tp, product_id=_pid,
                     order_id=order.id, movement_type="unreserve", qty=_q,
                     field="reserved_quantity", delta=-_q)
                (_cmig_ids if _tp == "cmig" else _pg_ids).add(_pid)

            if item.catalog_variant_id and item.catalog_source == "cmig":
                await db.execute(
                    update(CMIGProductVariant)
                    .where(CMIGProductVariant.id == item.catalog_variant_id)
                    .values(reserved_quantity=CMIGProductVariant.reserved_quantity - qty)
                )
                _log(db, product_type="variant_cmig", product_id=item.catalog_variant_id,
                     order_id=order.id, movement_type="unreserve", qty=qty,
                     field="reserved_quantity", delta=-qty)

    try:
        await db.commit()
        # Propaga na hora: reservar/liberar muda o DISPONÍVEL (estoque − reservado), e o
        # `stock_sync_service` expande componente → kits, então o anúncio do kit e o do
        # componente são reavaliados juntos. Sem isto a mudança só apareceria no ciclo de
        # 30 min (regra do dono: recalcular a cada movimentação de kit ou componente).
        if _pg_ids or _cmig_ids:
            from services.stock_sync_service import schedule_push

            schedule_push(_cmig_ids, _pg_ids)
    except Exception as exc:
        logger.error("release_reservation order=%s: %s", order.id, exc)


# ─── Confirmação de despacho ──────────────────────────────────────────────────

async def _release_orphan_local_reserve(db: AsyncSession, order: Order) -> None:
    """Libera reserva LOCAL órfã de um pedido FULL.

    Quando um pedido FULL é baixado antes do shipping_mode ser classificado, o
    reserve_stock cai no caminho local e reserva o galpão (reserved_quantity).
    Ao despachar como FULL, essa reserva nunca era liberada. Aqui corrigimos:
    se há 'reserve' local sem 'unreserve', devolve a reserva.
    """
    if not await _already_has_movement(db, order.id, "reserve"):
        return
    if await _already_has_movement(db, order.id, "unreserve"):
        return
    items = await _get_order_items(db, order)
    for item in items:
        qty = item.quantity or 1
        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(reserved_quantity=CatalogProduct.reserved_quantity - qty)
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id, order_id=order.id,
                 movement_type="unreserve", qty=qty, field="reserved_quantity", delta=-qty)
            if item.catalog_variant_id and item.catalog_source == "pg":
                await db.execute(
                    update(CatalogProductVariant)
                    .where(CatalogProductVariant.id == item.catalog_variant_id)
                    .values(reserved_quantity=CatalogProductVariant.reserved_quantity - qty)
                )
                _log(db, product_type="variant_pg", product_id=item.catalog_variant_id, order_id=order.id,
                     movement_type="unreserve", qty=qty, field="reserved_quantity", delta=-qty)
        elif item.cmig_product_id:
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(reserved_quantity=CMIGProduct.reserved_quantity - qty)
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id, order_id=order.id,
                 movement_type="unreserve", qty=qty, field="reserved_quantity", delta=-qty)


async def confirm_dispatch(db: AsyncSession, order: Order) -> None:
    """Pedido despachado/shipped → debita estoque físico e libera reserva."""
    if order.shipping_mode == "full":
        from services.full_stock_service import apply_full_order_shipped
        try:
            await _release_orphan_local_reserve(db, order)
            await apply_full_order_shipped(db, order)
            await db.commit()
        except Exception as exc:
            logger.error("confirm_dispatch FULL order=%s: %s", order.id, exc)
        return
    if await _already_has_movement(db, order.id, "dispatch"):
        return

    items = await _get_order_items(db, order)
    _pg_ids: set[int] = set()
    _cmig_ids: set[int] = set()

    for item in items:
        qty = item.quantity or 1
        dispatched = False

        if item.catalog_product_id:
            # Kit: baixa e libera reserva nos COMPONENTES (o kit não tem estoque próprio —
            # debitar a coluna dele deixava-a negativa). O replay já debita o componente
            # pelo `kit_usage`; este é o caminho incremental, que converge com ele.
            kit = await _kit_components(db, item.catalog_product_id, qty)
            alvos = kit if kit is not None else [(item.catalog_product_id, qty)]
            for _pid, _q in alvos:
                await db.execute(
                    update(CatalogProduct)
                    .where(CatalogProduct.id == _pid)
                    .values(
                        stock_quantity=CatalogProduct.stock_quantity - _q,
                        reserved_quantity=CatalogProduct.reserved_quantity - _q,
                    )
                )
                _log(db, product_type="pg", product_id=_pid,
                     order_id=order.id, movement_type="dispatch", qty=_q,
                     field="stock_quantity", delta=-_q)
                _pg_ids.add(_pid)
            dispatched = True

            if item.catalog_variant_id and item.catalog_source == "pg":
                await db.execute(
                    update(CatalogProductVariant)
                    .where(CatalogProductVariant.id == item.catalog_variant_id)
                    .values(
                        stock_quantity=CatalogProductVariant.stock_quantity - qty,
                        reserved_quantity=CatalogProductVariant.reserved_quantity - qty,
                    )
                )
                _log(db, product_type="variant_pg", product_id=item.catalog_variant_id,
                     order_id=order.id, movement_type="dispatch", qty=qty,
                     field="stock_quantity", delta=-qty)

        if item.cmig_product_id and not dispatched:
            # Kit CMIG: baixa e libera nos COMPONENTES (o kit não tem estoque próprio).
            _kit = await _kit_components_cmig(db, item.cmig_product_id, qty)
            _alvos = _kit if _kit is not None else [("cmig", item.cmig_product_id, qty)]
            for _tp, _pid, _q in _alvos:
                _M = CMIGProduct if _tp == "cmig" else CatalogProduct
                await db.execute(
                    update(_M).where(_M.id == _pid).values(
                        stock_quantity=_M.stock_quantity - _q,
                        reserved_quantity=_M.reserved_quantity - _q,
                    )
                )
                _log(db, product_type=_tp, product_id=_pid,
                     order_id=order.id, movement_type="dispatch", qty=_q,
                     field="stock_quantity", delta=-_q)
                (_cmig_ids if _tp == "cmig" else _pg_ids).add(_pid)

            if item.catalog_variant_id and item.catalog_source == "cmig":
                await db.execute(
                    update(CMIGProductVariant)
                    .where(CMIGProductVariant.id == item.catalog_variant_id)
                    .values(
                        stock_quantity=CMIGProductVariant.stock_quantity - qty,
                        reserved_quantity=CMIGProductVariant.reserved_quantity - qty,
                    )
                )
                _log(db, product_type="variant_cmig", product_id=item.catalog_variant_id,
                     order_id=order.id, movement_type="dispatch", qty=qty,
                     field="stock_quantity", delta=-qty)

    try:
        await db.commit()
        from services.stock_sync_service import schedule_push
        schedule_push(_cmig_ids, _pg_ids)
    except Exception as exc:
        logger.error("confirm_dispatch order=%s: %s", order.id, exc)


# ─── Cancelamento pós-despacho ────────────────────────────────────────────────

async def mark_awaiting_return(db: AsyncSession, order: Order) -> None:
    """Pedido cancelado APÓS despacho → libera reserva e marca produto como aguardando retorno."""
    if order.shipping_mode == "full":
        return  # Retorno de FULL é via NF-e entrada — não usa awaiting_return do galpão
    if await _already_has_movement(db, order.id, "await_return"):
        return

    items = await _get_order_items(db, order)
    for item in items:
        qty = item.quantity or 1
        marked = False

        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(
                    reserved_quantity=CatalogProduct.reserved_quantity - qty,
                    awaiting_return_quantity=CatalogProduct.awaiting_return_quantity + qty,
                )
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 order_id=order.id, movement_type="await_return", qty=qty,
                 field="awaiting_return_quantity", delta=qty)
            marked = True

        if item.cmig_product_id and not marked:
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(
                    reserved_quantity=CMIGProduct.reserved_quantity - qty,
                    awaiting_return_quantity=CMIGProduct.awaiting_return_quantity + qty,
                )
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 order_id=order.id, movement_type="await_return", qty=qty,
                 field="awaiting_return_quantity", delta=qty)

    order.return_status = "awaiting_return"
    try:
        await db.commit()
    except Exception as exc:
        logger.error("mark_awaiting_return order=%s: %s", order.id, exc)


# ─── Confirmação de retorno físico (pedido cancelado pós-despacho) ────────────

async def confirm_pending_return(db: AsyncSession, order: Order) -> None:
    """UGO confirma que o produto físico voltou ao galpão → entra no estoque disponível."""
    if await _already_has_movement(db, order.id, "confirm_return"):
        return

    items = await _get_order_items(db, order)
    _pg_ids: set[int] = set()
    _cmig_ids: set[int] = set()

    for item in items:
        qty = item.quantity or 1
        confirmed = False

        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(
                    stock_quantity=CatalogProduct.stock_quantity + qty,
                    awaiting_return_quantity=CatalogProduct.awaiting_return_quantity - qty,
                )
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 order_id=order.id, movement_type="confirm_return", qty=qty,
                 field="stock_quantity", delta=qty)
            _pg_ids.add(item.catalog_product_id)
            confirmed = True

        if item.cmig_product_id and not confirmed:
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(
                    stock_quantity=CMIGProduct.stock_quantity + qty,
                    awaiting_return_quantity=CMIGProduct.awaiting_return_quantity - qty,
                )
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 order_id=order.id, movement_type="confirm_return", qty=qty,
                 field="stock_quantity", delta=qty)
            _cmig_ids.add(item.cmig_product_id)

    order.return_status = "returned"
    try:
        await db.commit()
        from services.stock_sync_service import schedule_push
        schedule_push(_cmig_ids, _pg_ids)
    except Exception as exc:
        logger.error("confirm_pending_return order=%s: %s", order.id, exc)


# ─── Recebimento de devolução de cliente ─────────────────────────────────────

async def receive_customer_return(db: AsyncSession, return_obj: Return) -> None:
    """Devolução de cliente recebida → produto entra em pending_validation_quantity."""
    if not return_obj.order_id:
        return
    if await _already_has_return_movement(db, return_obj.id, "receive_return"):
        return

    result = await db.execute(select(Order).where(Order.id == return_obj.order_id))
    order = result.scalar_one_or_none()
    if not order:
        return

    items = await _get_order_items(db, order)
    for item in items:
        qty = item.quantity or 1
        received = False

        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(
                    pending_validation_quantity=CatalogProduct.pending_validation_quantity + qty,
                )
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 return_id=return_obj.id, movement_type="receive_return", qty=qty,
                 field="pending_validation_quantity", delta=qty)
            received = True

        if item.cmig_product_id and not received:
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(
                    pending_validation_quantity=CMIGProduct.pending_validation_quantity + qty,
                )
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 return_id=return_obj.id, movement_type="receive_return", qty=qty,
                 field="pending_validation_quantity", delta=qty)

    try:
        await db.commit()
    except Exception as exc:
        logger.error("receive_customer_return return=%s: %s", return_obj.id, exc)


# ─── Validação de devolução ───────────────────────────────────────────────────

async def validate_return(
    db: AsyncSession, return_obj: Return, approved: bool, user_id: int | None = None
) -> None:
    """UGO valida a devolução:
    - approved=True  → produto volta ao estoque físico disponível
    - approved=False → produto vai para unfit_quantity
    """
    movement_type = "validate_ok" if approved else "validate_unfit"
    if await _already_has_return_movement(db, return_obj.id, movement_type):
        return
    if not return_obj.order_id:
        return

    result = await db.execute(select(Order).where(Order.id == return_obj.order_id))
    order = result.scalar_one_or_none()
    if not order:
        return

    items = await _get_order_items(db, order)
    _pg_ids: set[int] = set()
    _cmig_ids: set[int] = set()

    for item in items:
        qty = item.quantity or 1
        validated = False

        if item.catalog_product_id:
            if approved:
                await db.execute(
                    update(CatalogProduct)
                    .where(CatalogProduct.id == item.catalog_product_id)
                    .values(
                        pending_validation_quantity=CatalogProduct.pending_validation_quantity - qty,
                        stock_quantity=CatalogProduct.stock_quantity + qty,
                    )
                )
                _log(db, product_type="pg", product_id=item.catalog_product_id,
                     return_id=return_obj.id, movement_type=movement_type, qty=qty,
                     field="stock_quantity", delta=qty, created_by=user_id)
                _pg_ids.add(item.catalog_product_id)
            else:
                await db.execute(
                    update(CatalogProduct)
                    .where(CatalogProduct.id == item.catalog_product_id)
                    .values(
                        pending_validation_quantity=CatalogProduct.pending_validation_quantity - qty,
                        unfit_quantity=CatalogProduct.unfit_quantity + qty,
                    )
                )
                _log(db, product_type="pg", product_id=item.catalog_product_id,
                     return_id=return_obj.id, movement_type=movement_type, qty=qty,
                     field="unfit_quantity", delta=qty, created_by=user_id)
            validated = True

        if item.cmig_product_id and not validated:
            if approved:
                await db.execute(
                    update(CMIGProduct)
                    .where(CMIGProduct.id == item.cmig_product_id)
                    .values(
                        pending_validation_quantity=CMIGProduct.pending_validation_quantity - qty,
                        stock_quantity=CMIGProduct.stock_quantity + qty,
                    )
                )
                _log(db, product_type="cmig", product_id=item.cmig_product_id,
                     return_id=return_obj.id, movement_type=movement_type, qty=qty,
                     field="stock_quantity", delta=qty, created_by=user_id)
                _cmig_ids.add(item.cmig_product_id)
            else:
                await db.execute(
                    update(CMIGProduct)
                    .where(CMIGProduct.id == item.cmig_product_id)
                    .values(
                        pending_validation_quantity=CMIGProduct.pending_validation_quantity - qty,
                        unfit_quantity=CMIGProduct.unfit_quantity + qty,
                    )
                )
                _log(db, product_type="cmig", product_id=item.cmig_product_id,
                     return_id=return_obj.id, movement_type=movement_type, qty=qty,
                     field="unfit_quantity", delta=qty, created_by=user_id)

    try:
        await db.commit()
        if approved:
            from services.stock_sync_service import schedule_push
            schedule_push(_cmig_ids, _pg_ids)
    except Exception as exc:
        logger.error("validate_return return=%s approved=%s: %s", return_obj.id, approved, exc)


# ─── Devolução NF-e-driven (Fase B): usa a QTD da NF-e de devolução ──────────
# Diferente de receive/validate_customer_return (que usam a qtd do PEDIDO), estas
# operam item a item pela quantidade REAL da NF-e (devolução parcial). `items` são
# os InvoiceItem da NF-e de devolução, já casados (catalog_product_id/cmig_product_id).


async def receive_return_items(db: AsyncSession, return_obj: Return, items: list) -> int:
    """Recebe a devolução pela QTD da NF-e → pending_validation_quantity. Idempotente.
    Retorna a qtd total recebida (0 se nada casou)."""
    if await _already_has_return_movement(db, return_obj.id, "receive_return"):
        return 0
    total = 0
    for item in items:
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(pending_validation_quantity=CatalogProduct.pending_validation_quantity + qty)
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 return_id=return_obj.id, movement_type="receive_return", qty=qty,
                 field="pending_validation_quantity", delta=qty)
            total += qty
        elif item.cmig_product_id:
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(pending_validation_quantity=CMIGProduct.pending_validation_quantity + qty)
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 return_id=return_obj.id, movement_type="receive_return", qty=qty,
                 field="pending_validation_quantity", delta=qty)
            total += qty
    return total


async def validate_return_items(
    db: AsyncSession, return_obj: Return, items: list, approved: bool, user_id: int | None = None
) -> None:
    """Valida a devolução NF-e-driven pela QTD da NF-e. Idempotente.
    - approved=True  → pending−, stock_quantity+ (volta ao vendável).
    - approved=False → pending−, unfit_quantity+ (fora do vendável; a nota de descarte
      é gerada pelo router como documento fiscal SEM efeito no estoque vendável).
    NÃO commita — o chamador (router) orquestra a transação e faz o commit."""
    movement_type = "validate_ok" if approved else "validate_unfit"
    if await _already_has_return_movement(db, return_obj.id, movement_type):
        return
    _pg_ids: set[int] = set()
    _cmig_ids: set[int] = set()
    for item in items:
        qty = int(item.quantity or 0)
        if qty <= 0:
            continue
        if item.catalog_product_id:
            vals = (
                {
                    "pending_validation_quantity": CatalogProduct.pending_validation_quantity - qty,
                    "stock_quantity": CatalogProduct.stock_quantity + qty,
                }
                if approved
                else {
                    "pending_validation_quantity": CatalogProduct.pending_validation_quantity - qty,
                    "unfit_quantity": CatalogProduct.unfit_quantity + qty,
                }
            )
            await db.execute(
                update(CatalogProduct).where(CatalogProduct.id == item.catalog_product_id).values(**vals)
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 return_id=return_obj.id, movement_type=movement_type, qty=qty,
                 field="stock_quantity" if approved else "unfit_quantity",
                 delta=qty if approved else qty, created_by=user_id)
            _pg_ids.add(item.catalog_product_id)
        elif item.cmig_product_id:
            vals = (
                {
                    "pending_validation_quantity": CMIGProduct.pending_validation_quantity - qty,
                    "stock_quantity": CMIGProduct.stock_quantity + qty,
                }
                if approved
                else {
                    "pending_validation_quantity": CMIGProduct.pending_validation_quantity - qty,
                    "unfit_quantity": CMIGProduct.unfit_quantity + qty,
                }
            )
            await db.execute(
                update(CMIGProduct).where(CMIGProduct.id == item.cmig_product_id).values(**vals)
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 return_id=return_obj.id, movement_type=movement_type, qty=qty,
                 field="stock_quantity" if approved else "unfit_quantity",
                 delta=qty if approved else qty, created_by=user_id)
            _cmig_ids.add(item.cmig_product_id)

    if approved and (_pg_ids or _cmig_ids):
        from services.stock_sync_service import schedule_push
        schedule_push(_cmig_ids, _pg_ids)


# ─── Recompute de reservas a partir da trilha de auditoria ───────────────────

async def recompute_reservations_from_movements(db) -> dict:
    """Reconstrói reserved_quantity de todos os produtos a partir dos stock_movements.

    Necessário após executar SQL 74 (que zera reserved_quantity): replay das reservas
    ativas (pedidos com movimento 'reserve' mas sem 'unreserve', 'dispatch' ou 'await_return').
    """
    cancel = aliased(StockMovement, name="sm_cancel")

    # Reservas ativas: tem movimento 'reserve' sem movimento de encerramento correspondente.
    # Pedidos FULL NÃO reservam no galpão (reservam em full_stock) — se um pedido FULL
    # gerou uma reserva local (porque o shipping_mode ainda não estava classificado no
    # download), ela é espúria e é excluída aqui.
    result = await db.execute(
        select(
            StockMovement.product_type,
            StockMovement.product_id,
            func.sum(StockMovement.qty).label("active_reserved"),
        )
        .join(Order, Order.id == StockMovement.order_id)
        .where(
            StockMovement.movement_type == "reserve",
            StockMovement.product_type.in_(["pg", "cmig"]),
            StockMovement.order_id.is_not(None),
            or_(Order.shipping_mode.is_(None), Order.shipping_mode != "full"),  # L-012: coalesce(x,"") descarta NULL no Oracle
            ~exists(
                select(cancel.id).where(
                    cancel.order_id == StockMovement.order_id,
                    cancel.movement_type.in_(["unreserve", "dispatch", "await_return"]),
                    cancel.product_type == StockMovement.product_type,
                    cancel.product_id == StockMovement.product_id,
                )
            ),
        )
        .group_by(StockMovement.product_type, StockMovement.product_id)
    )
    rows = result.all()

    pg_updates: dict[int, int] = {}
    cmig_updates: dict[int, int] = {}
    for row in rows:
        qty = max(0, int(row.active_reserved or 0))
        if row.product_type == "pg":
            pg_updates[row.product_id] = qty
        elif row.product_type == "cmig":
            cmig_updates[row.product_id] = qty

    # Zera todos (cobre produtos cujas reservas foram integralmente encerradas)
    await db.execute(update(CatalogProduct).values(reserved_quantity=0))
    await db.execute(update(CMIGProduct).values(reserved_quantity=0))

    for product_id, qty in pg_updates.items():
        if qty > 0:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == product_id)
                .values(reserved_quantity=qty)
            )

    for product_id, qty in cmig_updates.items():
        if qty > 0:
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == product_id)
                .values(reserved_quantity=qty)
            )

    # ── Variantes ────────────────────────────────────────────────────────────
    # Reconstrói reserved_quantity das variantes a partir dos ITENS dos pedidos
    # cuja reserva-PAI está ativa (não FULL, com 'reserve' e sem fechamento no
    # nível do pai). NÃO usamos os movimentos variant_* porque alguns caminhos de
    # encerramento não logam a variante (mark_awaiting_return em pg/cmig e o
    # release órfão-FULL em cmig) — reconstruir a partir deles perpetuaria o
    # vazamento. A reserva-pai é a fonte confiável; cada OrderItem aponta sua
    # variante via catalog_variant_id + catalog_source ('pg' | 'cmig').
    cancel_v = aliased(StockMovement, name="sm_cancel_v")
    active_orders_subq = (
        select(StockMovement.order_id)
        .join(Order, Order.id == StockMovement.order_id)
        .where(
            StockMovement.movement_type == "reserve",
            StockMovement.product_type.in_(["pg", "cmig"]),
            StockMovement.order_id.is_not(None),
            or_(Order.shipping_mode.is_(None), Order.shipping_mode != "full"),  # L-012: coalesce(x,"") descarta NULL no Oracle
            ~exists(
                select(cancel_v.id).where(
                    cancel_v.order_id == StockMovement.order_id,
                    cancel_v.movement_type.in_(["unreserve", "dispatch", "await_return"]),
                    cancel_v.product_type == StockMovement.product_type,
                    cancel_v.product_id == StockMovement.product_id,
                )
            ),
        )
        .distinct()
        .subquery()
    )

    var_result = await db.execute(
        select(
            OrderItem.catalog_source,
            OrderItem.catalog_variant_id,
            func.sum(OrderItem.quantity).label("active_reserved"),
        )
        .where(
            OrderItem.catalog_variant_id.is_not(None),
            OrderItem.order_id.in_(select(active_orders_subq.c.order_id)),
        )
        .group_by(OrderItem.catalog_source, OrderItem.catalog_variant_id)
    )

    pg_var_updates: dict[int, int] = {}
    cmig_var_updates: dict[int, int] = {}
    for row in var_result.all():
        qty = max(0, int(row.active_reserved or 0))
        if row.catalog_source == "pg":
            pg_var_updates[row.catalog_variant_id] = qty
        elif row.catalog_source == "cmig":
            cmig_var_updates[row.catalog_variant_id] = qty

    # Zera todas (cobre variantes cujas reservas foram integralmente encerradas)
    await db.execute(update(CatalogProductVariant).values(reserved_quantity=0))
    await db.execute(update(CMIGProductVariant).values(reserved_quantity=0))

    for variant_id, qty in pg_var_updates.items():
        if qty > 0:
            await db.execute(
                update(CatalogProductVariant)
                .where(CatalogProductVariant.id == variant_id)
                .values(reserved_quantity=qty)
            )

    for variant_id, qty in cmig_var_updates.items():
        if qty > 0:
            await db.execute(
                update(CMIGProductVariant)
                .where(CMIGProductVariant.id == variant_id)
                .values(reserved_quantity=qty)
            )

    await db.commit()
    return {
        "pg_products_updated": len(pg_updates),
        "cmig_products_updated": len(cmig_updates),
        "pg_variants_updated": len(pg_var_updates),
        "cmig_variants_updated": len(cmig_var_updates),
    }


# ─── Backfill de reservas órfãs ──────────────────────────────────────────────

async def backfill_orphan_reservations(
    db,
    *,
    dry_run: bool = True,
    dropshipper_id: int | None = None,
    limit: int = 1000,
) -> dict:
    """Libera reservas órfãs de pedidos não-FULL já entregues no ML.

    Sintoma: pedido com `shipment_status IN ('shipped','delivered')` que ainda tem
    movimento 'reserve' sem fechamento ('unreserve'/'dispatch'/'await_return') — a
    reserva nunca foi liberada, então `available = stock - reserved` fica subestimado.

    IMPORTANTE: NÃO toca no estoque físico. `stock_quantity` de PG/CMIG é
    event-sourced (services/fiscal/stock_calculator) — o pedido entregue já é a
    saída canônica do estoque. Decrementar aqui (via confirm_dispatch) causaria
    DUPLA CONTAGEM, sobrescrita no próximo recompute. Por isso liberamos apenas
    `reserved_quantity` via `release_reservation` (loga movimento 'unreserve').

    - dry_run=True (default): NÃO grava nada; só devolve o relatório do que faria.
    - dry_run=False: roda `release_reservation` (idempotente) para cada pedido.
    """
    cancel = aliased(StockMovement, name="sm_close_bf")
    q = (
        select(StockMovement.order_id)
        .join(Order, Order.id == StockMovement.order_id)
        .where(
            StockMovement.movement_type == "reserve",
            StockMovement.product_type.in_(["pg", "cmig"]),
            StockMovement.order_id.is_not(None),
            or_(Order.shipping_mode.is_(None), Order.shipping_mode != "full"),  # L-012: coalesce(x,"") descarta NULL no Oracle
            Order.status != "cancelled",
            func.coalesce(Order.shipment_status, "").in_(["shipped", "delivered"]),
            ~exists(
                select(cancel.id).where(
                    cancel.order_id == StockMovement.order_id,
                    cancel.movement_type.in_(["unreserve", "dispatch", "await_return"]),
                    cancel.product_type == StockMovement.product_type,
                    cancel.product_id == StockMovement.product_id,
                )
            ),
        )
    )
    if dropshipper_id is not None:
        q = q.where(Order.dropshipper_id == dropshipper_id)
    q = q.distinct().limit(limit)

    res = await db.execute(q)
    order_ids = [r[0] for r in res.all()]

    if not order_ids:
        return {"dry_run": dry_run, "orders_found": 0, "orders": [], "products": []}

    # Carrega pedidos + itens.
    ord_res = await db.execute(select(Order).where(Order.id.in_(order_ids)))
    orders = list(ord_res.scalars().all())
    items_res = await db.execute(select(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    items = list(items_res.scalars().all())

    # Agrega qty de reserva a liberar por produto (mesma regra de reserve_stock:
    # catalog_product_id → pg; senão cmig_product_id → cmig).
    deltas: dict[tuple[str, int], int] = {}
    orders_report = []
    items_by_order: dict[int, list] = {}
    for it in items:
        items_by_order.setdefault(it.order_id, []).append(it)
        qty = it.quantity or 1
        if it.catalog_product_id:
            deltas[("pg", it.catalog_product_id)] = deltas.get(("pg", it.catalog_product_id), 0) + qty
        elif it.cmig_product_id:
            deltas[("cmig", it.cmig_product_id)] = deltas.get(("cmig", it.cmig_product_id), 0) + qty

    for o in orders:
        orders_report.append({
            "order_id": o.id,
            "platform_order_id": o.platform_order_id,
            "shipping_mode": o.shipping_mode,
            "shipment_status": o.shipment_status,
            "status": o.status,
            "items": [
                {"sku": it.sku, "qty": it.quantity or 1,
                 "product_type": "pg" if it.catalog_product_id else ("cmig" if it.cmig_product_id else None)}
                for it in items_by_order.get(o.id, [])
            ],
        })

    # Estado atual de reserved_quantity dos produtos afetados (pra projeção).
    pg_ids = [pid for (t, pid) in deltas if t == "pg"]
    cmig_ids = [pid for (t, pid) in deltas if t == "cmig"]
    cur: dict[tuple[str, int], dict] = {}
    if pg_ids:
        for p in (await db.execute(select(CatalogProduct).where(CatalogProduct.id.in_(pg_ids)))).scalars():
            cur[("pg", p.id)] = {"sku": p.sku, "reserved": int(p.reserved_quantity or 0)}
    if cmig_ids:
        for p in (await db.execute(select(CMIGProduct).where(CMIGProduct.id.in_(cmig_ids)))).scalars():
            cur[("cmig", p.id)] = {"sku": p.sku, "reserved": int(p.reserved_quantity or 0)}

    products_report = []
    for (ptype, pid), qty in deltas.items():
        c = cur.get((ptype, pid), {"sku": None, "reserved": 0})
        products_report.append({
            "product_type": ptype, "product_id": pid, "sku": c["sku"],
            "reserved_to_release": qty,
            "reserved_before": c["reserved"],
            "reserved_after": c["reserved"] - qty,  # release_reservation não trava em 0
        })

    if not dry_run:
        for o in orders:
            try:
                await release_reservation(db, o)  # idempotente, faz commit próprio
            except Exception as exc:
                logger.error("backfill release_reservation order=%s: %s", o.id, exc)

    return {
        "dry_run": dry_run,
        "orders_found": len(orders),
        "products_affected": len(products_report),
        "orders": orders_report,
        "products": products_report,
    }

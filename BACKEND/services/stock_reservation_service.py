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

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct, CMIGProductVariant
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


# ─── Reserva ──────────────────────────────────────────────────────────────────

async def reserve_stock(db: AsyncSession, order: Order) -> None:
    """Pedido baixado (downloaded) → reserva o estoque dos produtos vinculados."""
    if order.shipping_mode == "full":
        return  # FULL orders não reservam galpão
    if order.status == "cancelled":
        return
    if await _already_has_movement(db, order.id, "reserve"):
        return

    items = await _get_order_items(db, order)
    for item in items:
        qty = item.quantity or 1
        reserved = False

        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(reserved_quantity=CatalogProduct.reserved_quantity + qty)
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 order_id=order.id, movement_type="reserve", qty=qty,
                 field="reserved_quantity", delta=qty)
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
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(reserved_quantity=CMIGProduct.reserved_quantity + qty)
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 order_id=order.id, movement_type="reserve", qty=qty,
                 field="reserved_quantity", delta=qty)

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
    except Exception as exc:
        logger.error("reserve_stock order=%s: %s", order.id, exc)


# ─── Liberação de reserva (cancelamento antes do despacho) ───────────────────

async def release_reservation(db: AsyncSession, order: Order) -> None:
    """Pedido cancelado ANTES de ser despachado → libera a reserva de volta ao disponível."""
    if order.shipping_mode == "full":
        return  # FULL orders não têm reserva de galpão para liberar
    if await _already_has_movement(db, order.id, "unreserve"):
        return

    items = await _get_order_items(db, order)
    for item in items:
        qty = item.quantity or 1
        released = False

        if item.catalog_product_id:
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(reserved_quantity=CatalogProduct.reserved_quantity - qty)
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 order_id=order.id, movement_type="unreserve", qty=qty,
                 field="reserved_quantity", delta=-qty)
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
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(reserved_quantity=CMIGProduct.reserved_quantity - qty)
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 order_id=order.id, movement_type="unreserve", qty=qty,
                 field="reserved_quantity", delta=-qty)

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
    except Exception as exc:
        logger.error("release_reservation order=%s: %s", order.id, exc)


# ─── Confirmação de despacho ──────────────────────────────────────────────────

async def confirm_dispatch(db: AsyncSession, order: Order) -> None:
    """Pedido despachado/shipped → debita estoque físico e libera reserva."""
    if order.shipping_mode == "full":
        from services.full_stock_service import apply_full_order_shipped
        try:
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
            await db.execute(
                update(CatalogProduct)
                .where(CatalogProduct.id == item.catalog_product_id)
                .values(
                    stock_quantity=CatalogProduct.stock_quantity - qty,
                    reserved_quantity=CatalogProduct.reserved_quantity - qty,
                )
            )
            _log(db, product_type="pg", product_id=item.catalog_product_id,
                 order_id=order.id, movement_type="dispatch", qty=qty,
                 field="stock_quantity", delta=-qty)
            _pg_ids.add(item.catalog_product_id)
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
            await db.execute(
                update(CMIGProduct)
                .where(CMIGProduct.id == item.cmig_product_id)
                .values(
                    stock_quantity=CMIGProduct.stock_quantity - qty,
                    reserved_quantity=CMIGProduct.reserved_quantity - qty,
                )
            )
            _log(db, product_type="cmig", product_id=item.cmig_product_id,
                 order_id=order.id, movement_type="dispatch", qty=qty,
                 field="stock_quantity", delta=-qty)
            _cmig_ids.add(item.cmig_product_id)

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

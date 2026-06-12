"""Job de polling do status dos pedidos enviados ao eShip.

Registrado em tasks/scheduler.py. Como o eShip não tem webhook, varremos os
pedidos com eship_order_id ainda não finalizados e consultamos o status.
"""

import logging

from sqlalchemy import select

from database import task_db
from models.order import Order
from tasks._job_wrapper import tracked_job

from . import service

logger = logging.getLogger(__name__)

# Estados em que não vale mais consultar o eShip.
TERMINAL_SHIPMENT = ("delivered", "not_delivered", "cancelled")


async def sync_eship_status() -> None:
    async with tracked_job("eship_status") as result:
        stats = {"checked": 0, "updated": 0, "failed": 0}
        async with task_db() as db:
            rows = (
                await db.execute(
                    select(Order).where(
                        Order.eship_order_id.isnot(None),
                        Order.shipment_status.notin_(TERMINAL_SHIPMENT)
                        | (Order.shipment_status.is_(None)),
                    )
                )
            ).scalars().all()

            for order in rows:
                stats["checked"] += 1
                try:
                    if await service.sync_order_status(db, order):
                        stats["updated"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    logger.warning("[eShip] sync status pedido %s falhou: %s", order.id, e)

        result.set(stats)

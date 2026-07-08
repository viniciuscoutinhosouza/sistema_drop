"""Job de manutenção: libera reservas órfãs de pedidos não-FULL já entregues.

Safety-net do fix de causa-raiz (webhook_service libera a reserva na criação de pedidos
já despachados). Cobre casos de borda (relink pós-entrega, sync que não observou a
transição, backfill de dados antigos). Idempotente: só libera reserva sem 'unreserve';
NÃO toca no estoque físico (event-sourced). Ver backfill_orphan_reservations.
"""

import logging

from database import task_db
from services.stock_reservation_service import backfill_orphan_reservations

logger = logging.getLogger(__name__)


async def run_release_orphan_reservations() -> None:
    try:
        async with task_db() as db:
            rep = await backfill_orphan_reservations(db, dry_run=False, limit=5000)
        found = rep.get("orders_found", 0)
        if found:
            logger.info(
                "[orphan-reservations] liberadas: pedidos=%s produtos=%s",
                found, rep.get("products_affected"),
            )
    except Exception:
        logger.exception("[orphan-reservations] job falhou")

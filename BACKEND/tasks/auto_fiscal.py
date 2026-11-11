"""Background task: emissão AUTOMÁTICA de NF-e dos pedidos armados (ADR-0041).

Varre os pedidos na "lane" automática (`auto_fiscal_status` in emitting|emitted) e avança cada um
(emitir → finalizar) via `services.auto_fiscal_dispatch.process_order`. O ato fiscal e as travas
vivem no serviço (reusa o roteador único como ator de sistema); aqui é só o loop resiliente.

Cadência própria (a cada 5 min) — mais ágil que o `sync_orders`/`sync_pending_nfe` (15 min) porque
a emissão é o gargalo que o dono quer imediato. A convergência de `nfe_status` com o `sync_pending_nfe`
é benigna (ambos escrevem a MESMA verdade do ML); a dupla-EMISSÃO é barrada pelo claim atômico
(`arm_if_eligible`) + guard de unicidade antes do ato fiscal.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from database import task_db
from models.order import Order
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)

# Janela: pedido fica pouco tempo na lane (emite em minutos/horas). Varrer histórico seria inútil.
_JANELA_DIAS = 15


async def run_auto_fiscal():
    async with tracked_job("auto_fiscal") as result:
        from services.auto_fiscal_dispatch import process_order

        stats = {"checked": 0, "advanced": 0, "errors": 0}
        desde = datetime.now(UTC) - timedelta(days=_JANELA_DIAS)

        async with task_db() as db:
            orders = list(
                (
                    await db.execute(
                        select(Order).where(
                            Order.auto_fiscal_status.in_(("emitting", "emitted")),
                            Order.status != "cancelled",
                            Order.created_at >= desde,
                        )
                    )
                )
                .scalars()
                .all()
            )
            stats["checked"] = len(orders)

            for order in orders:
                before = order.auto_fiscal_status
                try:
                    await process_order(db, order)
                    if order.auto_fiscal_status != before:
                        stats["advanced"] += 1
                except Exception as e:  # noqa: BLE001 — um pedido não derruba o job
                    stats["errors"] += 1
                    logger.warning("[auto_fiscal] order=%s error: %s", order.id, e)
                    # Falhar alto, nunca em silêncio: superfície o erro no pedido (best-effort, sem PII).
                    try:
                        from services.auto_fiscal_dispatch import sanitize_fiscal_msg

                        order.auto_fiscal_error = sanitize_fiscal_msg(e)
                        await db.commit()
                    except Exception:  # noqa: BLE001 — sessão já ruim: não mascara o erro original
                        await db.rollback()

        result.set(stats)
        return stats

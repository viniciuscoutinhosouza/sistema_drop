"""Job diário: sincroniza TODAS as NF-e do MÊS ATUAL de cada conta ML (batch do
Faturador ML), incluindo as remessas para o FULL que o sync por pedido não pega.

Idempotente (dedup por chave de acesso) — se falhar/errar num dia, a execução do
dia seguinte corrige. Sequencial por conta (o batch é sensível a 429). Os furos de
sequência são detectados e logados por `_sync_ml_fiscal_account`.
"""

import logging
from datetime import datetime

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from services.datetime_br import BR_TZ as _BRT  # fonte única do fuso do Brasil
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


async def sync_ml_fiscal_current_month():
    """Entry point do scheduler: sincroniza o mês atual (BRT) de todas as contas ML ativas."""
    async with tracked_job("sync_ml_fiscal") as job_result:
        now = datetime.now(_BRT)
        year, month = now.year, now.month
        stats = {"accounts": 0, "created": 0, "full_moved": 0, "gaps": 0, "errors": 0}

        async with task_db() as db:
            accounts = (
                await db.execute(
                    select(MarketplaceAccount.id, MarketplaceAccount.cmig_id).where(
                        MarketplaceAccount.platform == "mercadolivre",
                        MarketplaceAccount.is_active == True,  # noqa: E712
                        MarketplaceAccount.access_token.isnot(None),
                        MarketplaceAccount.cmig_id.isnot(None),
                    )
                )
            ).all()

        # Import tardio: routers.invoices já está carregado pelo app; evita ciclo no import.
        from routers.invoices import _sync_ml_fiscal_account

        for acc_id, cmig_id in accounts:
            try:
                r = await _sync_ml_fiscal_account(acc_id, cmig_id, year, month, None)
                stats["accounts"] += 1
                stats["created"] += r.get("created", 0)
                stats["full_moved"] += r.get("full_moved", 0)
                stats["gaps"] += sum(len(v) for v in (r.get("gaps") or {}).values())
            except Exception as e:  # noqa: BLE001 — tolerância por conta
                stats["errors"] += 1
                logger.error("[sync_ml_fiscal] conta %s: %s", acc_id, e)

        job_result.set(stats)

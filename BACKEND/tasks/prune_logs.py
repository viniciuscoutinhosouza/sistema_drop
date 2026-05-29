"""Housekeeping diário — remove execuções de jobs com mais de 30 dias.

Mantém a tabela `scheduler_job_executions` em tamanho razoável e a tela
de monitoramento responsiva. Executa às 04:00 UTC.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from database import task_db
from models.scheduler_job_execution import SchedulerJobExecution
from tasks._job_wrapper import tracked_job

log = logging.getLogger(__name__)

RETENTION_DAYS = 30


async def prune_job_executions():
    async with tracked_job("prune_job_executions") as result:
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        async with task_db() as db:
            exec_result = await db.execute(
                delete(SchedulerJobExecution).where(
                    SchedulerJobExecution.started_at < cutoff
                )
            )
            rows_deleted = exec_result.rowcount or 0
            await db.commit()
        log.info("prune_job_executions: %d linhas removidas (cutoff=%s)", rows_deleted, cutoff)
        result.set({"rows_deleted": rows_deleted, "retention_days": RETENTION_DAYS})

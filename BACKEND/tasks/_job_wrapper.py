"""Wrapper de execução de jobs para gravar histórico em `scheduler_job_executions`.

Cada job no `tasks/` envolve seu corpo com `async with tracked_job("job_id"): ...`
e devolve um `dict` de contadores (ou nada). O wrapper grava 1 linha por execução
com `started_at`, `finished_at`, `duration_ms`, `status` e `result_json`.

A sessão de log é independente da sessão do job — falhas no job não impedem
o registro do erro, e rollbacks no job não destroem o log.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update

from database import task_db
from models.scheduler_job_execution import SchedulerJobExecution

log = logging.getLogger(__name__)

_MAX_ERROR_LEN = 3900  # VARCHAR2(4000) com folga


def _serialize_result(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


class _JobResult:
    """Captura o `dict` de contadores retornado pelo corpo do job."""

    def __init__(self) -> None:
        self.data: dict | None = None

    def set(self, data: dict | None) -> None:
        self.data = data


@asynccontextmanager
async def tracked_job(job_id: str, triggered_by: str = "scheduler"):
    """Context manager que grava execução do job (running → success/failed).

    Uso:
        async with tracked_job("sync_orders") as result:
            ...
            result.set({"orders_created": 5})

    Em caso de exceção dentro do bloco, a exceção é re-raised após gravar
    status='failed' + error_message (não engole erros do scheduler).
    """
    started_at = datetime.now(UTC)
    perf_start = time.perf_counter()
    execution_id: int | None = None

    try:
        async with task_db() as db:
            row = SchedulerJobExecution(
                job_id=job_id,
                started_at=started_at,
                status="running",
                triggered_by=triggered_by,
            )
            db.add(row)
            await db.flush()
            execution_id = row.id
            await db.commit()
    except Exception as exc:
        log.exception("[tracked_job] Falha ao registrar início de %s: %s", job_id, exc)

    result = _JobResult()
    error: Exception | None = None
    try:
        yield result
    except Exception as exc:
        error = exc
    finally:
        duration_ms = int((time.perf_counter() - perf_start) * 1000)
        finished_at = datetime.now(UTC)
        status = "failed" if error else "success"
        error_message = None
        if error:
            tb = traceback.format_exc()
            error_message = (f"{type(error).__name__}: {error}\n{tb}")[:_MAX_ERROR_LEN]

        if execution_id is not None:
            try:
                async with task_db() as db:
                    await db.execute(
                        update(SchedulerJobExecution)
                        .where(SchedulerJobExecution.id == execution_id)
                        .values(
                            finished_at=finished_at,
                            duration_ms=duration_ms,
                            status=status,
                            result_json=_serialize_result(result.data),
                            error_message=error_message,
                        )
                    )
                    await db.commit()
            except Exception as log_exc:
                log.exception("[tracked_job] Falha ao gravar fim de %s: %s", job_id, log_exc)
        else:
            # Tenta inserir do zero quando não conseguimos registrar o início
            try:
                async with task_db() as db:
                    row = SchedulerJobExecution(
                        job_id=job_id,
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_ms=duration_ms,
                        status=status,
                        result_json=_serialize_result(result.data),
                        error_message=error_message,
                        triggered_by=triggered_by,
                    )
                    db.add(row)
                    await db.commit()
            except Exception as log_exc:
                log.exception(
                    "[tracked_job] Falha ao gravar execução de %s sem ID prévio: %s",
                    job_id,
                    log_exc,
                )

        if error:
            raise error

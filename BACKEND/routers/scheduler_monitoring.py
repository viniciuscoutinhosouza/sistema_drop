"""Tela de monitoramento de rotinas automatizadas.

Endpoints acessíveis por roles `ugo`, `go` e `admin`. Mostram:
- Status agregado de cada rotina (success rate, duração média, próxima execução)
- Histórico paginado de execuções, com filtros de período/job/status
- Detalhe individual de uma execução (resultado completo + traceback)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.scheduler_job_execution import SchedulerJobExecution
from models.user import User

router = APIRouter()

# Catálogo estático: descrição amigável + frequência declarada.
# Espelha o que está em tasks/scheduler.py — manter sincronizado ao adicionar/remover jobs.
JOB_CATALOG: list[dict[str, Any]] = [
    {
        "job_id": "sync_orders",
        "name": "Sync de Pedidos (ML + Shopee)",
        "schedule": "A cada 15 min",
        "type": "interval",
    },
    {
        "job_id": "refresh_tokens",
        "name": "Refresh de Tokens OAuth",
        "schedule": "A cada 1h",
        "type": "interval",
    },
    {
        "job_id": "sync_stock",
        "name": "Sync de Estoque para Marketplaces",
        "schedule": "A cada 30 min",
        "type": "interval",
    },
    {
        "job_id": "sync_dfe",
        "name": "Sync de DFe (NFes recebidas via Focus)",
        "schedule": "A cada 30 min",
        "type": "interval",
    },
    {
        "job_id": "sync_messages",
        "name": "Sync de Mensagens e Perguntas ML",
        "schedule": "A cada 15 min",
        "type": "interval",
    },
    {
        "job_id": "check_subscriptions",
        "name": "Verificação de Mensalidades Vencidas",
        "schedule": "Diário às 00:00 UTC",
        "type": "cron",
    },
    {
        "job_id": "fiscal_alerts",
        "name": "Alertas Fiscais (certificados + invoices stale)",
        "schedule": "Diário às 09:00 UTC",
        "type": "cron",
    },
    {
        "job_id": "refresh_ml_reputation",
        "name": "Refresh de Reputação ML (medalhas)",
        "schedule": "Diário às 03:15 UTC",
        "type": "cron",
    },
    {
        "job_id": "stock_recompute_on_order",
        "name": "Recálculo de Estoque por Pedido (event-driven)",
        "schedule": "A cada pedido criado",
        "type": "event",
    },
    {
        "job_id": "prune_job_executions",
        "name": "Limpeza de execuções antigas (30 dias)",
        "schedule": "Diário às 04:00 UTC",
        "type": "cron",
    },
]


def _serialize(row: SchedulerJobExecution, *, include_full_error: bool = False) -> dict:
    """Converte uma linha em dict JSON-friendly."""
    result_data: Any = None
    if row.result_json:
        try:
            result_data = json.loads(row.result_json)
        except Exception:
            result_data = {"raw": str(row.result_json)}

    err = row.error_message or None
    if err and not include_full_error and len(err) > 200:
        err = err[:200] + "…"

    return {
        "id": row.id,
        "job_id": row.job_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": int(row.duration_ms) if row.duration_ms is not None else None,
        "status": row.status,
        "result": result_data,
        "error_message": err,
        "triggered_by": row.triggered_by,
    }


def _next_run_for(job_id: str) -> str | None:
    """Lê o próximo agendamento do APScheduler (None se job não estiver agendado)."""
    try:
        from tasks.scheduler import scheduler

        job = scheduler.get_job(job_id)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
    except Exception:
        pass
    return None


@router.get("/jobs")
async def list_jobs(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("ugo", "go", "admin")),
):
    """Lista as rotinas conhecidas com KPIs agregados no período (default últimas 24h)."""
    period_start = datetime.now(UTC) - timedelta(hours=hours)

    # Agregado por job_id no período
    agg_q = await db.execute(
        select(
            SchedulerJobExecution.job_id,
            func.count(SchedulerJobExecution.id).label("total"),
            func.sum(
                case((SchedulerJobExecution.status == "success", 1), else_=0)
            ).label("successes"),
            func.sum(
                case((SchedulerJobExecution.status == "failed", 1), else_=0)
            ).label("failures"),
            func.sum(
                case((SchedulerJobExecution.status == "running", 1), else_=0)
            ).label("runnings"),
            func.avg(SchedulerJobExecution.duration_ms).label("avg_duration_ms"),
        )
        .where(SchedulerJobExecution.started_at >= period_start)
        .group_by(SchedulerJobExecution.job_id)
    )
    agg_by_job: dict[str, dict] = {}
    for row in agg_q.all():
        agg_by_job[row.job_id] = {
            "total": int(row.total or 0),
            "successes": int(row.successes or 0),
            "failures": int(row.failures or 0),
            "runnings": int(row.runnings or 0),
            "avg_duration_ms": int(row.avg_duration_ms) if row.avg_duration_ms is not None else None,
        }

    # Última execução por job_id
    sub = (
        select(
            SchedulerJobExecution.job_id,
            func.max(SchedulerJobExecution.started_at).label("max_started"),
        )
        .group_by(SchedulerJobExecution.job_id)
        .subquery()
    )
    last_q = await db.execute(
        select(SchedulerJobExecution)
        .join(
            sub,
            and_(
                SchedulerJobExecution.job_id == sub.c.job_id,
                SchedulerJobExecution.started_at == sub.c.max_started,
            ),
        )
    )
    last_by_job: dict[str, SchedulerJobExecution] = {}
    for row in last_q.scalars().all():
        last_by_job[row.job_id] = row

    jobs_out = []
    for spec in JOB_CATALOG:
        jid = spec["job_id"]
        agg = agg_by_job.get(jid, {})
        total = agg.get("total", 0)
        successes = agg.get("successes", 0)
        success_rate = round((successes / total) * 100, 1) if total else None
        last_row = last_by_job.get(jid)
        jobs_out.append(
            {
                **spec,
                "executions_in_period": total,
                "successes": successes,
                "failures": agg.get("failures", 0),
                "runnings": agg.get("runnings", 0),
                "success_rate": success_rate,
                "avg_duration_ms": agg.get("avg_duration_ms"),
                "last_run": _serialize(last_row) if last_row else None,
                "next_run_at": _next_run_for(jid),
            }
        )

    return {
        "period_hours": hours,
        "period_start": period_start.isoformat(),
        "jobs": jobs_out,
    }


@router.get("/executions")
async def list_executions(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    job_id: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("ugo", "go", "admin")),
):
    """Histórico paginado de execuções. Default: últimas 3 horas."""
    if date_from is None and date_to is None:
        date_from = datetime.now(UTC) - timedelta(hours=3)

    where = []
    if date_from is not None:
        where.append(SchedulerJobExecution.started_at >= date_from)
    if date_to is not None:
        where.append(SchedulerJobExecution.started_at <= date_to)
    if job_id:
        where.append(SchedulerJobExecution.job_id == job_id)
    if status:
        if status not in ("running", "success", "failed"):
            raise HTTPException(status_code=400, detail="status inválido")
        where.append(SchedulerJobExecution.status == status)

    total_q = await db.execute(
        select(func.count(SchedulerJobExecution.id)).where(and_(*where) if where else True)
    )
    total = int(total_q.scalar() or 0)

    rows_q = await db.execute(
        select(SchedulerJobExecution)
        .where(and_(*where) if where else True)
        .order_by(desc(SchedulerJobExecution.started_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = rows_q.scalars().all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_serialize(r) for r in rows],
    }


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("ugo", "go", "admin")),
):
    """Detalhe individual de uma execução, com result_json e error_message completos."""
    row = (
        await db.execute(
            select(SchedulerJobExecution).where(SchedulerJobExecution.id == execution_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return _serialize(row, include_full_error=True)

"""Ponto ÚNICO de escopo por galpão (ADR-0026) — evita a divergência que vazou PG entre galpões.

Regra: admin é global; demais só enxergam os galpões a que pertencem. `go`/`ugo`/`ac` com
`warehouse_id` → esse galpão; `ac` sem `warehouse_id` → galpões das CMIGs que possui (owner_ac_id).
Fail-closed: quem não resolve nenhum galpão → set vazio (não global).

Convenção de retorno das funções: `None` = admin (sem filtro/todos); `set()` = nenhum (fail-closed);
`{ids}` = filtrar por esses galpões.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def warehouse_ids_for(user, db: AsyncSession) -> set[int] | None:
    """Galpões que o usuário enxerga (escopo geral: categorias, PG-base, etc.)."""
    if getattr(user, "role", None) == "admin":
        return None
    if getattr(user, "warehouse_id", None) is not None:
        return {user.warehouse_id}
    # `ac` sem warehouse_id → galpões das CMIGs que possui.
    from models.cmig import CMIG

    rows = (
        await db.execute(select(CMIG.warehouse_id).where(CMIG.owner_ac_id == user.id))
    ).scalars().all()
    return {w for w in rows if w is not None}


async def sellable_pg_warehouse_ids(user, db: AsyncSession) -> set[int] | None:
    """Galpões dos quais o usuário pode VER/vender PG: o escopo, EXCLUINDO galpões `multilojas`
    (multilojas só vende a própria CMIG — publicar/vender PG é bloqueado, ADR-0024).

    `None` = admin (todos). `set()` = nenhum PG (inclui o caso multilojas puro → seletor vazio)."""
    ids = await warehouse_ids_for(user, db)
    if ids is None:
        return None
    if not ids:
        return set()
    from models.warehouse import Warehouse

    rows = (
        await db.execute(
            select(Warehouse.id, Warehouse.work_type).where(Warehouse.id.in_(ids))
        )
    ).all()
    return {wid for (wid, work_type) in rows if work_type != "multilojas"}

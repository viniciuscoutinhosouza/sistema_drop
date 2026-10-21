"""Extrato de Crédito CMIG × Galpão (Fase 4, ADR-0034).

Saldo que a CMIG mantém com o Galpão para cobrir vendas de PG antes da entrega. Ponto único
de cálculo em `services/credit_service`. Isolamento por Galpão (ADR-0026) + por CMIG:
  - GET (ver): admin, OU operador/dono do Galpão, OU administrador da CMIG;
  - POST (lançar): admin OU lado do Galpão (quem confirma o depósito recebido).
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.cmig import CMIG, CMIGAdministrator
from models.user import User
from models.warehouse import Warehouse
from routers.warehouse import _can_access_warehouse, _owned_go_id
from services import credit_service

router = APIRouter()


def _serialize(e) -> dict:
    return {
        "id": e.id,
        "cmig_id": e.cmig_id,
        "warehouse_id": e.warehouse_id,
        "entry_type": e.entry_type,
        "amount": float(e.amount or 0),
        "order_id": e.order_id,
        "description": e.description,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


async def _warehouse_side(user: User, warehouse_id: int, db: AsyncSession) -> bool:
    """True se o usuário é admin ou tem acesso ao Galpão (operador/dono) — ADR-0026."""
    if user.role == "admin":
        return True
    w = (
        await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    ).scalar_one_or_none()
    return bool(w and _can_access_warehouse(user, w, await _owned_go_id(user, db)))


async def _resolve_pair(cmig_id: int, warehouse_id: int | None, user: User, db: AsyncSession):
    """Valida o par (cmig, galpão) e o acesso de LEITURA. Devolve (cmig, warehouse_id)."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    if not cmig.warehouse_id:
        raise HTTPException(status_code=400, detail="CMIG sem Galpão vinculado")
    if warehouse_id is not None and warehouse_id != cmig.warehouse_id:
        raise HTTPException(status_code=400, detail="Par CMIG×Galpão inconsistente")
    warehouse_id = cmig.warehouse_id

    if await _warehouse_side(user, warehouse_id, db):
        return cmig, warehouse_id
    # Lado CMIG: administrador da CMIG também pode ver.
    acc = (
        await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig_id
            )
        )
    ).scalar_one_or_none()
    if acc:
        return cmig, warehouse_id
    raise HTTPException(status_code=403, detail="Sem acesso ao crédito desta CMIG/Galpão")


@router.get("")
async def get_statement(
    cmig_id: int = Query(...),
    warehouse_id: int | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saldo + lançamentos do crédito do par CMIG×Galpão."""
    cmig, wh_id = await _resolve_pair(cmig_id, warehouse_id, current_user, db)
    balance = await credit_service.get_balance(db, cmig_id, wh_id)
    rows = await credit_service.list_entries(db, cmig_id, wh_id, limit=limit, offset=offset)
    return {
        "cmig_id": cmig_id,
        "warehouse_id": wh_id,
        "balance": float(balance),
        "entries": [_serialize(e) for e in rows],
    }


@router.post("", status_code=201)
async def add_entry(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lança um crédito/débito manual. Só admin ou o lado do Galpão (quem confirma o depósito)."""
    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=400, detail="cmig_id é obrigatório")
    cmig, wh_id = await _resolve_pair(cmig_id, body.get("warehouse_id"), current_user, db)
    if not await _warehouse_side(current_user, wh_id, db):
        raise HTTPException(
            status_code=403, detail="Apenas o Galpão (ou admin) pode lançar crédito/débito"
        )
    entry_type = (body.get("entry_type") or "").lower()
    if entry_type not in ("credit", "debit"):
        raise HTTPException(status_code=400, detail="entry_type deve ser 'credit' ou 'debit'")
    try:
        amount = Decimal(str(body.get("amount")))
    except Exception:
        raise HTTPException(status_code=400, detail="amount inválido") from None
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount deve ser maior que zero")
    entry = await credit_service.add_entry(
        db,
        cmig_id=cmig_id,
        warehouse_id=wh_id,
        entry_type=entry_type,
        amount=amount,
        description=(body.get("description") or None),
        created_by=current_user.id,
    )
    balance = await credit_service.get_balance(db, cmig_id, wh_id)
    return {"entry": _serialize(entry), "balance": float(balance)}

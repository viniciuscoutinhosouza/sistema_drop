"""Extrato de Crédito do CLIENTE (comprador) × CMIG (ADR-0037).

Passivo com o cliente final: quando um pedido PAGO é cancelado, cria-se um crédito a favor
do cliente; o operador depois devolve o dinheiro (ou abate numa compra) lançando um débito.
Ponto único de cálculo em `services/customer_credit_service`. Escopo por CMIG/Galpão (ADR-0026)
via `assert_cmig_access`:
  - GET (ver): quem tem acesso à CMIG (admin / galpão dono do CMIG / administrador da CMIG);
  - POST (lançar): acesso à CMIG + permissão de ação `credito_cliente_gerenciar` (ADR-0036).
Append-only: sem UPDATE/DELETE (razão imutável).
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_permission
from models.cmig import CMIG
from models.person import Person
from models.user import User
from services import customer_credit_service
from services.data_scope import assert_cmig_access

router = APIRouter()


def _serialize(e) -> dict:
    return {
        "id": e.id,
        "cmig_id": e.cmig_id,
        "person_id": e.person_id,
        "entry_type": e.entry_type,
        "amount": float(e.amount or 0),
        "order_id": e.order_id,
        "description": e.description,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


async def _resolve_scope(cmig_id: int, person_id: int, user: User, db: AsyncSession):
    """Valida CMIG + acesso + que o cliente pertence à CMIG. Devolve (cmig, person)."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await assert_cmig_access(cmig, user, db)
    person = (await db.execute(select(Person).where(Person.id == person_id))).scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if person.cmig_id != cmig_id:
        raise HTTPException(status_code=400, detail="Cliente não pertence a esta CMIG")
    return cmig, person


@router.get("")
async def get_statement(
    cmig_id: int = Query(...),
    person_id: int = Query(...),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saldo + lançamentos do crédito do par cliente×CMIG."""
    cmig, person = await _resolve_scope(cmig_id, person_id, current_user, db)
    balance = await customer_credit_service.get_balance(db, cmig_id, person_id)
    rows = await customer_credit_service.list_entries(db, cmig_id, person_id, limit=limit, offset=offset)
    return {
        "cmig_id": cmig_id,
        "person_id": person_id,
        "customer_name": person.name,
        "balance": float(balance),
        "entries": [_serialize(e) for e in rows],
    }


@router.post("", status_code=201)
async def add_entry(
    body: dict,
    current_user: User = Depends(require_permission("credito_cliente_gerenciar")),
    db: AsyncSession = Depends(get_db),
):
    """Lança um crédito/débito manual do cliente (ex.: operador registra a devolução do valor)."""
    cmig_id = body.get("cmig_id")
    person_id = body.get("person_id")
    if not cmig_id or not person_id:
        raise HTTPException(status_code=400, detail="cmig_id e person_id são obrigatórios")
    await _resolve_scope(cmig_id, person_id, current_user, db)
    entry_type = (body.get("entry_type") or "").lower()
    if entry_type not in ("credit", "debit"):
        raise HTTPException(status_code=400, detail="entry_type deve ser 'credit' ou 'debit'")
    try:
        amount = Decimal(str(body.get("amount")))
    except Exception:
        raise HTTPException(status_code=400, detail="amount inválido") from None
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount deve ser maior que zero")
    # Se amarrar a um pedido, ele TEM de ser da mesma CMIG (senão envenena a idempotência por
    # order_id e vincula o razão a pedido de outro escopo). Fail-closed.
    order_id = body.get("order_id")
    if order_id is not None:
        from models.order import Order

        ok = (
            await db.execute(
                select(Order.id).where(Order.id == order_id, Order.cmig_id == cmig_id)
            )
        ).scalar_one_or_none()
        if not ok:
            raise HTTPException(status_code=400, detail="Pedido não pertence a esta CMIG")
    entry = await customer_credit_service.add_entry(
        db,
        cmig_id=cmig_id,
        person_id=person_id,
        entry_type=entry_type,
        amount=amount,
        order_id=order_id,
        description=(body.get("description") or None),
        created_by=current_user.id,
    )
    balance = await customer_credit_service.get_balance(db, cmig_id, person_id)
    return {"entry": _serialize(entry), "balance": float(balance)}

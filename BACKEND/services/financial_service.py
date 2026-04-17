from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from models.user import DropshipperProfile
from models.financial import FinancialTransaction
from socket_manager import emit_to_user


class InsufficientBalanceError(Exception):
    pass


async def get_balance(db: AsyncSession, dropshipper_id: int) -> tuple[Decimal, Decimal]:
    """Returns (balance, balance_reserved) for a dropshipper."""
    result = await db.execute(
        select(DropshipperProfile).where(DropshipperProfile.user_id == dropshipper_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return Decimal("0"), Decimal("0")
    return profile.balance, profile.balance_reserved


async def credit_balance(
    db: AsyncSession,
    dropshipper_id: int,
    amount: Decimal,
    description: str,
    reference_type: str = None,
    reference_id: int = None,
    pix_txid: str = None,
    pix_key: str = None,
) -> FinancialTransaction:
    """Credit an amount to a dropshipper's balance. Thread-safe via FOR UPDATE."""
    # Lock the row to prevent race conditions
    result = await db.execute(
        select(DropshipperProfile)
        .where(DropshipperProfile.user_id == dropshipper_id)
        .with_for_update()
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de dropshipper não encontrado")

    balance_before = profile.balance
    profile.balance += amount
    balance_after = profile.balance

    tx = FinancialTransaction(
        dropshipper_id=dropshipper_id,
        type="credit",
        amount=amount,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
        balance_before=balance_before,
        balance_after=balance_after,
        pix_key=pix_key,
        pix_txid=pix_txid,
        status="completed",
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)

    # Emit real-time balance update
    await emit_to_user(dropshipper_id, "balance_update", {
        "balance": float(balance_after),
        "balance_reserved": float(profile.balance_reserved),
    })
    return tx


async def debit_balance(
    db: AsyncSession,
    dropshipper_id: int,
    amount: Decimal,
    description: str,
    reference_type: str = None,
    reference_id: int = None,
) -> FinancialTransaction:
    """
    Debit an amount from a dropshipper's balance.
    Uses SELECT FOR UPDATE NOWAIT to prevent race conditions.
    Raises InsufficientBalanceError if balance < amount.
    """
    # NOWAIT: immediately fail if another transaction holds the lock
    result = await db.execute(
        select(DropshipperProfile)
        .where(DropshipperProfile.user_id == dropshipper_id)
        .with_for_update(nowait=True)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de dropshipper não encontrado")

    available = profile.balance - profile.balance_reserved
    if available < amount:
        raise HTTPException(
            status_code=422,
            detail=f"Saldo insuficiente. Disponível: R$ {float(available):.2f}, necessário: R$ {float(amount):.2f}",
        )

    balance_before = profile.balance
    profile.balance -= amount
    balance_after = profile.balance

    tx = FinancialTransaction(
        dropshipper_id=dropshipper_id,
        type="debit",
        amount=amount,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
        balance_before=balance_before,
        balance_after=balance_after,
        status="completed",
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)

    await emit_to_user(dropshipper_id, "balance_update", {
        "balance": float(balance_after),
        "balance_reserved": float(profile.balance_reserved),
    })
    return tx


async def get_transactions(
    db: AsyncSession,
    dropshipper_id: int,
    page: int = 1,
    page_size: int = 20,
    type_filter: str = None,
    date_from=None,
    date_to=None,
) -> dict:
    query = select(FinancialTransaction).where(
        FinancialTransaction.dropshipper_id == dropshipper_id
    )
    if type_filter:
        query = query.where(FinancialTransaction.type == type_filter)
    if date_from:
        query = query.where(FinancialTransaction.created_at >= date_from)
    if date_to:
        query = query.where(FinancialTransaction.created_at <= date_to)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(FinancialTransaction.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": t.id,
                "type": t.type,
                "amount": float(t.amount),
                "description": t.description,
                "status": t.status,
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "pix_txid": t.pix_txid,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

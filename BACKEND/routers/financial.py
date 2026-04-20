from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from decimal import Decimal
from database import get_db
from dependencies import get_active_ac
from models.user import User
from schemas.financial import PIXDepositRequest, BalanceOut
from services.financial_service import get_balance, credit_balance, get_transactions

router = APIRouter()


@router.get("/balance", response_model=BalanceOut)
async def get_my_balance(
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    balance, reserved = await get_balance(db, current_user.id)
    return BalanceOut(
        balance=balance,
        balance_reserved=reserved,
        available=balance - reserved,
    )


@router.get("/transactions")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    return await get_transactions(
        db,
        dropshipper_id=current_user.id,
        page=page,
        page_size=page_size,
        type_filter=type,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/pix-deposit", status_code=201)
async def register_pix_deposit(
    body: PIXDepositRequest,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a PIX deposit.
    In production this would be confirmed via bank webhook.
    For now, it credits immediately (manual confirmation flow).
    """
    tx = await credit_balance(
        db,
        dropshipper_id=current_user.id,
        amount=body.amount,
        description=f"Depósito PIX – TXID: {body.pix_txid}",
        reference_type="pix_deposit",
        pix_txid=body.pix_txid,
        pix_key=body.pix_key,
    )
    return {
        "message": "Depósito registrado com sucesso",
        "transaction_id": tx.id,
        "new_balance": float(tx.balance_after),
    }

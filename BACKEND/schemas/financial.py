from pydantic import BaseModel, field_validator
from decimal import Decimal
from typing import Optional
from datetime import datetime


class PIXDepositRequest(BaseModel):
    amount: Decimal
    pix_txid: str
    pix_key: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("O valor deve ser positivo")
        return v


class TransactionOut(BaseModel):
    id: int
    type: str
    amount: Decimal
    description: Optional[str]
    status: str
    balance_before: Decimal
    balance_after: Decimal
    pix_txid: Optional[str]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    balance: Decimal
    balance_reserved: Decimal
    available: Decimal

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


class PIXDepositRequest(BaseModel):
    amount: Decimal
    pix_txid: str
    pix_key: str | None = None

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
    description: str | None
    status: str
    balance_before: Decimal
    balance_after: Decimal
    pix_txid: str | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    balance: Decimal
    balance_reserved: Decimal
    available: Decimal

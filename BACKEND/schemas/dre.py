from decimal import Decimal

from pydantic import BaseModel, field_validator


class DRESyncRequest(BaseModel):
    cmig_id: int
    year: int
    month: int

    @field_validator("month")
    @classmethod
    def month_range(cls, v):
        if not 1 <= v <= 12:
            raise ValueError("month deve estar entre 1 e 12")
        return v


class DREEntryIn(BaseModel):
    cmig_id: int
    category_kind: str  # entrada | custo_operacional | custo_fixo
    description: str | None = None
    category: str | None = None
    amount: Decimal
    ref_year: int
    ref_month: int
    installments: int = 1  # >1 gera parcelas recorrentes mensais

    @field_validator("category_kind")
    @classmethod
    def valid_kind(cls, v):
        if v not in ("entrada", "custo_operacional", "custo_fixo"):
            raise ValueError("category_kind inválido")
        return v

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v):
        if v <= 0:
            raise ValueError("O valor deve ser positivo")
        return v

    @field_validator("ref_month")
    @classmethod
    def month_range(cls, v):
        if not 1 <= v <= 12:
            raise ValueError("ref_month deve estar entre 1 e 12")
        return v


class DREEntryUpdate(BaseModel):
    category_kind: str | None = None
    description: str | None = None
    category: str | None = None
    amount: Decimal | None = None

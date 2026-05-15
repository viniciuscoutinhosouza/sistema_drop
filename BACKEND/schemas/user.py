from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class AddressSchema(BaseModel):
    zip_code: str
    street: str
    number: str
    complement: str = ""
    neighborhood: str
    city: str
    state: str


class ProfileOut(BaseModel):
    id: int
    email: str
    full_name: str
    whatsapp: str | None
    cpf_cnpj: str | None
    role: str  # ugo | ac | admin | go
    dark_mode: bool
    warehouse_id: int | None = None
    go_id: int | None = None
    created_at: datetime
    address: AddressSchema | None = None
    subscription_status: str | None = None
    subscription_due_date: date | None = None
    balance: Decimal | None = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    whatsapp: str | None = None


class PreferencesUpdate(BaseModel):
    dark_mode: bool


class ViaCEPResponse(BaseModel):
    cep: str
    logradouro: str
    complemento: str
    bairro: str
    localidade: str
    uf: str
    erro: bool | None = None

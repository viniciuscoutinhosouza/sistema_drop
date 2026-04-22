from pydantic import BaseModel, EmailStr
from datetime import date, datetime
from typing import Optional
from decimal import Decimal


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
    whatsapp: Optional[str]
    cpf_cnpj: Optional[str]
    role: str  # ugo | ac | admin | go
    dark_mode: bool
    warehouse_id: Optional[int] = None
    go_id: Optional[int] = None
    created_at: datetime
    address: Optional[AddressSchema] = None
    subscription_status: Optional[str] = None
    subscription_due_date: Optional[date] = None
    balance: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    whatsapp: Optional[str] = None


class PreferencesUpdate(BaseModel):
    dark_mode: bool


class ViaCEPResponse(BaseModel):
    cep: str
    logradouro: str
    complemento: str
    bairro: str
    localidade: str
    uf: str
    erro: Optional[bool] = None

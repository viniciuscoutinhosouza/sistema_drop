from datetime import datetime

from pydantic import BaseModel


class GOCreate(BaseModel):
    # Empresa / Galpão (→ warehouses)
    company_name: str
    trade_name: str | None = None
    cnpj: str
    phone: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    zip_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    pix_key_type: str | None = None
    pix_key: str | None = None
    notes: str | None = None
    # Responsável / Pessoa Física (→ users)
    full_name: str
    user_email: str
    user_whatsapp: str | None = None
    password: str


class GOUpdate(BaseModel):
    # Campos do Warehouse
    company_name: str | None = None
    trade_name: str | None = None
    phone: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    zip_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    pix_key_type: str | None = None
    pix_key: str | None = None
    notes: str | None = None
    # Status do GO
    is_active: bool | None = None


class GOOut(BaseModel):
    id: int
    user_id: int
    warehouse_id: int | None = None
    is_active: bool
    created_at: datetime
    # Do User (responsável)
    full_name: str | None = None
    # Do Warehouse (empresa / galpão)
    company_name: str | None = None
    trade_name: str | None = None
    cnpj: str | None = None
    phone: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    zip_code: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    pix_key_type: str | None = None
    pix_key: str | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}

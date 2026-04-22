from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class GOCreate(BaseModel):
    # Empresa / Galpão (→ warehouses)
    company_name: str
    trade_name: Optional[str] = None
    cnpj: str
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    zip_code: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pix_key_type: Optional[str] = None
    pix_key: Optional[str] = None
    notes: Optional[str] = None
    # Responsável / Pessoa Física (→ users)
    full_name: str
    user_email: str
    user_whatsapp: Optional[str] = None
    password: str


class GOUpdate(BaseModel):
    # Campos do Warehouse
    company_name: Optional[str] = None
    trade_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    zip_code: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pix_key_type: Optional[str] = None
    pix_key: Optional[str] = None
    notes: Optional[str] = None
    # Status do GO
    is_active: Optional[bool] = None


class GOOut(BaseModel):
    id: int
    user_id: int
    warehouse_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    # Do User (responsável)
    full_name: Optional[str] = None
    # Do Warehouse (empresa / galpão)
    company_name: Optional[str] = None
    trade_name: Optional[str] = None
    cnpj: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    zip_code: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pix_key_type: Optional[str] = None
    pix_key: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}

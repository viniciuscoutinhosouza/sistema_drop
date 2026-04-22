from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# ── CMIG ──────────────────────────────────────────────────────────────────────

class CMIGCreate(BaseModel):
    warehouse_id: int
    cnpj: str
    company_name: str
    trade_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    zip_code: Optional[str] = None
    street: Optional[str] = None
    address_number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class CMIGUpdate(BaseModel):
    company_name: Optional[str] = None
    trade_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    zip_code: Optional[str] = None
    street: Optional[str] = None
    address_number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: Optional[bool] = None


class CMIGOut(BaseModel):
    id: int
    owner_ac_id: int
    warehouse_id: int
    cnpj: str
    company_name: str
    trade_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    zip_code: Optional[str]
    street: Optional[str]
    address_number: Optional[str]
    complement: Optional[str]
    neighborhood: Optional[str]
    city: Optional[str]
    state: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CMIGAdminAdd(BaseModel):
    user_id: int


# ── Produto CMIG ───────────────────────────────────────────────────────────────

class CMIGProductImageOut(BaseModel):
    id: int
    url: str
    sort_order: int
    is_primary: bool

    model_config = {"from_attributes": True}


class CMIGProductCreate(BaseModel):
    sku_cmig: str
    title: str
    description: Optional[str] = None
    brand: Optional[str] = None
    cost_price: Optional[float] = None
    stock_quantity: int = 0
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    width_cm: Optional[float] = None
    length_cm: Optional[float] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    origin: Optional[int] = 0


class CMIGProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    cost_price: Optional[float] = None
    stock_quantity: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    width_cm: Optional[float] = None
    length_cm: Optional[float] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    origin: Optional[int] = None
    is_active: Optional[bool] = None


class CMIGProductLinkPG(BaseModel):
    pg_product_id: int


class CMIGProductOut(BaseModel):
    id: int
    cmig_id: int
    sku_cmig: str
    title: str
    description: Optional[str]
    brand: Optional[str]
    cost_price: Optional[float]
    stock_quantity: int
    weight_kg: Optional[float]
    height_cm: Optional[float]
    width_cm: Optional[float]
    length_cm: Optional[float]
    ncm: Optional[str]
    cest: Optional[str]
    origin: Optional[int]
    pg_product_id: Optional[int]
    is_active: bool
    created_at: datetime
    images: List[CMIGProductImageOut] = []

    model_config = {"from_attributes": True}


# ── NF-e Config ───────────────────────────────────────────────────────────────

class NFeConfigCreate(BaseModel):
    shipping_method: str
    issuer: str  # marketplace | system
    notes: Optional[str] = None


class NFeConfigUpdate(BaseModel):
    issuer: Optional[str] = None
    notes: Optional[str] = None


class NFeConfigOut(BaseModel):
    id: int
    cm_id: int
    shipping_method: str
    issuer: str
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

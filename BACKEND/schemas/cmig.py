from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator


def _norm_ncm(v: str | None) -> str | None:
    if not v:
        return v
    return v.replace(".", "").replace("-", "")[:8] or None


def _norm_cest(v: str | None) -> str | None:
    if not v:
        return v
    return v.replace(".", "").replace("-", "")[:7] or None

# ── CMIG ──────────────────────────────────────────────────────────────────────


class CMIGCreate(BaseModel):
    warehouse_id: int
    cnpj: str | None = None
    cpf: str | None = None
    company_name: str  # Razão Social (PJ) ou Nome completo (PF)
    trade_name: str | None = None
    email: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    street: str | None = None
    address_number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None

    @model_validator(mode="after")
    def check_document(self):
        if not self.cnpj and not self.cpf:
            raise ValueError("Informe o CNPJ (Pessoa Jurídica) ou CPF (Pessoa Física)")
        if self.cnpj and self.cpf:
            raise ValueError("Informe apenas CNPJ ou CPF, não ambos")
        return self


class CMIGUpdate(BaseModel):
    cnpj: str | None = None
    cpf: str | None = None
    company_name: str | None = None
    trade_name: str | None = None
    email: str | None = None
    phone: str | None = None
    zip_code: str | None = None
    street: str | None = None
    address_number: str | None = None
    complement: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    ibge_code: str | None = None
    # Conveniência p/ a conversão CPF→CNPJ: IE mora em CMIGFiscalConfig, mas pode ser
    # informada aqui para o backend fazer o upsert na hora de virar PJ (exige IE + IBGE).
    ie: str | None = None
    is_active: bool | None = None

    @field_validator("cnpj", "cpf", "ibge_code", "ie", "company_name", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        # '' / espaços → None, para permitir LIMPAR o documento antigo na conversão de tipo.
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class CMIGOut(BaseModel):
    id: int
    owner_ac_id: int
    warehouse_id: int
    cnpj: str | None
    cpf: str | None
    company_name: str | None
    trade_name: str | None
    email: str | None
    phone: str | None
    zip_code: str | None
    street: str | None
    address_number: str | None
    complement: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    ibge_code: str | None = None
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


class CMIGProductComponentIn(BaseModel):
    cmig_product_id: int | None = None
    catalog_product_id: int | None = None
    quantity: int = 1


class CMIGProductCreate(BaseModel):
    # stock_quantity intencionalmente fora — gerenciado por eventos de NF-e/pedido
    sku_cmig: str
    title: str
    description: str | None = None
    brand: str | None = None
    model: str | None = None
    ean: str | None = None
    cost_price: float | None = None
    suggested_price: float | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    width_cm: float | None = None
    length_cm: float | None = None
    ncm: str | None = None
    cest: str | None = None
    origin: int | None = 0
    csosn: str | None = None
    category_id: int | None = None
    video_id: str | None = None
    attributes_json: str | None = None
    is_composite: bool | None = False
    components: list[CMIGProductComponentIn] | None = None

    @field_validator("ncm", mode="before")
    @classmethod
    def normalize_ncm(cls, v):
        return _norm_ncm(v)

    @field_validator("cest", mode="before")
    @classmethod
    def normalize_cest(cls, v):
        return _norm_cest(v)


class CMIGProductUpdate(BaseModel):
    # stock_quantity intencionalmente fora — gerenciado por eventos de NF-e/pedido
    sku_cmig: str | None = None
    cascade_sku_to_linked: bool | None = False  # se True, propaga SKU pro PG e anúncios vinculados
    title: str | None = None
    description: str | None = None
    brand: str | None = None
    model: str | None = None
    ean: str | None = None
    cost_price: float | None = None
    suggested_price: float | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    width_cm: float | None = None
    length_cm: float | None = None
    ncm: str | None = None
    cest: str | None = None

    @field_validator("ncm", mode="before")
    @classmethod
    def normalize_ncm(cls, v):
        return _norm_ncm(v)

    @field_validator("cest", mode="before")
    @classmethod
    def normalize_cest(cls, v):
        return _norm_cest(v)
    origin: int | None = None
    csosn: str | None = None
    is_active: bool | None = None
    category_id: int | None = None
    video_id: str | None = None
    attributes_json: str | None = None
    images: list | None = None  # [{url: "..."}]; quando presente, sincroniza cmig_product_images
    components: list[CMIGProductComponentIn] | None = (
        None  # quando presente, substitui todos os componentes
    )


class CMIGProductLinkPG(BaseModel):
    pg_product_id: int


class CMIGProductComponentOut(BaseModel):
    id: int
    type: str  # 'cmig' | 'pg'
    product_id: int
    title: str
    sku: str
    stock_quantity: int
    quantity: int
    contribution: int  # floor(stock_quantity / quantity)

    model_config = {"from_attributes": True}


class CMIGProductOut(BaseModel):
    id: int
    cmig_id: int
    sku_cmig: str
    title: str
    description: str | None
    brand: str | None
    model: str | None
    ean: str | None
    cost_price: float | None
    suggested_price: float | None
    stock_quantity: int
    weight_kg: float | None
    height_cm: float | None
    width_cm: float | None
    length_cm: float | None
    ncm: str | None
    cest: str | None
    origin: int | None
    csosn: str | None = None
    category_id: int | None = None
    category_name: str | None = None  # derivado do join (read-only)
    video_id: str | None
    attributes_json: str | None = None
    pictures_json: str | None = None  # legado — fallback de leitura
    pg_product_id: int | None
    is_composite: bool = False
    is_active: bool
    created_at: datetime
    images: list[CMIGProductImageOut] = []
    components: list[CMIGProductComponentOut] = []

    model_config = {"from_attributes": True}


# ── NF-e Config ───────────────────────────────────────────────────────────────


class NFeConfigCreate(BaseModel):
    shipping_method: str
    issuer: str  # marketplace | system
    notes: str | None = None


class NFeConfigUpdate(BaseModel):
    issuer: str | None = None
    notes: str | None = None


class NFeConfigOut(BaseModel):
    id: int
    cm_id: int
    shipping_method: str
    issuer: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

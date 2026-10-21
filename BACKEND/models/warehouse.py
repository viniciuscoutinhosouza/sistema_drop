from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class Warehouse(Base):
    """Galpão pertencente a um GO. Um GO pode ter múltiplos galpões."""

    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True)
    go_id = Column(Integer, ForeignKey("goes.id"), nullable=True)
    name = Column(String(200), nullable=False)
    # 'dropship' (contas vendem PG + própria CMIG) | 'multilojas' (só a própria CMIG). Migration 137.
    work_type = Column(String(20), nullable=False, server_default=text("'dropship'"))
    cnpj = Column(String(18))
    company_name = Column(String(255))
    trade_name = Column(String(255))
    phone = Column(String(20))
    whatsapp = Column(String(20))
    email = Column(String(255))
    zip_code = Column(String(9))
    street = Column(String(255))
    number = Column("address_number", String(20))
    complement = Column(String(100))
    neighborhood = Column(String(100))
    city = Column(String(100))
    state = Column(String(2))
    pix_key_type = Column(String(20))  # cpf | cnpj | email | phone | random
    pix_key = Column(String(255))
    # Flags de recebimento/checkout (migration 152, ADR-0031) — INERTES na Fase 1 (só config):
    #   pg_requires_prepaid          = venda de PG exige crédito/pagamento da CMIG antes da entrega
    #   manual_sale_requires_payment = venda manual exige pagamento do cliente p/ dar continuidade
    pg_requires_prepaid = Column(Boolean, nullable=False, server_default=text("0"))
    manual_sale_requires_payment = Column(Boolean, nullable=False, server_default=text("0"))
    notes = Column(String(2000))
    # Branding por Galpão (migration 141): logo + até 5 cores de tema (hex #RRGGBB). NULL = padrão MIG.
    logo_url = Column(String(500))
    theme_sidebar = Column(String(7))       # fundo da barra lateral
    theme_accent = Column(String(7))        # item ativo / destaque
    theme_topbar = Column(String(7))        # barra superior (navbar)
    theme_sidebar_text = Column(String(7))  # texto/ícones da barra lateral
    theme_link = Column(String(7))          # links e realces
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    go = relationship("GO", back_populates="warehouses", foreign_keys=[go_id])
    cmigs = relationship("CMIG", back_populates="warehouse")
    bank_accounts = relationship(
        "WarehouseBankAccount", back_populates="warehouse", cascade="all, delete-orphan"
    )


class WarehouseBankAccount(Base):
    """Conta de recebimento de um Galpão (ex.: ASAAS). Migration 152 (ADR-0031).

    A API Key do gateway é guardada CIFRADA (`api_key_encrypted`, Fernet via services/crypto) —
    nunca em claro e nunca devolvida ao front (só o flag `api_key_set`). Vários bancos por galpão
    (cada conta tem a sua); `is_primary` prepara a Fase 2 (qual conta usar p/ cobrar).
    """

    __tablename__ = "warehouse_bank_accounts"

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    provider = Column(String(20), nullable=False, server_default=text("'asaas'"))
    bank_code = Column(String(10))
    name = Column(String(200), nullable=False)
    api_key_encrypted = Column(String(2000))
    wallet_id = Column(String(100))
    chart_account_label = Column(String(255))  # texto livre — não há Plano de Contas ainda
    is_sandbox = Column(Boolean, nullable=False, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    is_primary = Column(Boolean, nullable=False, server_default=text("0"))
    agency = Column(String(20))
    account_number = Column(String(30))
    pix_key_type = Column(String(20))
    pix_key = Column(String(255))
    holder_name = Column(String(255))
    holder_document = Column(String(20))
    opening_balance = Column(Numeric(15, 2), server_default=text("0"))
    opening_balance_date = Column(Date)
    notes = Column(String(2000))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    warehouse = relationship("Warehouse", back_populates="bank_accounts")

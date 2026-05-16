from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class CMIGFiscalConfig(Base):
    """Configuração de emissor NFe por CMIG (Focus NFe + dados fiscais complementares)."""

    __tablename__ = "cmig_fiscal_config"
    __table_args__ = (UniqueConstraint("cmig_id", name="uq_cfc_cmig"),)

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    crt = Column(Integer, nullable=False, default=1)  # 1=Simples 2=SimplesExc 3=Normal 4=MEI
    environment = Column(String(20), nullable=False, default="homolog")

    # Focus NFe
    focus_company_token = Column(String(200))
    focus_company_id = Column(String(100))
    focus_registered_at = Column(TIMESTAMP(timezone=True))

    # Certificado A1 (.pfx) — armazenado no Focus, espelhamos metadados
    certificate_uploaded_at = Column(TIMESTAMP(timezone=True))
    certificate_expires_at = Column(TIMESTAMP(timezone=True))
    certificate_subject = Column(String(500))

    # Dados fiscais complementares
    ie = Column(String(20))
    im = Column(String(20))
    cnae = Column(String(10))
    default_natureza_operacao = Column(String(255), default="Venda de mercadoria")

    # Numeração NFe
    nfe_serie = Column(Integer, default=1)
    nfe_next_number = Column(Integer, default=1)

    # NFC-e (futuro)
    csc_id = Column(String(20))
    csc_token = Column(String(100))

    # Geral
    fiscal_email_copy = Column(String(255))

    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    cmig = relationship("CMIG", back_populates="fiscal_config")


class Invoice(Base):
    """NFe emitida (saída) ou recebida (entrada) por uma CMIG."""

    __tablename__ = "invoices"
    __table_args__ = (
        # uq_inv_serie_number é um índice funcional Oracle (migration 58) — não declarável aqui.
        # Aplica unicidade somente quando serie e nfe_number são não-NULL (rascunhos ficam livres).
        UniqueConstraint("access_key", name="uq_inv_access_key"),
    )

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    direction = Column(String(3), nullable=False)  # 'out' | 'in'
    purpose = Column(String(20), nullable=False, default="venda")
    model = Column(String(2), default="55")
    serie = Column(Integer)
    nfe_number = Column(Integer)
    access_key = Column(String(50))
    person_id = Column(Integer, ForeignKey("people.id"))
    order_id = Column(Integer, ForeignKey("orders.id"))
    inbound_invoice_id = Column(Integer, ForeignKey("invoices.id"))
    natureza_operacao = Column(String(255))
    issue_date = Column(TIMESTAMP(timezone=True))
    exit_date = Column(TIMESTAMP(timezone=True))
    status = Column(String(20), nullable=False, default="draft")

    # Entrada (direction='in')
    inbound_source = Column(String(20))  # xml_upload | manual | dfe_focus
    manifestation = Column(String(20))  # pending | ciencia | ...
    manifestation_at = Column(TIMESTAMP(timezone=True))
    manifestation_protocol = Column(String(50))
    stock_updated = Column(Boolean, nullable=False, default=False)

    # Focus NFe
    focus_ref = Column(String(100))
    focus_status = Column(String(50))
    focus_message = Column(String(2000))

    # Arquivos
    xml_url = Column(String(1000))
    danfe_url = Column(String(1000))
    xml_local_path = Column(String(1000))

    # Totais
    total_products = Column(Numeric(15, 2), default=0)
    total_freight = Column(Numeric(15, 2), default=0)
    total_insurance = Column(Numeric(15, 2), default=0)
    total_discount = Column(Numeric(15, 2), default=0)
    total_other = Column(Numeric(15, 2), default=0)
    total_icms = Column(Numeric(15, 2), default=0)
    total_icms_st = Column(Numeric(15, 2), default=0)
    total_pis = Column(Numeric(15, 2), default=0)
    total_cofins = Column(Numeric(15, 2), default=0)
    total_ipi = Column(Numeric(15, 2), default=0)
    total_invoice = Column(Numeric(15, 2), default=0)

    # Transporte
    freight_modality = Column(Integer)
    carrier_person_id = Column(Integer, ForeignKey("people.id"))

    # Pagamento
    payment_method = Column(String(2))
    payment_terms_json = Column(Text)

    # Adicionais
    additional_info = Column(String(2000))
    fiscal_info = Column(String(2000))

    # Cancelamento
    cancelled_at = Column(TIMESTAMP(timezone=True))
    cancel_reason = Column(String(500))
    cancel_protocol = Column(String(50))

    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id"))

    cmig = relationship("CMIG")
    person = relationship("Person", foreign_keys=[person_id])
    carrier = relationship("Person", foreign_keys=[carrier_person_id])
    order = relationship("Order", foreign_keys=[order_id])
    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        foreign_keys="[InvoiceItem.invoice_id]",
    )
    events = relationship("InvoiceEvent", back_populates="invoice", cascade="all, delete-orphan")
    inbound_invoice = relationship("Invoice", remote_side=[id], foreign_keys=[inbound_invoice_id])


class InvoiceItem(Base):
    """Item de uma NFe."""

    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    item_number = Column(Integer, nullable=False)
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"))
    sku = Column(String(50))
    source_type = Column(String(10))  # 'cmig' | 'pg' | 'manual'
    cfop = Column(String(4))
    ncm = Column(String(8))
    cest = Column(String(7))
    description = Column(String(500), nullable=False)
    ean = Column(String(14))
    unit = Column(String(6), default="UN")
    quantity = Column(Numeric(15, 4), default=1)
    unit_value = Column(Numeric(15, 4), default=0)
    total_value = Column(Numeric(15, 2), default=0)
    discount = Column(Numeric(15, 2), default=0)
    freight_value = Column(Numeric(15, 2), default=0)
    insurance_value = Column(Numeric(15, 2), default=0)
    other_value = Column(Numeric(15, 2), default=0)
    origin = Column(Integer, default=0)
    icms_cst = Column(String(3))
    icms_csosn = Column(String(3))
    icms_base = Column(Numeric(15, 2), default=0)
    icms_aliquota = Column(Numeric(8, 4), default=0)
    icms_value = Column(Numeric(15, 2), default=0)
    icms_st_base = Column(Numeric(15, 2), default=0)
    icms_st_aliquota = Column(Numeric(8, 4), default=0)
    icms_st_value = Column(Numeric(15, 2), default=0)
    ipi_cst = Column(String(2))
    ipi_aliquota = Column(Numeric(8, 4), default=0)
    ipi_value = Column(Numeric(15, 2), default=0)
    pis_cst = Column(String(2))
    pis_aliquota = Column(Numeric(8, 4), default=0)
    pis_value = Column(Numeric(15, 2), default=0)
    cofins_cst = Column(String(2))
    cofins_aliquota = Column(Numeric(8, 4), default=0)
    cofins_value = Column(Numeric(15, 2), default=0)
    inbound_item_id = Column(Integer, ForeignKey("invoice_items.id"))
    additional_info = Column(String(2000))

    invoice = relationship("Invoice", back_populates="items", foreign_keys=[invoice_id])
    cmig_product = relationship("CMIGProduct")


class InvoiceEvent(Base):
    """Auditoria de eventos NFe (cancelamento, CCe, manifestação, inutilização)."""

    __tablename__ = "invoice_events"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    event_type = Column(String(30), nullable=False)
    sequence_number = Column(Integer)
    reason = Column(String(2000))
    focus_ref = Column(String(100))
    sefaz_protocol = Column(String(50))
    sefaz_status_code = Column(String(10))
    sefaz_message = Column(String(2000))
    xml_url = Column(String(1000))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    created_by_user_id = Column(Integer, ForeignKey("users.id"))

    invoice = relationship("Invoice", back_populates="events")

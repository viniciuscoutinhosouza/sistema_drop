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

    # Focus NFe (LEGACY — emissão própria SEFAZ abaixo substitui; mantido p/ compat)
    focus_company_token = Column(String(200))
    focus_company_id = Column(String(100))
    focus_registered_at = Column(TIMESTAMP(timezone=True))

    # Certificado A1 (.pfx) — agora armazenado LOCAL no servidor; senha CIFRADA no banco
    certificate_uploaded_at = Column(TIMESTAMP(timezone=True))
    certificate_expires_at = Column(TIMESTAMP(timezone=True))
    certificate_subject = Column(String(500))
    cert_path = Column(String(255))             # caminho do .pfx no servidor (fora de static/)
    cert_pass_encrypted = Column(String(512))   # senha do .pfx cifrada (Fernet) — nunca em claro

    # Emissão própria SEFAZ
    production_released = Column(Integer, default=0, nullable=False)  # go-live faseado por empresa
    aliquota_fecp = Column(Numeric(5, 2), default=0)                 # FECP (ex.: RJ 2%) por produto
    ultimo_nsu = Column(String(20), default="0")                     # Distribuição DFe (NSU por CNPJ)

    # Série específica configurável p/ emissão MANUAL via SEFAZ (separada do marketplace),
    # numeração desdobrada por ambiente.
    manual_nfe_serie = Column(Integer)
    manual_nfe_next_number = Column(Integer, default=1)
    manual_nfe_next_number_homolog = Column(Integer, default=1)

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

    # DRE — % de imposto estimado sobre o faturamento (linha "Imposto ML")
    tax_estimate_pct = Column(Numeric(8, 4), default=0)

    # Fase 2 — modo de regime tributário (Reforma Tributária EC 132/2023)
    # legacy = regime atual (ICMS/PIS/COFINS)
    # transition = coexistência 2026-2032 (ambos os regimes)
    # reform = regime pleno IBS/CBS (2033+)
    tax_regime_mode = Column(String(12), default="legacy", nullable=False)

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

    # Focus NFe (LEGACY) + emissão própria SEFAZ
    focus_ref = Column(String(100))
    focus_status = Column(String(50))
    focus_message = Column(String(2000))
    auth_protocol = Column(String(20))      # nProt da autorização SEFAZ (cStat=100)
    sefaz_cstat = Column(String(4))         # último cStat da nota
    sefaz_xmotivo = Column(String(255))     # último xMotivo
    environment = Column(String(12))        # ambiente fixado na emissão: homolog | production
    emission_provider = Column(String(10), default="focus")  # focus | sefaz

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
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"))
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

    # Fase 1 — DIFAL (EC 87/2015): venda interestadual a consumidor final não-contribuinte
    difal_base = Column(Numeric(15, 2))
    difal_aliquota_orig = Column(Numeric(5, 2))  # alíquota ICMS na UF de origem
    difal_aliquota_dest = Column(Numeric(5, 2))  # alíquota ICMS na UF de destino
    difal_value = Column(Numeric(15, 2))         # base × (dest - orig)
    difal_fcp_aliquota = Column(Numeric(5, 2))   # FCP % destino
    difal_fcp_value = Column(Numeric(15, 2))     # base × fcp_aliquota

    # Fase 2 — Reforma Tributária (EC 132/2023)
    cbs_cst = Column(String(2))
    cbs_aliquota = Column(Numeric(6, 4))
    cbs_base = Column(Numeric(15, 2))
    cbs_value = Column(Numeric(15, 2))
    ibs_cst = Column(String(2))
    ibs_aliquota_uf = Column(Numeric(6, 4))
    ibs_aliquota_mun = Column(Numeric(6, 4))
    ibs_base = Column(Numeric(15, 2))
    ibs_value = Column(Numeric(15, 2))
    is_value = Column(Numeric(15, 2))

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


class InvoiceSefazLog(Base):
    """Log bruto request/response SOAP da SEFAZ (append-only, migration 116)."""

    __tablename__ = "invoice_sefaz_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    cmig_id = Column(Integer, nullable=False)
    operation = Column(String(40), nullable=False)  # autorizacao|consulta|cancelamento|cce|distribuicao
    cstat = Column(String(4))
    xmotivo = Column(String(255))
    payload_request = Column(Text)
    payload_response = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))


class DFeRecebido(Base):
    """Documento da Distribuição de DFe (entrada própria, migration 116)."""

    __tablename__ = "dfe_recebidos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cmig_id = Column(Integer, nullable=False)
    nsu = Column(String(20), nullable=False)
    chave = Column(String(44))
    schema_dfe = Column(String(60))
    resumo_json = Column(Text)
    xml = Column(Text)
    manifestacao = Column(String(20), default="pending")
    manifestacao_at = Column(TIMESTAMP(timezone=True))
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    criado_em = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))


class CFOPCode(Base):
    """Tabela de CFOPs configuráveis — seed via migration 93."""

    __tablename__ = "cfop_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(4), nullable=False, unique=True)
    description = Column(String(255), nullable=False)
    direction = Column(String(3), nullable=False)
    notes = Column(String(500))
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))


class ICMSRate(Base):
    """Alíquotas ICMS por par UF origem/destino — seed via migration 94."""

    __tablename__ = "icms_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uf_origin = Column(String(2), nullable=False)
    uf_dest = Column(String(2), nullable=False)
    aliquota = Column(Numeric(5, 2), nullable=False)
    valid_from = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    valid_to = Column(TIMESTAMP(timezone=True))
    is_active = Column(Integer, default=1, nullable=False)
    notes = Column(String(255))


class NCMCode(Base):
    """Tabela de códigos NCM para validação — seed via migration 95."""

    __tablename__ = "ncm_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(8), nullable=False, unique=True)
    description = Column(String(500), nullable=False)
    section = Column(String(5))
    chapter = Column(String(2))
    ipi_rate = Column(Numeric(5, 2))
    is_active = Column(Integer, default=1, nullable=False)


class DFeSyncLog(Base):
    """Log de sincronização DFe por CMIG — criado via migration 96."""

    __tablename__ = "dfe_sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cmig_id = Column(Integer, nullable=False)
    started_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    finished_at = Column(TIMESTAMP(timezone=True))
    status = Column(String(10), default="running", nullable=False)
    invoices_created = Column(Integer, default=0)
    invoices_skipped = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    error_detail = Column(String(4000))
    consecutive_errors = Column(Integer, default=0)

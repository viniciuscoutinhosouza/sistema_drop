from sqlalchemy import (
    TIMESTAMP,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)

from database import Base


class DRESnapshot(Base):
    """Cache mensal sincronizado da DRE por CMIG.

    Guarda os valores do Mercado Livre (operacional + billing + ADS) de um
    (cmig_id, ref_year, ref_month). Recalculado sob demanda pelo botão de
    sincronização do mês na tela Gestão Financeira.

    `imposto` NÃO é coluna — é derivado na leitura a partir de
    CMIGFiscalConfig.tax_estimate_pct, para refletir mudança de alíquota
    sem precisar re-sincronizar.
    """

    __tablename__ = "dre_snapshots"
    __table_args__ = (
        UniqueConstraint("cmig_id", "ref_year", "ref_month", name="uq_dres_cmig_period"),
    )

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    ref_year = Column(Integer, nullable=False)
    ref_month = Column(Integer, nullable=False)  # 1..12
    faturamento = Column(Numeric(15, 2), default=0)
    vendas_canceladas = Column(Numeric(15, 2), default=0)
    tarifa_venda = Column(Numeric(15, 2), default=0)
    devolucao_parcial = Column(Numeric(15, 2), default=0)
    custo_produtos = Column(Numeric(15, 2), default=0)  # CMV
    frete_vendedor = Column(Numeric(15, 2), default=0)
    gasto_ads = Column(Numeric(15, 2), default=0)
    source = Column(String(20), default="operational")  # operational | billing | reconciled
    billing_json = Column(Text)  # CLOB — detalhe bruto do billing para auditoria
    last_synced_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )


class DREEntry(Base):
    """Lançamento manual da DRE por CMIG (entrada / custo operacional / custo fixo).

    Recorrência: ao cadastrar N parcelas a partir de (ref_year, ref_month),
    o backend gera N linhas (uma por mês) compartilhando o mesmo
    recurrence_group_id.
    """

    __tablename__ = "dre_entries"

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    category_kind = Column(String(20), nullable=False)  # entrada|custo_operacional|custo_fixo
    description = Column(String(500))
    category = Column(String(100))
    amount = Column(Numeric(15, 2), nullable=False)
    ref_year = Column(Integer, nullable=False)
    ref_month = Column(Integer, nullable=False)  # 1..12
    recurrence_group_id = Column(String(40))
    installment_no = Column(Integer)
    total_installments = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

"""Rastreabilidade de produtos — lote / validade / número serial (ADR-0027).

Sub-ledger PARALELO e ADITIVO ao estoque escalar event-sourced (ADR-0004):
- `product_lots`  = saldo por lote (CACHE derivado por replay; 5 baldes espelham o escalar).
- `product_serials` = 1 linha por unidade serial (status DERIVADO do replay das alocações).
- `invoice_item_lots` / `invoice_item_serials` = rastro capturado na nota de ENTRADA (<rastro>).
- `stock_lot_allocations` = alocação de SAÍDA por item de pedido (a baixa é ORDER-DRIVEN; a
  emissão fiscal lê esta alocação imutável, nunca o cache).
- `nfe_ncm_rastreavel` = parâmetro fiscal (NCM x UF x vigência exige rastro/med — carregado da NT).

`product_type` segue o enum de `stock_movements`: 'pg' | 'cmig' | 'variant_pg' | 'variant_cmig'.
"""
from sqlalchemy import (
    TIMESTAMP,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)

from database import Base


class ProductLot(Base):
    """Saldo por lote (LOCAL). Cache derivado por replay — nada grava fora do recompute (ADR-0027)."""

    __tablename__ = "product_lots"

    id = Column(Integer, primary_key=True)
    product_type = Column(String(20), nullable=False)  # pg|cmig|variant_pg|variant_cmig
    product_id = Column(Integer, nullable=False)
    lot_code = Column(String(20), nullable=False)
    mfg_date = Column(Date)
    expiry_date = Column(Date)
    # 5 baldes espelham o escalar (product.py:44-48). balance sobe só no APTO (ADR-0009).
    balance = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    awaiting_return = Column(Integer, nullable=False, default=0)
    pending_validation = Column(Integer, nullable=False, default=0)
    unfit = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    @property
    def available(self) -> int:
        return max(0, (self.balance or 0) - (self.reserved or 0))


class ProductSerial(Base):
    """Uma unidade serial. status: in_stock|allocated|shipped|returned|unfit (derivado do replay)."""

    __tablename__ = "product_serials"

    id = Column(Integer, primary_key=True)
    product_type = Column(String(20), nullable=False)
    product_id = Column(Integer, nullable=False)
    serial = Column(String(80), nullable=False)
    lot_id = Column(Integer, ForeignKey("product_lots.id"), nullable=True)
    # largura 20 alinhada ao vocabulário de baldes de StockLotAllocation.status
    # (in_stock|allocated|shipped|awaiting_return|pending_validation|returned|unfit).
    status = Column(String(20), nullable=False, default="in_stock")
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )


class InvoiceItemLot(Base):
    """Lote capturado no item de uma nota de ENTRADA (grupo <rastro>). N lotes por item."""

    __tablename__ = "invoice_item_lots"

    id = Column(Integer, primary_key=True)
    invoice_item_id = Column(Integer, ForeignKey("invoice_items.id"), nullable=False)
    n_lote = Column(String(20), nullable=False)
    q_lote = Column(Numeric(15, 3), nullable=False)
    d_fab = Column(Date)
    d_val = Column(Date)
    c_agreg = Column(String(20))


class InvoiceItemSerial(Base):
    """Serial capturado no item de uma nota de ENTRADA."""

    __tablename__ = "invoice_item_serials"

    id = Column(Integer, primary_key=True)
    invoice_item_id = Column(Integer, ForeignKey("invoice_items.id"), nullable=False)
    serial = Column(String(80), nullable=False)


class StockLotAllocation(Base):
    """Alocação de SAÍDA por item de pedido (FEFO/serial). A baixa do lote é dirigida pelo pedido.

    status: allocated|shipped|awaiting_return|pending_validation|returned|unfit — permite mover o
    lote entre baldes na devolução/cancelamento (ADR-0027).
    """

    __tablename__ = "stock_lot_allocations"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(Integer, nullable=True)
    product_type = Column(String(20), nullable=False)
    product_id = Column(Integer, nullable=False)
    lot_id = Column(Integer, ForeignKey("product_lots.id"), nullable=True)
    serial_id = Column(Integer, ForeignKey("product_serials.id"), nullable=True)
    qty = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="allocated")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )


class NfeNcmRastreavel(Base):
    """Parâmetro: NCM (x UF x vigência) que exige <rastro>/<med>. Carregado da NT — não hardcode.

    `uf` NULL = regra nacional. Consultar com cuidado à armadilha Oracle NULL/'' (lição L-012).
    """

    __tablename__ = "nfe_ncm_rastreavel"

    id = Column(Integer, primary_key=True)
    ncm = Column(String(8), nullable=False)
    uf = Column(String(2))
    vig_ini = Column(Date)
    vig_fim = Column(Date)
    requires_rastro = Column(Integer, nullable=False, default=1)
    requires_med = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

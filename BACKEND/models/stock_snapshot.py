"""Snapshot diário de estoque por produto (Fase 2 — trilha contábil).

Gerado por job APScheduler diário no fim do dia BRT. Combinação
(snapshot_date, product_type, product_id) é única — re-execução no mesmo dia
faz UPSERT.
"""

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from database import Base


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "product_type", "product_id", name="uq_stock_snap_date_product"
        ),
    )

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False)
    product_type = Column(String(10), nullable=False)  # 'pg' | 'cmig'
    product_id = Column(Integer, nullable=False)
    cmig_id = Column(Integer, nullable=True)
    sku = Column(String(100), nullable=True)

    physical = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    available = Column(Integer, default=0, nullable=False)
    awaiting_return = Column(Integer, default=0, nullable=False)
    pending_validation = Column(Integer, default=0, nullable=False)
    unfit = Column(Integer, default=0, nullable=False)
    full_qty = Column(Integer, default=0, nullable=False)
    full_reserved = Column(Integer, default=0, nullable=False)

    # Drift: cache stock_quantity divergiu do canônico (recompute) durante o snapshot.
    drift_detected = Column(Boolean, default=False, nullable=False)
    drift_details = Column(String(500), nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

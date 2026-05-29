from sqlalchemy import TIMESTAMP, CheckConstraint, Column, ForeignKey, Integer, Numeric, String, text

from database import Base


class StockManualAdjustment(Base):
    """Trilha de auditoria de alterações no cache stock_quantity (PG ou CMIG).

    Não afeta o cálculo de saldo — apenas registra quem alterou, quando e por que.
    Alimentada por hooks nos endpoints de override/recalculate.
    """

    __tablename__ = "stock_manual_adjustments"

    id = Column(Integer, primary_key=True)
    product_type = Column(String(10), nullable=False)  # 'pg' | 'cmig'
    product_id = Column(Integer, nullable=False)
    old_value = Column(Numeric, nullable=False)
    new_value = Column(Numeric, nullable=False)
    delta = Column(Numeric, nullable=False)
    reason = Column(String(500))
    user_id = Column(Integer, ForeignKey("users.id"))
    adjustment_kind = Column(String(30), nullable=False)  # manual_override | recompute | batch_recompute
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    __table_args__ = (
        CheckConstraint("product_type IN ('pg','cmig')", name="ck_sma_type"),
        CheckConstraint(
            "adjustment_kind IN ('manual_override','recompute','batch_recompute')",
            name="ck_sma_kind",
        ),
    )

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.orm import relationship

from database import Base


class CmigWarehouseCredit(Base):
    """Movimento do razão de crédito CMIG × Galpão (ADR-0034, migration 155).

    Append-only. Saldo de um par = Σ(amount where credit) − Σ(amount where debit).
    'credit' = a CMIG depositou crédito no Galpão; 'debit' = consumo por venda PG.
    """

    __tablename__ = "cmig_warehouse_credits"

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    entry_type = Column(String(10), nullable=False)  # 'credit' | 'debit'
    amount = Column(Numeric(15, 2), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    description = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    order = relationship("Order")

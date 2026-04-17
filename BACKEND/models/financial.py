from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, ForeignKey, text
from database import Base


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(String(500))
    reference_type = Column(String(50))
    reference_id = Column(Integer)
    balance_before = Column(Numeric(15, 2), nullable=False)
    balance_after = Column(Numeric(15, 2), nullable=False)
    pix_key = Column(String(255))
    pix_txid = Column(String(255))
    status = Column(String(20), nullable=False, default="completed")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

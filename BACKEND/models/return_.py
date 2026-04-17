from sqlalchemy import Column, Integer, String, Numeric, Date, TIMESTAMP, ForeignKey, text
from database import Base


class Return(Base):
    __tablename__ = "returns"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"))
    reason = Column(String(50))
    description = Column(String)
    tracking_code = Column(String(100))
    tracking_url = Column(String(500))
    carrier = Column(String(100))
    expected_date = Column(Date)
    security_code = Column(String(100))
    status = Column(String(20), nullable=False, default="analyzing")
    supplier_notes = Column(String)
    credit_amount = Column(Numeric(15, 2))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

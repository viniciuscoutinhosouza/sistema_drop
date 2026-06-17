from sqlalchemy import TIMESTAMP, Column, Date, ForeignKey, Integer, Numeric, String, text

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
    status = Column(String(30), nullable=False, default="analyzing")
    return_type = Column(String(20), default="customer")
    # Devolução NF-e-driven (Fase B):
    devolution_invoice_id = Column(Integer, ForeignKey("invoices.id"))  # NF-e de devolução (entrada)
    discard_invoice_id = Column(Integer, ForeignKey("invoices.id"))  # nota de descarte (não-apto)
    referenced_access_key = Column(String(50))  # chave da NF-e de venda referenciada (refNFe)
    supplier_notes = Column(String)
    credit_amount = Column(Numeric(15, 2))
    validation_notes = Column(String)
    validated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    validation_photos_json = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

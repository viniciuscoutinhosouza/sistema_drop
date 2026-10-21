from sqlalchemy import (
    TIMESTAMP,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class PaymentCharge(Base):
    """Cobrança criada num gateway (ASAAS) para um pedido, pela conta de recebimento do Galpão.

    Migration 153 (ADR-0032). O `asaas_payment_id` (único) é a âncora do webhook: o evento é
    casado por ESTE id (que nós criamos), nunca por order_id vindo do corpo. `order_id` liga a
    cobrança ao pedido de forma persistida e confiável.
    """

    __tablename__ = "payment_charges"
    __table_args__ = (UniqueConstraint("asaas_payment_id", name="uq_pay_charge_asaas_id"),)

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    bank_account_id = Column(Integer, ForeignKey("warehouse_bank_accounts.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"))
    provider = Column(String(20), nullable=False, server_default=text("'asaas'"))
    asaas_customer_id = Column(String(60))
    asaas_payment_id = Column(String(60), nullable=False)
    billing_type = Column(String(20))  # PIX | BOLETO | CREDIT_CARD | UNDEFINED
    value = Column(Numeric(15, 2))
    # Status do ASAAS: PENDING | RECEIVED | CONFIRMED | OVERDUE | REFUNDED | ... (string crua do gateway)
    status = Column(String(30))
    invoice_url = Column(String(500))   # link de pagamento (checkout ASAAS)
    bank_slip_url = Column(String(500))  # PDF do boleto
    pix_payload = Column(String(2000))   # copia-e-cola do Pix (quando buscado)
    due_date = Column(Date)
    external_reference = Column(String(100))  # = order.id (nossa referência)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    order = relationship("Order")

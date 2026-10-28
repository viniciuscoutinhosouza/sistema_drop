from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, text

from database import Base


class OrderPaymentProof(Base):
    """Trilha append-only de confirmação/cancelamento MANUAL de pagamento de um pedido.

    Complementa o ASAAS (PaymentCharge/charge_service): aqui o operador registra que o pagamento
    foi feito (COMO + comprovante) ou cancela um pagamento informando o motivo. O comprovante vai
    para o Google Drive (ADR-0038, área 'Comprovantes'); guardamos só o `proof_drive_id`.
    O estado corrente é derivado (último 'confirm' ainda não cancelado). Append-only.
    """

    __tablename__ = "order_payment_proofs"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    event_type = Column(String(10), nullable=False)  # 'confirm' | 'cancel'
    payment_method = Column(String(50))              # como foi pago (Pix, dinheiro, transferência…)
    description = Column(String(1000))
    proof_drive_id = Column(String(100))             # id do comprovante no Google Drive
    proof_mime = Column(String(30))                  # mime do comprovante (image/jpeg|png|webp)
    reason = Column(String(1000))                    # motivo do cancelamento
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

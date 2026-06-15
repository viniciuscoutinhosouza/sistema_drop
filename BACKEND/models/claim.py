"""
Reclamações pós-venda (claims) do Mercado Livre, por conta CMIG.
Persiste a reclamação, as mensagens dos 2 canais (comprador/mediador), o
histórico de ações e os status. Distinto de `models.return_.Return` (devolução
FÍSICA do galpão) — ver ADR-0007.
"""

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sa_text
from sqlalchemy.orm import relationship

from database import Base


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)
    marketplace_account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    platform = Column(String(30), nullable=False, default="mercadolivre")
    platform_claim_id = Column(String(50), nullable=False)
    resource_id = Column(String(50))
    order_id = Column(Integer)  # Order interno (quando casar)
    platform_order_id = Column(String(50))
    status = Column(String(20))  # opened | closed
    stage = Column(String(20))  # claim | dispute | recontact | stale | none
    claim_type = Column("claim_type", String(30))  # mediations | return | fulfillment | ml_case
    reason_id = Column(String(30))  # PNR | PDD | CS ...
    reason_label = Column(String(200))
    fulfilled = Column(Boolean, default=False)
    quantity_type = Column(String(20))  # total | partial
    affects_reputation = Column(String(20))  # affected | not_affected | not_applies
    title = Column(String(500))
    description = Column(Text)
    problem = Column(String(500))
    buyer_platform_id = Column(String(50))
    buyer_nickname = Column(String(200))
    item_id = Column(String(50))
    item_title = Column(String(500))
    thumbnail = Column(String(1000))  # foto de capa do anúncio (da OrderItem)
    quantity = Column(Integer)
    amount = Column(Numeric(15, 2))
    available_actions_json = Column(Text)
    has_return = Column(Boolean, default=False)
    related_return_id = Column(String(50))
    resolution_json = Column(Text)
    due_date = Column(TIMESTAMP(timezone=True))
    ml_date_created = Column(TIMESTAMP(timezone=True))
    ml_last_updated = Column(TIMESTAMP(timezone=True))
    last_message_at = Column(TIMESTAMP(timezone=True))
    synced_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=sa_text("SYSTIMESTAMP"),
        onupdate=sa_text("SYSTIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "platform_claim_id", "marketplace_account_id", name="uq_claims_platform"
        ),
    )

    account = relationship("MarketplaceAccount")
    messages = relationship(
        "ClaimMessage",
        back_populates="claim",
        order_by="ClaimMessage.sent_at",
        cascade="all, delete-orphan",
    )
    actions = relationship(
        "ClaimAction",
        back_populates="claim",
        order_by="ClaimAction.date_created.desc()",
        cascade="all, delete-orphan",
    )


class ClaimMessage(Base):
    __tablename__ = "claim_messages"

    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    channel = Column(String(20), nullable=False)  # complainant | mediator
    sender_role = Column(String(20))  # complainant | respondent | mediator
    text = Column("text_content", Text)
    translated_text = Column(Text)
    attachments_json = Column(Text)
    status = Column(String(20))  # available | blocked
    stage = Column(String(20))
    platform_hash = Column(String(200))  # dedupe (UNIQUE)
    is_read = Column(Boolean, nullable=False, default=False)
    sent_at = Column(TIMESTAMP(timezone=True))
    synced_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    ai_suggested_text = Column(Text)

    claim = relationship("Claim", back_populates="messages")


class ClaimAction(Base):
    __tablename__ = "claim_actions"

    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    action_name = Column(String(60))
    player_role = Column(String(20))
    claim_stage = Column(String(20))
    claim_status = Column(String(20))
    label_pt = Column(String(200))
    triggered_by_user_id = Column(Integer)  # quem disparou (ação local) — auditoria
    date_created = Column(TIMESTAMP(timezone=True))
    synced_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))

    claim = relationship("Claim", back_populates="actions")


class MessageTemplate(Base):
    """Mensagens Prontas (templates de resposta) — escopo por CMIG ou por usuário."""

    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer)  # NULL = template pessoal do usuário
    user_id = Column(Integer)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=sa_text("SYSTIMESTAMP"),
        onupdate=sa_text("SYSTIMESTAMP"),
    )

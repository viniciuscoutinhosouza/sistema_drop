from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sa_text
from sqlalchemy.orm import relationship

from database import Base


class ConversationThread(Base):
    """Thread de atendimento unificada — suporta qualquer marketplace."""

    __tablename__ = "conversation_threads"

    id = Column(Integer, primary_key=True)
    marketplace_account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    platform = Column(String(30), nullable=False)  # mercadolivre | shopee | amazon | tiktok
    thread_type = Column(String(30), nullable=False)  # post_sale | pre_sale_question
    platform_thread_id = Column(String(100), nullable=False)  # pack_id ou question_id
    platform_order_id = Column(String(100))  # order_id (pós-venda)
    buyer_platform_id = Column(String(100))
    buyer_nickname = Column(String(200))
    item_id = Column(String(100))  # anúncio (pré-venda e pós-venda enriquecido)
    item_title = Column(String(500))
    item_thumbnail = Column(String(1000))  # foto de capa do anúncio
    item_permalink = Column(String(1000))  # link do anúncio no marketplace
    status = Column(
        String(30), nullable=False, default="open"
    )  # open | pending_reply | closed | answered
    unread_count = Column(Integer, nullable=False, default=0)
    is_archived = Column(Boolean, nullable=False, default=False)
    last_message_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=sa_text("SYSTIMESTAMP"),
        onupdate=sa_text("SYSTIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "platform", "platform_thread_id", "marketplace_account_id", name="uq_thread_platform_id"
        ),
    )

    account = relationship("MarketplaceAccount")
    messages = relationship(
        "ConversationMessage",
        back_populates="thread",
        order_by="ConversationMessage.sent_at",
        cascade="all, delete-orphan",
    )


class ConversationMessage(Base):
    """Mensagem individual dentro de uma thread."""

    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("conversation_threads.id"), nullable=False)
    platform_message_id = Column(String(200), unique=True)
    from_role = Column(String(20), nullable=False)  # buyer | seller | system | ai
    from_platform_id = Column(String(100))
    text = Column("text_content", Text)
    attachments_json = Column(Text)
    is_read = Column(Boolean, nullable=False, default=False)
    sent_at = Column(TIMESTAMP(timezone=True))
    synced_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    ai_suggested_text = Column(
        "ai_suggested_text", Text
    )  # audit: o que a IA sugeriu antes do envio

    thread = relationship("ConversationThread", back_populates="messages")


class AIConfig(Base):
    """Configuração global de IA — singleton (espera-se apenas 1 linha)."""

    __tablename__ = "ai_configs"

    id = Column(Integer, primary_key=True)
    provider = Column(String(20), nullable=False, default="anthropic")  # openai | anthropic
    api_key = Column(String(2000))  # armazenado em base64
    model_name = Column(String(100), default="claude-sonnet-4-6")
    global_instructions = Column(Text)
    is_active = Column(Boolean, nullable=False, default=False)
    # IA de mídia (imagens) — independente do provider de chat acima.
    media_provider = Column(String(20), default="google")  # google (Gemini / Nano Banana)
    media_api_key = Column(String(2000))  # base64
    media_image_model = Column(String(100), default="gemini-2.5-flash-image")
    media_video_model = Column(String(100), default="veo-3.1-fast-generate-preview")
    media_instructions = Column(Text)  # perfil/instruções base p/ todos os prompts de mídia
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=sa_text("SYSTIMESTAMP"),
        onupdate=sa_text("SYSTIMESTAMP"),
    )


class CMIGAIConfig(Base):
    """Configuração de IA por CMIG — instruções e modo de resposta específicos."""

    __tablename__ = "cmig_ai_configs"

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False, unique=True)
    custom_instructions = Column(Text)
    auto_respond = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=sa_text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=sa_text("SYSTIMESTAMP"),
        onupdate=sa_text("SYSTIMESTAMP"),
    )

    cmig = relationship("CMIG")

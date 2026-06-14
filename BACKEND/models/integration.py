from sqlalchemy import (
    TIMESTAMP,
    Boolean,
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


class MarketplaceAccount(Base):
    """
    CONTA de Marketplace — entidade central do sistema.
    Identificada unicamente por (platform, email, phone).
    Pode ser co-administrada por múltiplos ACs via AccountAdministrator.
    """

    __tablename__ = "marketplace_accounts"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=True)
    platform = Column(String(20), nullable=False)  # mercadolivre | shopee | bling
    description = Column(String(200))  # Apelido interno
    email = Column(String(255))  # E-mail da conta no marketplace
    phone = Column(String(20))  # Celular da conta no marketplace
    access_token = Column(String(2000))
    refresh_token = Column(String(2000))
    token_expires_at = Column(TIMESTAMP(timezone=True))
    platform_user_id = Column(String(200))
    platform_username = Column(String(200))
    shop_id = Column(Integer)  # Shopee shop ID
    api_key = Column(String(500))  # Para Bling
    is_active = Column(Boolean, nullable=False, default=False)
    is_official_store = Column(
        Boolean, nullable=False, default=False
    )  # Loja Oficial ML — permite editar título
    otp_verified = Column(Boolean, nullable=False, default=False)
    requires_reauth = Column(Boolean, nullable=False, default=False)
    last_sync_at = Column(TIMESTAMP(timezone=True))
    # Reputação ML (medalhas) — refresh diário via tasks.scheduler.refresh_ml_reputation
    power_seller_status = Column(String(20))  # platinum | gold | silver | None
    level_id = Column(String(20))  # 5_green | 4_light_green | 3_yellow | 2_orange | 1_red | None
    reputation_cached_at = Column(TIMESTAMP(timezone=True))
    # Capacidades de envio detectadas via API ML (auto-detectadas + override manual)
    # NULL no override = usa o has_*; TRUE/FALSE = override do admin
    has_flex = Column(Boolean, nullable=False, default=False)
    has_full = Column(Boolean, nullable=False, default=False)
    has_flex_override = Column(Boolean, nullable=True)
    has_full_override = Column(Boolean, nullable=True)
    shipping_modes_checked_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    @property
    def effective_has_flex(self) -> bool:
        """Retorna has_flex_override se admin marcou; senão o detectado."""
        return self.has_flex_override if self.has_flex_override is not None else bool(self.has_flex)

    @property
    def effective_has_full(self) -> bool:
        return self.has_full_override if self.has_full_override is not None else bool(self.has_full)

    __table_args__ = (
        UniqueConstraint("platform", "email", "phone", name="uq_account_platform_email_phone"),
    )

    administrators = relationship(
        "AccountAdministrator", back_populates="account", cascade="all, delete-orphan"
    )
    balance = relationship("AccountBalance", back_populates="account", uselist=False)
    cmig = relationship("CMIG", back_populates="accounts")
    nfe_configs = relationship("NFeConfig", back_populates="cm", cascade="all, delete-orphan")


class AccountBalance(Base):
    """Saldo da conta corrente operacional por CONTA de marketplace."""

    __tablename__ = "account_balances"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False, unique=True)
    balance = Column(Numeric(15, 2), nullable=False, default=0)
    balance_reserved = Column(Numeric(15, 2), nullable=False, default=0)
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    account = relationship("MarketplaceAccount", back_populates="balance")
    transactions = relationship("AccountTransaction", back_populates="account_balance")


class AccountTransaction(Base):
    """Extrato financeiro operacional por CONTA (etiquetas, NFs, taxas, créditos PIX)."""

    __tablename__ = "account_transactions"

    id = Column(Integer, primary_key=True)
    account_balance_id = Column(Integer, ForeignKey("account_balances.id"), nullable=False)
    type = Column(String(10), nullable=False)  # credit | debit
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(String(500))
    reference_type = Column(String(50))  # order | pix_deposit | label | nfe | fee
    reference_id = Column(Integer)
    pix_key = Column(String(100))
    pix_txid = Column(String(200))
    status = Column(String(20), nullable=False, default="pending")  # pending | completed | failed
    balance_before = Column(Numeric(15, 2))
    balance_after = Column(Numeric(15, 2))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    account_balance = relationship("AccountBalance", back_populates="transactions")


class OTPVerification(Base):
    """Códigos OTP para verificação de vínculo de CONTA de marketplace."""

    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    code = Column(String(6), nullable=False)
    channel = Column(String(10), nullable=False)  # email | whatsapp
    destination = Column(String(255), nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))


class MarketplaceMetricDaily(Base):
    """
    Snapshot diário (BRT) de métricas que só existem na API do Mercado Livre
    e não são persistidas em nenhuma outra tabela: visitas, perguntas e gasto
    em ADS. Alimentada pelo job tasks/sync_marketplace_metrics.py (4x/dia),
    com upsert por (account_id, metric_date). Pedidos/Faturamento NÃO entram
    aqui — são calculados ao vivo da tabela orders no endpoint do dashboard.
    """

    __tablename__ = "marketplace_metrics_daily"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    metric_date = Column(Date, nullable=False)  # dia comercial em BRT
    visits = Column(Integer, nullable=False, default=0)
    questions_total = Column(Integer, nullable=False, default=0)
    questions_unanswered = Column(Integer, nullable=False, default=0)
    ads_cost = Column(Numeric(15, 2), nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("SYSTIMESTAMP"),
        onupdate=text("SYSTIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("account_id", "metric_date", name="uq_mmd_account_date"),
    )


class MarketplaceSetting(Base):
    """Configuração por marketplace (Super Admin). 1 linha por marketplace;
    `settings_json` (CLOB) guarda config flexível (formatos de mídia, prompts, etc.)
    para permitir novos campos sem migration. NÃO guardar credenciais aqui."""

    __tablename__ = "marketplace_settings"

    id = Column(Integer, primary_key=True)
    marketplace = Column(String(20), nullable=False, unique=True)
    settings_json = Column(String)  # CLOB (JSON)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("SYSTIMESTAMP"),
        onupdate=text("SYSTIMESTAMP"),
    )


class MediaClipJob(Base):
    """Geração assíncrona de clip/vídeo por IA (Veo). Persiste a operation
    long-running para sobreviver a reload, consultar status e listar os clips
    gerados (o resultado é pago — não pode se perder)."""

    __tablename__ = "media_clip_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    operation = Column(String(500), nullable=False)
    marketplace = Column(String(20))
    product_type = Column(String(10))   # 'pg' | 'cmig' | None — associa o clip ao produto
    product_id = Column(Integer)
    prompt = Column(String(1100))
    status = Column(String(20), nullable=False, default="running")  # running|done|failed
    video_url = Column(String(1000))
    error = Column(String(500))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("SYSTIMESTAMP"),
        onupdate=text("SYSTIMESTAMP"),
    )

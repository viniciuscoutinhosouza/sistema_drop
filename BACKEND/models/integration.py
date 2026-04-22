from sqlalchemy import Column, Integer, String, Boolean, Numeric, TIMESTAMP, ForeignKey, text, UniqueConstraint
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
    cmig_id  = Column(Integer, ForeignKey("cmigs.id"), nullable=True)
    platform = Column(String(20), nullable=False)   # mercadolivre | shopee | bling
    description = Column(String(200))               # Apelido interno
    email = Column(String(255))                     # E-mail da conta no marketplace
    phone = Column(String(20))                      # Celular da conta no marketplace
    access_token = Column(String(2000))
    refresh_token = Column(String(2000))
    token_expires_at = Column(TIMESTAMP(timezone=True))
    platform_user_id = Column(String(200))
    platform_username = Column(String(200))
    shop_id = Column(Integer)                       # Shopee shop ID
    api_key = Column(String(500))                   # Para Bling
    is_active = Column(Boolean, nullable=False, default=True)
    otp_verified = Column(Boolean, nullable=False, default=False)
    last_sync_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("platform", "email", "phone", name="uq_account_platform_email_phone"),
    )

    administrators = relationship("AccountAdministrator", back_populates="account", cascade="all, delete-orphan")
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
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

    account = relationship("MarketplaceAccount", back_populates="balance")
    transactions = relationship("AccountTransaction", back_populates="account_balance")


class AccountTransaction(Base):
    """Extrato financeiro operacional por CONTA (etiquetas, NFs, taxas, créditos PIX)."""
    __tablename__ = "account_transactions"

    id = Column(Integer, primary_key=True)
    account_balance_id = Column(Integer, ForeignKey("account_balances.id"), nullable=False)
    type = Column(String(10), nullable=False)        # credit | debit
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(String(500))
    reference_type = Column(String(50))             # order | pix_deposit | label | nfe | fee
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
    channel = Column(String(10), nullable=False)    # email | whatsapp
    destination = Column(String(255), nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

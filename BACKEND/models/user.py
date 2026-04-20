from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Numeric,
    TIMESTAMP, ForeignKey, text
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="ac")  # ugo | ac | admin
    full_name = Column(String(255), nullable=False)
    whatsapp = Column(String(20))
    cpf_cnpj = Column(String(18), unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    dark_mode = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

    profile = relationship("ACProfile", back_populates="user", uselist=False)
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    # Contas de marketplace que este AC co-administra
    administered_accounts = relationship("AccountAdministrator", back_populates="user", cascade="all, delete-orphan")


class ACProfile(Base):
    """Perfil do Administrador de Conta (AC). Contém endereço e vínculo com plano de acesso."""
    __tablename__ = "ac_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    zip_code = Column(String(9))
    street = Column(String(255))
    address_number = Column(String(20))
    complement = Column(String(100))
    neighborhood = Column(String(100))
    city = Column(String(100))
    state = Column(String(2))
    plan_id = Column(Integer, ForeignKey("access_plans.id"))
    subscription_status = Column(String(20), nullable=False, default="active")  # active | overdue | suspended
    subscription_due_date = Column(Date)
    balance = Column(Numeric(15, 2), nullable=False, default=0)
    balance_reserved = Column(Numeric(15, 2), nullable=False, default=0)

    user = relationship("User", back_populates="profile")
    plan = relationship("AccessPlan", back_populates="subscribers")
    subscription = relationship("ACSubscription", back_populates="profile", uselist=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    user = relationship("User", back_populates="refresh_tokens")


class AccessPlan(Base):
    """Planos de acesso para AC — cobrados por número de CONTAs ativas."""
    __tablename__ = "access_plans"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    max_accounts = Column(Integer, nullable=False)  # -1 = ilimitado
    monthly_price = Column(Numeric(10, 2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    subscribers = relationship("ACProfile", back_populates="plan")


class ACSubscription(Base):
    """Histórico de assinaturas do AC."""
    __tablename__ = "ac_subscriptions"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("ac_profiles.id"), nullable=False, unique=True)
    plan_id = Column(Integer, ForeignKey("access_plans.id"), nullable=False)
    status = Column(String(20), nullable=False, default="active")  # active | overdue | cancelled
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    profile = relationship("ACProfile", back_populates="subscription")
    plan = relationship("AccessPlan")


class AccountAdministrator(Base):
    """Tabela many-to-many: AC <-> MarketplaceAccount (CONTA)."""
    __tablename__ = "account_administrators"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    is_owner = Column(Boolean, nullable=False, default=False)  # True = AC que criou a CONTA
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    user = relationship("User", back_populates="administered_accounts")
    account = relationship("MarketplaceAccount", back_populates="administrators")

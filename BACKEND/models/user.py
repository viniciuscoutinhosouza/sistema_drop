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
    role = Column(String(20), nullable=False, default="dropshipper")  # supplier | dropshipper | admin
    full_name = Column(String(255), nullable=False)
    whatsapp = Column(String(20))
    cpf_cnpj = Column(String(18), unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    dark_mode = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

    profile = relationship("DropshipperProfile", back_populates="user", uselist=False)
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class DropshipperProfile(Base):
    __tablename__ = "dropshipper_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    zip_code = Column(String(9))
    street = Column(String(255))
    number = Column(String(20))
    complement = Column(String(100))
    neighborhood = Column(String(100))
    city = Column(String(100))
    state = Column(String(2))
    subscription_status = Column(String(20), nullable=False, default="active")
    subscription_due_date = Column(Date)
    balance = Column(Numeric(15, 2), nullable=False, default=0)
    balance_reserved = Column(Numeric(15, 2), nullable=False, default=0)

    user = relationship("User", back_populates="profile")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    user = relationship("User", back_populates="refresh_tokens")

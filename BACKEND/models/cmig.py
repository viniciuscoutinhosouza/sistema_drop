from sqlalchemy import Column, Integer, String, Boolean, Numeric, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base


class CMIG(Base):
    """Conta MIG — representa um CNPJ físico do AC; agrupa CMs e gerencia estoque/NF-e."""
    __tablename__ = "cmigs"

    id           = Column(Integer, primary_key=True)
    owner_ac_id  = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    cnpj         = Column(String(18), nullable=False, unique=True)
    company_name = Column(String(255), nullable=False)
    trade_name   = Column(String(255))
    email        = Column(String(255))
    phone        = Column(String(20))
    zip_code     = Column(String(9))
    street       = Column(String(255))
    address_number = Column(String(20))
    complement   = Column(String(100))
    neighborhood = Column(String(100))
    city         = Column(String(100))
    state        = Column(String(2))
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at   = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                          onupdate=text("SYSTIMESTAMP"))

    owner_ac   = relationship("User", back_populates="owned_cmigs", foreign_keys=[owner_ac_id])
    warehouse  = relationship("Warehouse", back_populates="cmigs")
    administrators = relationship("CMIGAdministrator", back_populates="cmig", cascade="all, delete-orphan")
    products   = relationship("CMIGProduct", back_populates="cmig", cascade="all, delete-orphan")
    accounts   = relationship("MarketplaceAccount", back_populates="cmig")


class CMIGAdministrator(Base):
    """M:M — AC co-administra CMIG."""
    __tablename__ = "cmig_administrators"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    cmig_id    = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    is_owner   = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    user = relationship("User", back_populates="administered_cmigs", foreign_keys=[user_id])
    cmig = relationship("CMIG", back_populates="administrators")


class CMIGProduct(Base):
    """Produto específico de uma CMIG; identificado por SKU CMIG; estoque independente do PG."""
    __tablename__ = "cmig_products"

    id             = Column(Integer, primary_key=True)
    cmig_id        = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    sku_cmig       = Column(String(100), nullable=False)
    title          = Column(String(255), nullable=False)
    description    = Column(String(4000))
    brand          = Column(String(100))
    cost_price     = Column(Numeric(10, 2))
    stock_quantity = Column(Integer, nullable=False, default=0)
    weight_kg      = Column(Numeric(8, 3))
    height_cm      = Column(Numeric(8, 2))
    width_cm       = Column(Numeric(8, 2))
    length_cm      = Column(Numeric(8, 2))
    ncm            = Column(String(8))
    cest           = Column(String(7))
    origin         = Column(Integer, default=0)
    pg_product_id  = Column(Integer, ForeignKey("catalog_products.id"), nullable=True)
    is_active      = Column(Boolean, nullable=False, default=True)
    created_at     = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at     = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                            onupdate=text("SYSTIMESTAMP"))

    cmig       = relationship("CMIG", back_populates="products")
    pg_product = relationship("CatalogProduct", back_populates="cmig_products")
    images     = relationship("CMIGProductImage", back_populates="product", cascade="all, delete-orphan")


class CMIGProductImage(Base):
    __tablename__ = "cmig_product_images"

    id              = Column(Integer, primary_key=True)
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=False)
    url             = Column(String(1000), nullable=False)
    sort_order      = Column(Integer, nullable=False, default=0)
    is_primary      = Column(Boolean, nullable=False, default=False)

    product = relationship("CMIGProduct", back_populates="images")

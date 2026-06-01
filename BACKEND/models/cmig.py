from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.orm import relationship

from database import Base


class CMIG(Base):
    """Conta MIG — pode ser PJ (CNPJ + Razão Social) ou PF (CPF + Nome). CNPJ/Razão Social podem ser adicionados depois."""

    __tablename__ = "cmigs"

    id = Column(Integer, primary_key=True)
    owner_ac_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    cnpj = Column(String(18), nullable=True, unique=True)
    cpf = Column(String(14), nullable=True, unique=True)
    company_name = Column(String(255), nullable=True)  # Razão Social (PJ) ou Nome (PF)
    trade_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(20))
    zip_code = Column(String(9))
    street = Column(String(255))
    address_number = Column(String(20))
    complement = Column(String(100))
    neighborhood = Column(String(100))
    city = Column(String(100))
    state = Column(String(2))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    owner_ac = relationship("User", back_populates="owned_cmigs", foreign_keys=[owner_ac_id])
    warehouse = relationship("Warehouse", back_populates="cmigs")
    administrators = relationship(
        "CMIGAdministrator", back_populates="cmig", cascade="all, delete-orphan"
    )
    products = relationship("CMIGProduct", back_populates="cmig", cascade="all, delete-orphan")
    accounts = relationship("MarketplaceAccount", back_populates="cmig")
    people = relationship("Person", back_populates="cmig", cascade="all, delete-orphan")
    fiscal_config = relationship(
        "CMIGFiscalConfig", back_populates="cmig", uselist=False, cascade="all, delete-orphan"
    )


class CMIGAdministrator(Base):
    """M:M — AC co-administra CMIG."""

    __tablename__ = "cmig_administrators"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    is_owner = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    user = relationship("User", back_populates="administered_cmigs", foreign_keys=[user_id])
    cmig = relationship("CMIG", back_populates="administrators")


class CMIGProduct(Base):
    """Produto específico de uma CMIG; identificado por SKU CMIG; estoque independente do PG."""

    __tablename__ = "cmig_products"

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    sku_cmig = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(String(4000))
    brand = Column(String(100))
    model = Column(String(200))
    ean = Column(String(14))
    cost_price = Column(Numeric(10, 2))
    stock_quantity = Column(Integer, nullable=False, default=0)           # estoque físico
    reserved_quantity = Column(Integer, nullable=False, default=0)        # reservado por pedidos ativos
    awaiting_return_quantity = Column(Integer, nullable=False, default=0)
    pending_validation_quantity = Column(Integer, nullable=False, default=0)
    unfit_quantity = Column(Integer, nullable=False, default=0)
    weight_kg = Column(Numeric(8, 3))
    height_cm = Column(Numeric(8, 2))
    width_cm = Column(Numeric(8, 2))
    length_cm = Column(Numeric(8, 2))
    ncm = Column(String(8))
    cest = Column(String(7))
    origin = Column(Integer, default=0)
    csosn = Column(String(3))  # ICMS CSOSN para Faturador ML (ex: "102" Simples Nacional)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    suggested_price = Column(Numeric(15, 2))
    video_id = Column(String(100))
    attributes_json = Column(Text)
    pictures_json = Column(Text)
    fiscal_json = Column(String(2000))
    pg_product_id = Column(Integer, ForeignKey("catalog_products.id"), nullable=True)
    # Rastreabilidade da origem quando criado a partir de uma variacao de anuncio ML.
    # `source_listing_id` aponta pro ProductListing pai e `source_variation_id` para
    # o `id` da variacao especifica (em variations_json). Permite marcar na UI quais
    # variacoes ja foram importadas e bloquear duplicacao.
    source_listing_id = Column(Integer, ForeignKey("product_listings.id"), nullable=True)
    source_variation_id = Column(String(100), nullable=True)
    is_composite = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    cmig = relationship("CMIG", back_populates="products")
    pg_product = relationship("CatalogProduct", back_populates="cmig_products")
    category = relationship("Category", lazy="joined")
    images = relationship(
        "CMIGProductImage", back_populates="product", cascade="all, delete-orphan"
    )
    variants = relationship(
        "CMIGProductVariant", back_populates="product", cascade="all, delete-orphan"
    )
    components = relationship(
        "CMIGProductComponent",
        foreign_keys="CMIGProductComponent.composite_id",
        back_populates="composite",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    marketplace_categories = relationship(
        "ProductMarketplaceCategory",
        foreign_keys="ProductMarketplaceCategory.cmig_product_id",
        back_populates="cmig_product",
        cascade="all, delete-orphan",
    )

    @property
    def available_quantity(self) -> int:
        return max(0, (self.stock_quantity or 0) - (self.reserved_quantity or 0))

    @property
    def physical_quantity(self) -> int:
        return self.stock_quantity or 0

    @property
    def category_name(self):
        return self.category.name if self.category else None


class CMIGProductImage(Base):
    __tablename__ = "cmig_product_images"

    id = Column(Integer, primary_key=True)
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, nullable=False, default=False)

    product = relationship("CMIGProduct", back_populates="images")


class CMIGProductVariant(Base):
    __tablename__ = "cmig_product_variants"

    id = Column(Integer, primary_key=True)
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=False)
    sku = Column(String(100), nullable=False, unique=True)
    variant_name = Column(String(255))
    color = Column(String(100))
    size_label = Column(String(100))
    voltage = Column(String(50))
    stock_quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    awaiting_return_quantity = Column(Integer, nullable=False, default=0)
    pending_validation_quantity = Column(Integer, nullable=False, default=0)
    unfit_quantity = Column(Integer, nullable=False, default=0)
    price_modifier = Column(Numeric(15, 2), default=0)
    suggested_price = Column(Numeric(15, 2))
    attributes_json = Column(String(2000))

    @property
    def available_quantity(self) -> int:
        return max(0, (self.stock_quantity or 0) - (self.reserved_quantity or 0))

    product = relationship("CMIGProduct", back_populates="variants")


class CMIGProductComponent(Base):
    """Componente de um Produto CMIG Composto — referencia um CMIGProduct ou CatalogProduct."""

    __tablename__ = "cmig_product_components"

    id = Column(Integer, primary_key=True)
    composite_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=False)
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=True)
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)

    composite = relationship(
        "CMIGProduct", foreign_keys=[composite_id], back_populates="components"
    )
    cmig_product = relationship("CMIGProduct", foreign_keys=[cmig_product_id], lazy="selectin")
    catalog_product = relationship(
        "CatalogProduct", foreign_keys=[catalog_product_id], lazy="selectin"
    )

from sqlalchemy import Column, Integer, String, Numeric, Boolean, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"))
    ml_category_id = Column(String(50))
    shopee_category_id = Column(Integer)

    children = relationship("Category", backref="parent", remote_side=[id])
    products = relationship("CatalogProduct", back_populates="category")


class CatalogProduct(Base):
    __tablename__ = "catalog_products"

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    sku = Column(String(100), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    description = Column(String)  # CLOB
    cost_price = Column(Numeric(15, 2), nullable=False)
    suggested_price = Column(Numeric(15, 2))
    weight_kg = Column(Numeric(8, 3))
    height_cm = Column(Numeric(8, 2))
    width_cm = Column(Numeric(8, 2))
    length_cm = Column(Numeric(8, 2))
    ncm = Column(String(10))
    cest = Column(String(7))
    brand = Column(String(100))
    model = Column(String(200))
    ean = Column(String(14))
    origin = Column(Integer, default=0)
    category_id = Column(Integer, ForeignKey("categories.id"))
    stock_quantity = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

    category = relationship("Category", back_populates="products")
    images = relationship("CatalogProductImage", back_populates="product",
                          order_by="CatalogProductImage.sort_order", cascade="all, delete-orphan")
    variants = relationship("CatalogProductVariant", back_populates="product",
                            cascade="all, delete-orphan")
    cmig_products = relationship("CMIGProduct", back_populates="pg_product")


class CatalogProductImage(Base):
    __tablename__ = "catalog_product_images"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("catalog_products.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    sort_order = Column(Integer, default=0)
    is_primary = Column(Boolean, default=False)

    product = relationship("CatalogProduct", back_populates="images")


class CatalogProductVariant(Base):
    __tablename__ = "catalog_product_variants"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("catalog_products.id"), nullable=False)
    sku = Column(String(100), nullable=False, unique=True)
    variant_name = Column(String(255))
    color = Column(String(100))
    size = Column(String(100))
    voltage = Column(String(50))
    stock_quantity = Column(Integer, nullable=False, default=0)
    price_modifier = Column(Numeric(15, 2), default=0)
    attributes_json = Column(String(2000))

    product = relationship("CatalogProduct", back_populates="variants")


class DropshipperProduct(Base):
    __tablename__ = "dropshipper_products"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"))
    kit_id = Column(Integer, ForeignKey("kits.id"))
    title = Column(String(500), nullable=False)
    title_ml = Column(String(60))
    title_shopee = Column(String(100))
    sale_price_ml = Column(Numeric(15, 2))
    sale_price_shopee = Column(Numeric(15, 2))
    ml_item_id = Column(String(100))
    ml_category_id = Column(String(50))
    ml_listing_type = Column(String(20))
    shopee_item_id = Column(Integer)
    shopee_category_id = Column(Integer)
    bling_product_id = Column(Integer)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

    images = relationship("DropshipperProductImage", back_populates="product",
                          cascade="all, delete-orphan")
    listings = relationship("ProductListing", back_populates="product",
                            cascade="all, delete-orphan")


class DropshipperProductImage(Base):
    __tablename__ = "dropshipper_product_images"

    id = Column(Integer, primary_key=True)
    dropshipper_product_id = Column(Integer, ForeignKey("dropshipper_products.id"), nullable=False)
    url = Column(String(1000), nullable=False)
    sort_order = Column(Integer, default=0)
    is_primary = Column(Boolean, default=False)

    product = relationship("DropshipperProduct", back_populates="images")


class ProductListing(Base):
    __tablename__ = "product_listings"

    id                 = Column(Integer, primary_key=True)
    product_id         = Column(Integer, ForeignKey("dropshipper_products.id", ondelete="CASCADE"), nullable=True)
    account_id         = Column(Integer, ForeignKey("marketplace_accounts.id", ondelete="CASCADE"), nullable=False)
    cmig_product_id    = Column(Integer, ForeignKey("cmig_products.id"), nullable=True)
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"), nullable=True)
    platform_item_id   = Column(String(200))
    permalink          = Column(String(1000))
    thumbnail          = Column(String(1000))
    sku                = Column(String(100))
    weight_kg          = Column(Numeric(8, 3))
    height_cm          = Column(Numeric(8, 2))
    width_cm           = Column(Numeric(8, 2))
    length_cm          = Column(Numeric(8, 2))
    pictures_json      = Column(String)         # CLOB
    fiscal_json        = Column(String(2000))
    variations_json    = Column(String)         # CLOB
    sale_price         = Column(Numeric(15, 2), nullable=False)
    title_override     = Column(String(500))
    category_id        = Column(String(100))
    category_name      = Column(String(200))
    listing_type       = Column(String(20))
    is_full            = Column(Boolean, default=False)
    ml_catalog_id      = Column(String(200))
    status             = Column(String(20), nullable=False, default="draft")
    error_message      = Column(String(2000))
    published_at         = Column(TIMESTAMP(timezone=True))
    last_sync_at         = Column(TIMESTAMP(timezone=True))
    description_override = Column(String)            # CLOB
    attributes_json      = Column(String(4000))
    available_quantity   = Column(Integer, default=1)
    sold_quantity        = Column(Integer, default=0)
    visits_7d            = Column(Integer, default=0)
    item_condition       = Column(String(20), default="new")
    warranty_type        = Column(String(50))
    warranty_time        = Column(String(20))
    shipping_mode        = Column(String(20), default="me2")
    free_shipping        = Column(Boolean, default=False)
    video_id             = Column(String(100))
    created_at           = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at           = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                                  onupdate=text("SYSTIMESTAMP"))

    product         = relationship("DropshipperProduct", back_populates="listings")
    account         = relationship("MarketplaceAccount")
    cmig_product    = relationship("CMIGProduct")
    catalog_product = relationship("CatalogProduct")

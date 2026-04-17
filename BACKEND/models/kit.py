from sqlalchemy import Column, Integer, String, Numeric, Boolean, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base


class Kit(Base):
    __tablename__ = "kits"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sku = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(String)
    color = Column(String(100))
    size = Column(String(100))
    width_cm = Column(Numeric(8, 2))
    height_cm = Column(Numeric(8, 2))
    length_cm = Column(Numeric(8, 2))
    weight_kg = Column(Numeric(8, 3))
    ncm = Column(String(10))
    cest = Column(String(7))
    origin = Column(Integer, default=0)
    category_id = Column(Integer, ForeignKey("categories.id"))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    components = relationship("KitComponent", back_populates="kit", cascade="all, delete-orphan")


class KitComponent(Base):
    __tablename__ = "kit_components"

    id = Column(Integer, primary_key=True)
    kit_id = Column(Integer, ForeignKey("kits.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("catalog_products.id"))
    variant_id = Column(Integer, ForeignKey("catalog_product_variants.id"))
    quantity = Column(Integer, nullable=False, default=1)

    kit = relationship("Kit", back_populates="components")

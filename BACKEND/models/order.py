from sqlalchemy import Column, Integer, String, Numeric, Boolean, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"))
    platform = Column(String(20))
    platform_order_id = Column(String(200))
    platform_order_ref = Column(String(200))
    platform_status = Column(String(50))
    status = Column(String(30), nullable=False, default="downloaded")
    payment_status = Column(String(20), nullable=False, default="pending")
    buyer_name = Column(String(255))
    buyer_email = Column(String(255))
    buyer_document = Column(String(20))
    shipping_address = Column(String)   # JSON CLOB
    shipping_method = Column(String(100))
    tracking_code = Column(String(100))
    tracking_url = Column(String(500))
    label_url = Column(String(1000))
    sale_amount = Column(Numeric(15, 2))
    product_cost = Column(Numeric(15, 2))
    platform_fee = Column(Numeric(15, 2))
    shipping_cost = Column(Numeric(15, 2))
    total_debit = Column(Numeric(15, 2))
    is_hidden = Column(Boolean, default=False)
    notes = Column(String)
    paid_at = Column(TIMESTAMP(timezone=True))
    shipped_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                        onupdate=text("SYSTIMESTAMP"))

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    dropshipper_product_id = Column(Integer, ForeignKey("dropshipper_products.id"))
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"))
    catalog_variant_id = Column(Integer)
    sku = Column(String(100))
    title = Column(String(500))
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(15, 2))
    unit_cost = Column(Numeric(15, 2))

    order = relationship("Order", back_populates="items")

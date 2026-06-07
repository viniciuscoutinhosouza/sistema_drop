from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship

from database import Base


class PickingCart(Base):
    """Carrinho Gaiola — agrupa pedidos NÃO-FULL para separação e despacho."""

    __tablename__ = "picking_carts"

    id = Column(Integer, primary_key=True)
    cart_number = Column(String(30), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    cart_mode = Column(String(10), nullable=False, default="manual")  # manual | scan
    status = Column(String(15), nullable=False, default="open")  # open|separated|delivered|cancelled
    carrier_name = Column(String(120))
    notes = Column(String(500))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    separated_by = Column(Integer, ForeignKey("users.id"))
    separated_at = Column(TIMESTAMP(timezone=True))
    delivered_by = Column(Integer, ForeignKey("users.id"))
    delivered_at = Column(TIMESTAMP(timezone=True))

    orders = relationship(
        "PickingCartOrder", back_populates="cart", cascade="all, delete-orphan"
    )


class PickingCartOrder(Base):
    """Vínculo pedido ↔ gaiola, com status de separação do pedido."""

    __tablename__ = "picking_cart_orders"

    id = Column(Integer, primary_key=True)
    cart_id = Column(Integer, ForeignKey("picking_carts.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_status = Column(String(15), nullable=False, default="pending")  # pending | separated
    separated_by = Column(Integer, ForeignKey("users.id"))
    separated_at = Column(TIMESTAMP(timezone=True))
    label_printed_at = Column(TIMESTAMP(timezone=True))
    label_printed_by = Column(Integer, ForeignKey("users.id"))
    nfe_printed_at = Column(TIMESTAMP(timezone=True))
    nfe_printed_by = Column(Integer, ForeignKey("users.id"))

    cart = relationship("PickingCart", back_populates="orders")
    items = relationship(
        "PickingCartItem", back_populates="cart_order", cascade="all, delete-orphan"
    )


class PickingCartItem(Base):
    """Item esperado / progresso de bipagem (Processo 2). Kits viram N linhas."""

    __tablename__ = "picking_cart_items"

    id = Column(Integer, primary_key=True)
    cart_order_id = Column(Integer, ForeignKey("picking_cart_orders.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False)
    component_catalog_id = Column(Integer, nullable=True)  # null = item simples
    sku = Column(String(100))
    ean = Column(String(20))
    expected_qty = Column(Integer, nullable=False, default=1)
    scanned_qty = Column(Integer, nullable=False, default=0)

    cart_order = relationship("PickingCartOrder", back_populates="items")

from sqlalchemy import TIMESTAMP, Boolean, Column, Date, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.orm import relationship

from database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"))
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=True)
    platform = Column(String(20))
    platform_order_id = Column(String(200))
    platform_order_ref = Column(String(200))
    platform_status = Column(String(50))
    status = Column(String(30), nullable=False, default="downloaded")
    payment_status = Column(String(20), nullable=False, default="pending")
    buyer_name = Column(String(255))
    buyer_email = Column(String(255))
    buyer_document = Column(String(20))
    shipping_address = Column(String)  # JSON CLOB
    shipping_method = Column(String(100))
    shipping_mode = Column(String(20))  # full|flex|agencia|correios|coletado|combinado|desconhecido
    shipment_status = Column(String(50))
    tracking_code = Column(String(100))
    tracking_url = Column(String(500))
    shipment_id = Column(String(100))
    label_url = Column(String(1000))
    label_cached_at = Column(TIMESTAMP(timezone=True))  # quando a etiqueta foi salva no disco
    nfe_url = Column(String(1000))
    nfe_key = Column(String(50))
    nfe_status = Column(String(30))
    nfe_invoices_json = Column(
        String
    )  # CLOB — cache da lista de NF-e do Faturador ML (venda + referências)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    estimated_delivery_date = Column(Date)
    estimated_handling_limit = Column(Date)
    estimated_delivery_final = Column(Date)
    order_tags = Column(String(500))
    buyer_person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    sale_amount = Column(Numeric(15, 2))
    product_cost = Column(Numeric(15, 2))
    platform_fee = Column(Numeric(15, 2))  # tarifa ML (sale_fee somado dos itens)
    shipping_cost = Column(Numeric(15, 2))  # legacy / agregado
    buyer_shipping_paid = Column(Numeric(15, 2))  # frete que o comprador pagou
    seller_shipping_cost = Column(Numeric(15, 2))  # frete deduzido do vendedor (list_cost - cost)
    ml_fee_pct = Column(Numeric(8, 4))  # % da tarifa ML sobre o valor da venda
    total_debit = Column(Numeric(15, 2))
    is_hidden = Column(Boolean, default=False)
    notes = Column(String)
    paid_at = Column(TIMESTAMP(timezone=True))
    shipped_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    invoice = relationship("Invoice", foreign_keys=[invoice_id])
    buyer_person = relationship("Person", foreign_keys=[buyer_person_id])


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    dropshipper_product_id = Column(Integer, ForeignKey("dropshipper_products.id"))
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"))
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=True)
    catalog_variant_id = Column(Integer)
    sku = Column(String(100))
    title = Column(String(500))
    quantity = Column(Integer, nullable=False, default=1)
    ml_item_id = Column(String(200))
    unit_price = Column(Numeric(15, 2))
    unit_cost = Column(Numeric(15, 2))
    thumbnail_url = Column(String(1000))
    # 'pg' (Catalogo Geral) | 'cmig' (Catalogo CMIG) | NULL (pedidos historicos de marketplace)
    catalog_source = Column(String(10))

    order = relationship("Order", back_populates="items")

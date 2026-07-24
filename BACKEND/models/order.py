from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
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
    # 'CPF' | 'CNPJ' — vem de GET /orders/{id}/billing_info (o ML tirou o documento do /orders).
    # Migration 127. Escolhe cpfDestinatario x cnpjDestinatario pela FONTE, não pelo tamanho.
    buyer_document_type = Column(String(10))
    # Razão social do PJ (CNPJ) — vem de billing_info.name; usado no eShip
    # (razaoSocialDestinatario, obrigatório p/ CNPJ não cadastrado). Migration 133.
    buyer_business_name = Column(String(255))
    shipping_address = Column(String)  # JSON CLOB
    shipping_method = Column(String(100))
    shipping_mode = Column(String(20))  # full|flex|agencia|correios|coletado|combinado|desconhecido
    shipment_status = Column(String(50))
    tracking_code = Column(String(100))
    tracking_url = Column(String(500))
    shipment_id = Column(String(100))
    eship_order_id = Column(String(100))  # ID da ordem no WMS eShip (integração isolada)
    # Selos de anexo no eShip — guardas de idempotência do envio completo (Ordem+NF-e+Etiqueta)
    eship_nfe_attached = Column(Integer, default=0)     # 0|1 — XML da NF-e anexado à Ordem
    eship_label_attached = Column(Integer, default=0)   # 0|1 — etiqueta anexada à Ordem
    eship_dispatch_status = Column(String(20))          # None|sending|sent|partial|failed|cancelled
    eship_dispatch_error = Column(String(500))          # última pendência/erro do envio
    eship_dispatch_attempts = Column(Integer, default=0)  # nº de tentativas de envio
    # Migration 126:
    eship_last_response = Column(Text)                  # resposta CRUA do PostOrdem (conferência)
    eship_dispatch_at = Column(TIMESTAMP(timezone=True))  # instante do claim (TTL do lock 'sending')
    # Migration 134: selo de idempotência do TRANSPORTE (codigoTransporte gravado no eShip).
    # Evita reenviar o PutOrdem de transporte a cada ciclo de sync (scheduler 15min).
    eship_transporte_codigo = Column(String(10))
    label_url = Column(String(1000))
    label_cached_at = Column(TIMESTAMP(timezone=True))  # quando a etiqueta foi salva no disco
    nfe_url = Column(String(1000))
    nfe_key = Column(String(50))
    nfe_status = Column(String(30))
    nfe_invoices_json = Column(
        String
    )  # CLOB — cache da lista de NF-e do Faturador ML (venda + referências)
    # DC-e (Declaração de Conteúdo Eletrônica) — contas pessoa física (CPF) que não
    # emitem NF-e. dce_status: None | 'pending' | 'emitted'. pack_id: dedup por envio.
    dce_status = Column(String(30))
    pack_id = Column(String(50))
    # Shopee — estado do anexo da NF-e no pedido (Fase 3). None|pending|uploaded|validated|rejected.
    # Migration 135. `uploaded`=enviado à Shopee; `validated`=Shopee validou na SEFAZ (invoice_data
    # preenchido no get_order_detail); pré-requisito do ship_order no BR.
    shopee_invoice_status = Column(String(20))
    shopee_invoice_uploaded_at = Column(TIMESTAMP(timezone=True))
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
    return_status = Column(String(30), nullable=True)  # None | 'awaiting_return' | 'returned'
    is_hidden = Column(Boolean, default=False)
    notes = Column(String)
    paid_at = Column(TIMESTAMP(timezone=True))
    shipped_at = Column(TIMESTAMP(timezone=True))
    # Separação (módulo SEPARAÇÃO / Carrinho Gaiola)
    separated_at = Column(TIMESTAMP(timezone=True))
    separated_by = Column(Integer, ForeignKey("users.id"))
    dispatched_at = Column(TIMESTAMP(timezone=True))  # entregue à transportadora
    dispatched_by = Column(Integer, ForeignKey("users.id"))
    picking_cart_id = Column(Integer, ForeignKey("picking_carts.id"))
    # Fase 2 — Split Payment (retenção automática na origem — plataformas marketplace 2027+)
    split_payment_amount = Column(Numeric(15, 2))
    split_payment_ref = Column(String(100))
    split_payment_date = Column(TIMESTAMP(timezone=True))
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

-- ============================================================
-- MIG ECOMMERCE – Script 06: Pedidos
-- ============================================================

CREATE TABLE orders (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id      NUMBER          NOT NULL,
    integration_id      NUMBER,
    platform            VARCHAR2(20)
                            CONSTRAINT chk_ord_platform CHECK (platform IN ('mercadolivre','shopee','manual')),
    platform_order_id   VARCHAR2(200),       -- ID do pedido no marketplace
    platform_order_ref  VARCHAR2(200),       -- Ref visível ao comprador
    platform_status     VARCHAR2(50),        -- Status original do marketplace
    status              VARCHAR2(30)    DEFAULT 'downloaded' NOT NULL
                            CONSTRAINT chk_ord_status CHECK (status IN (
                                'downloaded','paid','label_generated',
                                'label_printed','separated','shipped',
                                'cancelled','returned'
                            )),
    payment_status      VARCHAR2(20)    DEFAULT 'pending' NOT NULL
                            CONSTRAINT chk_ord_payment CHECK (payment_status IN ('pending','paid','failed')),
    buyer_name          VARCHAR2(255),
    buyer_email         VARCHAR2(255),
    buyer_document      VARCHAR2(20),
    shipping_address    CLOB,               -- JSON com dados de entrega
    shipping_method     VARCHAR2(100),
    tracking_code       VARCHAR2(100),
    tracking_url        VARCHAR2(500),
    label_url           VARCHAR2(1000),
    sale_amount         NUMBER(15,2),        -- Valor da venda (marketplace)
    product_cost        NUMBER(15,2),        -- Custo produto(s) ao fornecedor
    platform_fee        NUMBER(15,2),        -- Taxa da plataforma MIG
    shipping_cost       NUMBER(15,2),        -- Frete cobrado
    total_debit         NUMBER(15,2),        -- = product_cost + platform_fee + shipping_cost
    is_hidden           NUMBER(1)       DEFAULT 0,
    notes               CLOB,
    paid_at             TIMESTAMP WITH TIME ZONE,
    shipped_at          TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_ord_dropshipper   FOREIGN KEY (dropshipper_id) REFERENCES users(id)
    -- fk_ord_integration added in 07_integrations.sql (table created there)
);

CREATE TABLE order_items (
    id                      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id                NUMBER          NOT NULL,
    dropshipper_product_id  NUMBER,
    catalog_product_id      NUMBER,
    catalog_variant_id      NUMBER,
    sku                     VARCHAR2(100),
    title                   VARCHAR2(500),
    quantity                NUMBER          DEFAULT 1 NOT NULL,
    unit_price              NUMBER(15,2),   -- Preço de venda unitário
    unit_cost               NUMBER(15,2),   -- Custo unitário ao fornecedor
    CONSTRAINT fk_oi_order      FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_oi_dp         FOREIGN KEY (dropshipper_product_id) REFERENCES dropshipper_products(id),
    CONSTRAINT fk_oi_catalog    FOREIGN KEY (catalog_product_id) REFERENCES catalog_products(id)
);

CREATE OR REPLACE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Critical indexes
CREATE INDEX idx_orders_dropshipper     ON orders(dropshipper_id);
CREATE INDEX idx_orders_status          ON orders(dropshipper_id, status);
CREATE INDEX idx_orders_payment         ON orders(dropshipper_id, payment_status);
CREATE INDEX idx_orders_platform_id     ON orders(platform, platform_order_id);
CREATE INDEX idx_orders_created         ON orders(dropshipper_id, created_at DESC);
CREATE INDEX idx_oi_order               ON order_items(order_id);

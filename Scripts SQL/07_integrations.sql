-- ============================================================
-- MIG ECOMMERCE – Script 07: Integrações com Marketplaces
-- ============================================================

CREATE TABLE marketplace_integrations (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id      NUMBER          NOT NULL,
    platform            VARCHAR2(20)    NOT NULL
                            CONSTRAINT chk_mi_platform CHECK (platform IN ('mercadolivre','shopee','bling')),
    description         VARCHAR2(200),      -- Nome interno (ex: "Loja ML Principal")
    access_token        VARCHAR2(2000),
    refresh_token       VARCHAR2(2000),
    token_expires_at    TIMESTAMP WITH TIME ZONE,
    platform_user_id    VARCHAR2(200),
    platform_username   VARCHAR2(200),
    shop_id             NUMBER,             -- Shopee shop ID
    api_key             VARCHAR2(500),      -- Para Bling
    is_active           NUMBER(1)       DEFAULT 1 NOT NULL
                            CONSTRAINT chk_mi_active CHECK (is_active IN (0,1)),
    last_sync_at        TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_mi_dropshipper FOREIGN KEY (dropshipper_id) REFERENCES users(id)
);

CREATE INDEX idx_mi_dropshipper ON marketplace_integrations(dropshipper_id);
CREATE INDEX idx_mi_platform    ON marketplace_integrations(dropshipper_id, platform);

-- FK from orders.integration_id (orders table created in 06_orders.sql)
ALTER TABLE orders ADD CONSTRAINT fk_ord_integration
    FOREIGN KEY (integration_id) REFERENCES marketplace_integrations(id);

-- Tabela de anúncios por marketplace por conta
-- Vincula DropshipperProduct ↔ MarketplaceAccount (N:N)
-- Um produto pode ter anúncios em múltiplas contas do mesmo marketplace
CREATE TABLE product_listings (
    id                NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id        NUMBER NOT NULL,
    account_id        NUMBER NOT NULL,
    platform_item_id  VARCHAR2(200),
    sale_price        NUMBER(15,2) NOT NULL,
    title_override    VARCHAR2(500),
    category_id       VARCHAR2(100),
    listing_type      VARCHAR2(20),
    status            VARCHAR2(20) DEFAULT 'draft'
                          CONSTRAINT chk_pl_status CHECK (status IN ('draft','published','paused','error')),
    error_message     VARCHAR2(2000),
    published_at      TIMESTAMP WITH TIME ZONE,
    last_sync_at      TIMESTAMP WITH TIME ZONE,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pl_product FOREIGN KEY (product_id) REFERENCES dropshipper_products(id) ON DELETE CASCADE,
    CONSTRAINT fk_pl_account FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_product_account UNIQUE (product_id, account_id)
);

CREATE INDEX idx_pl_product ON product_listings(product_id);
CREATE INDEX idx_pl_account  ON product_listings(account_id);
CREATE INDEX idx_pl_status   ON product_listings(status);

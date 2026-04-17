-- ============================================================
-- MIG ECOMMERCE – Script 05: Anúncios do Dropshipper
-- ============================================================

CREATE TABLE dropshipper_products (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id      NUMBER          NOT NULL,
    catalog_product_id  NUMBER,
    kit_id              NUMBER,
    title               VARCHAR2(500)   NOT NULL,
    title_ml            VARCHAR2(60),
    title_shopee        VARCHAR2(100),
    sale_price_ml       NUMBER(15,2),
    sale_price_shopee   NUMBER(15,2),
    -- Mercado Livre
    ml_item_id          VARCHAR2(100),
    ml_category_id      VARCHAR2(50),
    ml_listing_type     VARCHAR2(20),
    -- Shopee
    shopee_item_id      NUMBER,
    shopee_category_id  NUMBER,
    -- Bling
    bling_product_id    NUMBER,
    -- General
    status              VARCHAR2(20)    NOT NULL DEFAULT 'draft'
                            CONSTRAINT chk_dp_status CHECK (status IN ('draft','active','paused','closed')),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_dp_dropshipper    FOREIGN KEY (dropshipper_id) REFERENCES users(id),
    CONSTRAINT fk_dp_catalog        FOREIGN KEY (catalog_product_id) REFERENCES catalog_products(id),
    CONSTRAINT fk_dp_kit            FOREIGN KEY (kit_id) REFERENCES kits(id)
);

CREATE TABLE dropshipper_product_images (
    id                      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_product_id  NUMBER          NOT NULL,
    url                     VARCHAR2(1000)  NOT NULL,
    sort_order              NUMBER          DEFAULT 0,
    is_primary              NUMBER(1)       DEFAULT 0,
    CONSTRAINT fk_dpi_product FOREIGN KEY (dropshipper_product_id)
        REFERENCES dropshipper_products(id) ON DELETE CASCADE
);

CREATE OR REPLACE TRIGGER trg_dp_updated_at
    BEFORE UPDATE ON dropshipper_products
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE INDEX idx_dp_dropshipper ON dropshipper_products(dropshipper_id);
CREATE INDEX idx_dp_catalog     ON dropshipper_products(catalog_product_id);
CREATE INDEX idx_dp_ml_item     ON dropshipper_products(ml_item_id);
CREATE INDEX idx_dp_shopee_item ON dropshipper_products(shopee_item_id);

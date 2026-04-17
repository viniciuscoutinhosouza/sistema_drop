-- ============================================================
-- MIG ECOMMERCE – Script 03: Catálogo de Produtos do Fornecedor
-- ============================================================

CREATE TABLE categories (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                VARCHAR2(200)   NOT NULL,
    parent_id           NUMBER,
    ml_category_id      VARCHAR2(50),
    shopee_category_id  NUMBER,
    CONSTRAINT fk_cat_parent FOREIGN KEY (parent_id) REFERENCES categories(id)
);

CREATE TABLE catalog_products (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku             VARCHAR2(100)   NOT NULL,
    title           VARCHAR2(500)   NOT NULL,
    description     CLOB,
    cost_price      NUMBER(15,2)    NOT NULL,
    suggested_price NUMBER(15,2),
    weight_kg       NUMBER(8,3),
    height_cm       NUMBER(8,2),
    width_cm        NUMBER(8,2),
    length_cm       NUMBER(8,2),
    ncm             VARCHAR2(10),
    cest            VARCHAR2(7),
    brand           VARCHAR2(100),
    origin          NUMBER(1)       DEFAULT 0,
    category_id     NUMBER,
    stock_quantity  NUMBER          DEFAULT 0 NOT NULL,
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_cp_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_cp_sku        UNIQUE (sku),
    CONSTRAINT fk_cp_category   FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE catalog_product_images (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id  NUMBER          NOT NULL,
    url         VARCHAR2(1000)  NOT NULL,
    sort_order  NUMBER          DEFAULT 0,
    is_primary  NUMBER(1)       DEFAULT 0
                    CONSTRAINT chk_cpi_primary CHECK (is_primary IN (0,1)),
    CONSTRAINT fk_cpi_product FOREIGN KEY (product_id) REFERENCES catalog_products(id) ON DELETE CASCADE
);

CREATE TABLE catalog_product_variants (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      NUMBER          NOT NULL,
    sku             VARCHAR2(100)   NOT NULL,
    variant_name    VARCHAR2(255),
    color           VARCHAR2(100),
    size_label      VARCHAR2(100),
    stock_quantity  NUMBER          DEFAULT 0 NOT NULL,
    price_modifier  NUMBER(15,2)    DEFAULT 0,
    CONSTRAINT uq_cpv_sku       UNIQUE (sku),
    CONSTRAINT fk_cpv_product   FOREIGN KEY (product_id) REFERENCES catalog_products(id) ON DELETE CASCADE
);

-- Trigger updated_at
CREATE OR REPLACE TRIGGER trg_catalog_products_upd
    BEFORE UPDATE ON catalog_products
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE INDEX idx_cp_category    ON catalog_products(category_id);
CREATE INDEX idx_cp_active      ON catalog_products(is_active, created_at DESC);
CREATE INDEX idx_cp_sku         ON catalog_products(sku);
CREATE INDEX idx_cpi_product    ON catalog_product_images(product_id, sort_order);
CREATE INDEX idx_cpv_product    ON catalog_product_variants(product_id);

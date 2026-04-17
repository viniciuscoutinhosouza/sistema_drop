-- ============================================================
-- MIG ECOMMERCE – Script 04: Kits
-- ============================================================

CREATE TABLE kits (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id  NUMBER          NOT NULL,
    sku             VARCHAR2(100)   NOT NULL,  -- Enforced prefix KITB2- at app level
    title           VARCHAR2(500)   NOT NULL,
    description     CLOB,
    color           VARCHAR2(100),
    size_label      VARCHAR2(100),
    width_cm        NUMBER(8,2),
    height_cm       NUMBER(8,2),
    length_cm       NUMBER(8,2),
    weight_kg       NUMBER(8,3),
    ncm             VARCHAR2(10),
    cest            VARCHAR2(7),
    origin          NUMBER(1)       DEFAULT 0,
    category_id     NUMBER,
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_kit_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_kit_sku   UNIQUE (dropshipper_id, sku),
    CONSTRAINT fk_kit_ds    FOREIGN KEY (dropshipper_id) REFERENCES users(id),
    CONSTRAINT fk_kit_cat   FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE kit_components (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kit_id      NUMBER  NOT NULL,
    product_id  NUMBER,
    variant_id  NUMBER,
    quantity    NUMBER  DEFAULT 1 NOT NULL,
    CONSTRAINT fk_kc_kit        FOREIGN KEY (kit_id) REFERENCES kits(id) ON DELETE CASCADE,
    CONSTRAINT fk_kc_product    FOREIGN KEY (product_id) REFERENCES catalog_products(id),
    CONSTRAINT fk_kc_variant    FOREIGN KEY (variant_id) REFERENCES catalog_product_variants(id)
);

CREATE INDEX idx_kit_ds         ON kits(dropshipper_id);
CREATE INDEX idx_kc_kit         ON kit_components(kit_id);

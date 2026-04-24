-- Script 22: Enriquecimento de campos de produto (Gerais e CMIG) + variantes CMIG

-- Campos faltantes em catalog_products
ALTER TABLE catalog_products ADD model VARCHAR2(200);
ALTER TABLE catalog_products ADD ean   VARCHAR2(14);

-- Campos faltantes em cmig_products
ALTER TABLE cmig_products ADD model    VARCHAR2(200);
ALTER TABLE cmig_products ADD ean      VARCHAR2(14);

-- Voltagem e atributos extras em catalog_product_variants (tabela ja existe)
ALTER TABLE catalog_product_variants ADD voltage         VARCHAR2(50);
ALTER TABLE catalog_product_variants ADD attributes_json VARCHAR2(2000);

-- Nova tabela: variantes de produtos CMIG (espelha catalog_product_variants)
CREATE TABLE cmig_product_variants (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cmig_product_id NUMBER        NOT NULL REFERENCES cmig_products(id) ON DELETE CASCADE,
    sku             VARCHAR2(100) NOT NULL,
    variant_name    VARCHAR2(255),
    color           VARCHAR2(100),
    size_label      VARCHAR2(100),
    voltage         VARCHAR2(50),
    stock_quantity  NUMBER(6)     DEFAULT 0 NOT NULL,
    price_modifier  NUMBER(15,2)  DEFAULT 0,
    attributes_json VARCHAR2(2000),
    CONSTRAINT uq_cmig_variant_sku UNIQUE (sku)
);

COMMIT;

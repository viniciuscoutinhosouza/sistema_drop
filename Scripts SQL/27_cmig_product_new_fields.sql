-- Migration 27: Novos campos em cmig_products e cmig_product_variants
-- para suportar criacao automatica de produto CMIG a partir de anuncio

-- Campos novos em cmig_products
ALTER TABLE cmig_products ADD category_name   VARCHAR2(200);
ALTER TABLE cmig_products ADD sale_price      NUMBER(15,2);
ALTER TABLE cmig_products ADD video_id        VARCHAR2(100);
ALTER TABLE cmig_products ADD attributes_json CLOB;
ALTER TABLE cmig_products ADD pictures_json   CLOB;
ALTER TABLE cmig_products ADD fiscal_json     VARCHAR2(2000);

-- Campo novo em cmig_product_variants
ALTER TABLE cmig_product_variants ADD sale_price NUMBER(15,2);

COMMIT;

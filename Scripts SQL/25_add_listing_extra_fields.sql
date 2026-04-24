-- Script 25: Campos extras em product_listings — categoria nome, FULL, catálogo ML
ALTER TABLE product_listings ADD category_name  VARCHAR2(200);
ALTER TABLE product_listings ADD is_full        NUMBER(1)     DEFAULT 0;
ALTER TABLE product_listings ADD ml_catalog_id  VARCHAR2(200);
COMMIT;

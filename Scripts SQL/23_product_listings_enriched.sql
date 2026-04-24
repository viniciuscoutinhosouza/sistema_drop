-- Script 23: Enriquecimento de product_listings
-- Adiciona SKU, dimensões, peso, fotos completas, dados fiscais e variações
ALTER TABLE product_listings ADD sku             VARCHAR2(100);
ALTER TABLE product_listings ADD weight_kg       NUMBER(8,3);
ALTER TABLE product_listings ADD height_cm       NUMBER(8,2);
ALTER TABLE product_listings ADD width_cm        NUMBER(8,2);
ALTER TABLE product_listings ADD length_cm       NUMBER(8,2);
ALTER TABLE product_listings ADD pictures_json   CLOB;
ALTER TABLE product_listings ADD fiscal_json     VARCHAR2(2000);
ALTER TABLE product_listings ADD variations_json CLOB;
COMMIT;

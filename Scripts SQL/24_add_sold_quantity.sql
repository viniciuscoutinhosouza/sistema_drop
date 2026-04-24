-- Script 24: Adiciona quantidade vendida em product_listings
ALTER TABLE product_listings ADD sold_quantity NUMBER(10) DEFAULT 0;
COMMIT;

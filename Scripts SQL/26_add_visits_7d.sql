-- Script 26: Adiciona visitas 7 dias em product_listings
ALTER TABLE product_listings ADD visits_7d NUMBER(10) DEFAULT 0;
COMMIT;

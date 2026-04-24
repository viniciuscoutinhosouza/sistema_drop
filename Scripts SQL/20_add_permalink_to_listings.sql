-- Script 20: adiciona permalink à product_listings para link direto ao ML
ALTER TABLE product_listings ADD permalink VARCHAR2(1000);
COMMIT;

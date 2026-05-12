-- Migration 56: adiciona has_auto_price_adj em product_listings
-- Indica que o ML está aplicando ajuste automático de preço (PRICE_DISCOUNT / PRICE_MATCHING)
-- em vez de uma promoção de campanha normal.
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD has_auto_price_adj NUMBER(1) DEFAULT 0';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/


COMMIT;

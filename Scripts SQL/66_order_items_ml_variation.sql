-- Migration 66: Adiciona ml_variation_id em order_items
-- Armazena o variation_id do ML ao processar pedidos de produtos variantes,
-- permitindo rastrear qual SKU físico foi vendido.
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_items ADD ml_variation_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

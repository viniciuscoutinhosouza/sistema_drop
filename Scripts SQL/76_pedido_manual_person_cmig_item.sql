-- Migration 76: suporte a "Pedido Manual" enriquecido
--   1. orders.buyer_person_id  -> FK opcional para people (cliente cadastrado)
--   2. order_items.cmig_product_id -> FK opcional para cmig_products (item CMIG no carrinho)
-- Ambos sao opcionais para nao quebrar pedidos historicos (marketplace).

-- 1) orders.buyer_person_id
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD buyer_person_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_fk_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_fk_exists, -2275);
  e_dup_name EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_dup_name, -2264);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE orders ADD CONSTRAINT fk_orders_buyer_person '
    || 'FOREIGN KEY (buyer_person_id) REFERENCES people(id)';
EXCEPTION
  WHEN e_fk_exists THEN NULL;
  WHEN e_dup_name THEN NULL;
END;
/

-- 2) order_items.cmig_product_id
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_items ADD cmig_product_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_fk_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_fk_exists, -2275);
  e_dup_name EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_dup_name, -2264);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE order_items ADD CONSTRAINT fk_order_items_cmig_product '
    || 'FOREIGN KEY (cmig_product_id) REFERENCES cmig_products(id)';
EXCEPTION
  WHEN e_fk_exists THEN NULL;
  WHEN e_dup_name THEN NULL;
END;
/

COMMIT;

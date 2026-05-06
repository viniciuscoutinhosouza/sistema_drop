-- Migration 46: controle de modo de estoque por anúncio
-- stock_mode: 'product' = usa estoque do produto PG/CMIG | 'fixed' = valor definido pelo usuário
-- fixed_quantity: quantidade fixa quando stock_mode = 'fixed'
-- keep_stock_fixed: 1 = job de sync restaura fixed_quantity após vendas

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD stock_mode VARCHAR2(10) DEFAULT ''product''';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD fixed_quantity NUMBER(10) DEFAULT 1';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD keep_stock_fixed NUMBER(1) DEFAULT 0';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Atualiza registros existentes para o padrão
UPDATE product_listings SET stock_mode = 'product' WHERE stock_mode IS NULL;
UPDATE product_listings SET fixed_quantity = 1 WHERE fixed_quantity IS NULL;
UPDATE product_listings SET keep_stock_fixed = 0 WHERE keep_stock_fixed IS NULL;

COMMIT;

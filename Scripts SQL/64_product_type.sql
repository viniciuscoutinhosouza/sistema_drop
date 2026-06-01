-- Migration 64: Adiciona product_type em catalog_products
-- Discrimina entre 'simple', 'kit' e 'variant'
-- Idempotente: ignora se coluna já existe
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD product_type VARCHAR2(10) DEFAULT ''simple'' NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/
UPDATE catalog_products SET product_type = 'kit' WHERE is_composite = 1;
COMMIT;

-- Migration 28: garantir que catalog_products tem as colunas model e ean
-- Seguro de re-executar caso a migration 22 já tenha sido aplicada (ORA-01430 ignorado)

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD model VARCHAR2(200)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD ean VARCHAR2(14)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

-- 68_invoice_items_catalog_product_id.sql
-- Adiciona catalog_product_id em invoice_items para match direto com CatalogProduct (PG),
-- eliminando a dependência de match por string de SKU/EAN.
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE invoice_items ADD catalog_product_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/
COMMIT;

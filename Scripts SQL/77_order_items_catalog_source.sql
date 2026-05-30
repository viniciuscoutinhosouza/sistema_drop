-- Migration 77: rastreabilidade de catalogo de origem em pedidos manuais
-- order_items.catalog_source identifica de qual catalogo o produto foi escolhido
-- ('pg' = Catalogo Geral / 'cmig' = Catalogo CMIG / NULL = pedidos historicos de marketplace).
-- Resolve ambiguidade quando um item CMIG espelha catalog_product_id do PG vinculado.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_items ADD catalog_source VARCHAR2(10)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

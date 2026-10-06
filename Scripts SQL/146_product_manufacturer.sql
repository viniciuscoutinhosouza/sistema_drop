-- Migration 146: campo "Fabricante" (manufacturer) no cadastro de produto.
--
-- Novo campo EM PARALELO ao `brand` (Marca) já existente, para os DOIS tipos de produto do cadastro:
--   cmig_products.manufacturer     → Fabricante do Produto CMIG
--   catalog_products.manufacturer  → Fabricante do Produto PG (Produto Geral)
--
-- VARCHAR2(100), igual a `brand` (não 200, que é do `model`). NÃO toca `brand` de anúncios/ML/listings
-- (lá marca é atributo de marketplace, não o cadastro).
--
-- Idempotente: cada ADD é isolado e ORA-01430 (coluna já existe) é ignorado.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_ddl VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_ddl;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE cmig_products ADD (manufacturer VARCHAR2(100))');
  add_col('ALTER TABLE catalog_products ADD (manufacturer VARCHAR2(100))');
END;
/

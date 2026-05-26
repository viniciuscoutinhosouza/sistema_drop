-- ============================================================
-- MIG ECOMMERCE – Script 70: Fix dos índices únicos de product_marketplace_categories
-- ============================================================
-- Problema: os índices únicos compostos criados na migration 69
--   uq_pmc_catalog ON (catalog_product_id, marketplace, category_id)
--   uq_pmc_cmig    ON (cmig_product_id,    marketplace, category_id)
-- tratavam linhas com a coluna-owner NULL como duplicáveis entre si.
-- No Oracle, um índice composto INDEXA a linha desde que pelo menos UMA
-- coluna do índice seja NOT NULL. Como (marketplace, category_id) são
-- NOT NULL, todas as linhas eram indexadas — e duas linhas com
-- cmig_product_id=NULL, mesmo marketplace e mesmo category_id colidiam.
--
-- Sintoma: ao adicionar a mesma categoria ML (ex: Bolas / MLB123037) em
-- dois produtos PG diferentes, a segunda inserção falhava com
-- ORA-00001: unique constraint (UQ_PMC_CMIG) violated.
--
-- Fix: recriar os índices usando CASE WHEN para que linhas onde o owner
-- correspondente é NULL fiquem com TODAS as colunas indexadas NULL —
-- nesse caso, o Oracle NÃO indexa a linha ("Oracle does not index keys
-- composed entirely of nulls in B-tree indexes"), eliminando a colisão.
--
-- Idempotente: sobrevive a re-runs (DROP IF EXISTS + CREATE IF NOT EXISTS
-- via PRAGMA EXCEPTION_INIT).

-- Drop dos índices defeituosos (ORA-01418 = índice não existe → ignora)
DECLARE
  e_idx_missing EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_missing, -01418);
BEGIN
  EXECUTE IMMEDIATE 'DROP INDEX uq_pmc_catalog';
EXCEPTION WHEN e_idx_missing THEN NULL;
END;
/

DECLARE
  e_idx_missing EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_missing, -01418);
BEGIN
  EXECUTE IMMEDIATE 'DROP INDEX uq_pmc_cmig';
EXCEPTION WHEN e_idx_missing THEN NULL;
END;
/

-- Recria com CASE WHEN: linhas com owner NULL ficam all-NULL na chave
-- do índice e não são indexadas — duas dessas linhas não colidem.
DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE UNIQUE INDEX uq_pmc_catalog ON product_marketplace_categories(
      CASE WHEN catalog_product_id IS NULL THEN NULL ELSE catalog_product_id END,
      CASE WHEN catalog_product_id IS NULL THEN NULL ELSE marketplace END,
      CASE WHEN catalog_product_id IS NULL THEN NULL ELSE category_id END
    )
  ]';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE UNIQUE INDEX uq_pmc_cmig ON product_marketplace_categories(
      CASE WHEN cmig_product_id IS NULL THEN NULL ELSE cmig_product_id END,
      CASE WHEN cmig_product_id IS NULL THEN NULL ELSE marketplace END,
      CASE WHEN cmig_product_id IS NULL THEN NULL ELSE category_id END
    )
  ]';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

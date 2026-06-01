-- 70_stock_reservation_columns.sql
-- Adiciona colunas de controle de estoque transacional:
--   reserved_quantity        : reservado por pedidos ativos
--   awaiting_return_quantity : pedido cancelado após despacho, aguardando retorno físico
--   pending_validation_quantity : devolução recebida aguardando inspeção do operador
--   unfit_quantity           : produto reprovado na inspeção
--
-- As colunas são adicionadas em catalog_products, cmig_products e suas tabelas de variantes.
-- Também adiciona return_status em orders para marcar pedidos com retorno pendente.
-- Idempotente via EXCEPTION WHEN e_col_exists.

-- ─── catalog_products ────────────────────────────────────────────────────────
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD reserved_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD awaiting_return_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD pending_validation_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD unfit_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- ─── catalog_product_variants ────────────────────────────────────────────────
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_product_variants ADD reserved_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_product_variants ADD awaiting_return_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_product_variants ADD pending_validation_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_product_variants ADD unfit_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- ─── cmig_products ───────────────────────────────────────────────────────────
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD reserved_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD awaiting_return_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD pending_validation_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD unfit_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- ─── cmig_product_variants ───────────────────────────────────────────────────
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_product_variants ADD reserved_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_product_variants ADD awaiting_return_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_product_variants ADD pending_validation_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_product_variants ADD unfit_quantity NUMBER DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- ─── orders: return_status ───────────────────────────────────────────────────
-- Marca pedidos cujo produto retornou ao fluxo de estoque após cancelamento pós-despacho.
-- Valores: NULL (normal) | 'awaiting_return' | 'returned'
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD return_status VARCHAR2(30)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

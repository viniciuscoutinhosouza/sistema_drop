-- Migration 50: Produto Composto (CMIG Composto + PG Composto)
-- Idempotente — usa blocos DECLARE/EXCEPTION para re-execução segura

-- 1. Coluna is_composite em cmig_products
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD is_composite NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- 2. Tabela de componentes do Produto CMIG Composto
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE cmig_product_components (
      id                 NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      composite_id       NUMBER        NOT NULL REFERENCES cmig_products(id) ON DELETE CASCADE,
      cmig_product_id    NUMBER        REFERENCES cmig_products(id) ON DELETE SET NULL,
      catalog_product_id NUMBER        REFERENCES catalog_products(id) ON DELETE SET NULL,
      quantity           NUMBER        DEFAULT 1 NOT NULL
    )
  ]';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE = -955 THEN NULL; ELSE RAISE; END IF;
END;
/

-- 3. Coluna is_composite em catalog_products
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD is_composite NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- 4. Tabela de componentes do Produto PG Composto
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE catalog_product_components (
      id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      composite_id NUMBER NOT NULL REFERENCES catalog_products(id) ON DELETE CASCADE,
      component_id NUMBER NOT NULL REFERENCES catalog_products(id) ON DELETE CASCADE,
      quantity     NUMBER DEFAULT 1 NOT NULL
    )
  ]';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE = -955 THEN NULL; ELSE RAISE; END IF;
END;
/

COMMIT;


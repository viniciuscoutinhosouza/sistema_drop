-- Migration 145: categorias de produto isoladas por GALPÃO (warehouse).
-- Pedido do dono: categoria criada num galpão não aparece em outro. As categorias atuais são do MIG.
--
--   - Adiciona categories.warehouse_id (FK warehouses, nullable — coerente com catalog_products.warehouse_id).
--   - Backfill: categorias existentes (warehouse_id NULL) → galpão MIG (resolvido por NOME, não hardcode).
--   - FK + índice.
--
-- Idempotente: ORA-01430 (coluna existe), ORA-00955 (objeto/índice existe), ORA-02264/-02275 (constraint existe).

-- 1. Coluna
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE categories ADD (warehouse_id NUMBER)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

-- 2. Backfill → MIG (por nome; re-executável — só toca NULLs)
UPDATE categories
   SET warehouse_id = (SELECT MIN(id) FROM warehouses WHERE name = 'MIG')
 WHERE warehouse_id IS NULL
   AND EXISTS (SELECT 1 FROM warehouses WHERE name = 'MIG')
/

-- 3. FK
DECLARE
  e_cons_exists EXCEPTION;
  e_cons_exists2 EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_cons_exists, -2264);   -- nome já usado por constraint
  PRAGMA EXCEPTION_INIT(e_cons_exists2, -2275);  -- FK equivalente já existe
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE categories ADD CONSTRAINT fk_categories_wh
       FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)';
EXCEPTION
  WHEN e_cons_exists THEN NULL;
  WHEN e_cons_exists2 THEN NULL;
END;
/

-- 4. Índice
DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_categories_wh ON categories (warehouse_id)';
EXCEPTION
  WHEN e_exists THEN NULL;
END;
/

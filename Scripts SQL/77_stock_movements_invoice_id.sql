-- 77_stock_movements_invoice_id.sql
-- Adiciona invoice_id (nullable) em stock_movements para rastrear movimentos
-- originados de NF-e (em especial os movimentos FULL) e garantir idempotência.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE stock_movements ADD invoice_id NUMBER REFERENCES invoices(id)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_stock_mov_invoice ON stock_movements(invoice_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

-- Verificação
SELECT column_name, data_type, nullable
  FROM user_tab_columns
 WHERE table_name = 'STOCK_MOVEMENTS'
   AND column_name = 'INVOICE_ID';

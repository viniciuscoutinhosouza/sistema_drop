-- Migration 44: Adiciona orders.invoice_id (FK para invoices) — vínculo formal
-- entre pedido e a NFe que o sistema emitiu para ele.
-- Idempotente.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD invoice_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_constraint_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_constraint_exists, -02275);
  e_dup_key EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_dup_key, -02264);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD CONSTRAINT fk_orders_invoice
                       FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL';
EXCEPTION
  WHEN e_constraint_exists THEN NULL;
  WHEN e_dup_key THEN NULL;
  WHEN OTHERS THEN
    IF SQLCODE = -02275 OR SQLCODE = -02264 THEN NULL;
    ELSE RAISE;
    END IF;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_orders_invoice ON orders(invoice_id)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

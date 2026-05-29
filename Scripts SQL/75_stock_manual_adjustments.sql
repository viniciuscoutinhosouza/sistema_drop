-- Migration 75: trilha de auditoria de alterações no cache stock_quantity.
-- Registra cada vez que stock_quantity foi alterado por:
--   - manual_override: POST /pg/{id}/stock (endpoint deprecated de override direto)
--   - recompute: POST /pg/{id}/recalculate-stock ou /cmigs/.../recalculate-stock
--   - batch_recompute: POST /pg/recalculate-all-stock (job admin)
-- A tabela é APENAS para auditoria — não afeta o cálculo de saldo.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE stock_manual_adjustments (
      id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      product_type    VARCHAR2(10) NOT NULL,
      product_id      NUMBER NOT NULL,
      old_value       NUMBER NOT NULL,
      new_value       NUMBER NOT NULL,
      delta           NUMBER NOT NULL,
      reason          VARCHAR2(500),
      user_id         NUMBER,
      adjustment_kind VARCHAR2(30) NOT NULL,
      created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT ck_sma_type CHECK (product_type IN ('pg','cmig')),
      CONSTRAINT ck_sma_kind CHECK (adjustment_kind IN ('manual_override','recompute','batch_recompute')),
      CONSTRAINT fk_sma_user FOREIGN KEY (user_id) REFERENCES users(id)
    )
  ]';
EXCEPTION
  WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_sma_product ON stock_manual_adjustments(product_type, product_id, created_at DESC)';
EXCEPTION
  WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_sma_created ON stock_manual_adjustments(created_at DESC)';
EXCEPTION
  WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

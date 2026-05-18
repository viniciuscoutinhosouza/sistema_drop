-- Migration 63: adiciona 'stock_reapplied' à constraint chk_invevt_type
-- Necessário pra registrar eventos do endpoint POST /invoices/{id}/reapply-stock
-- que reaplica movimentação de estoque pra notas finalizadas (corrige NFes
-- antigas que ignoraram itens PG).
-- Idempotente.

DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'CHK_INVEVT_TYPE'
     AND table_name = 'INVOICE_EVENTS';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE invoice_events DROP CONSTRAINT chk_invevt_type';
  END IF;
END;
/

ALTER TABLE invoice_events ADD CONSTRAINT chk_invevt_type CHECK (
    event_type IN ('cancellation','correction_letter','manifestation',
                   'inutilization','finalize_no_sefaz','transmission',
                   'status_update','stock_reapplied')
);

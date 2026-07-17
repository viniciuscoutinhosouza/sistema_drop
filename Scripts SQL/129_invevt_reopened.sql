-- Migration 129: adiciona 'reopened' à constraint CHK_INVEVT_TYPE.
--
-- Necessário para o endpoint POST /invoices/{id}/reopen, que registra um InvoiceEvent
-- 'reopened' ao reabrir uma nota finalizada/rejeitada para edição. Sem este valor na
-- whitelist, o reopen falha com ORA-02290 (check constraint violated) e devolve 500.
--
-- Mantém todos os tipos já existentes (migration 60/63) e acrescenta 'reopened'.
-- Idempotente: dropa a constraint se existir antes de recriar.

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
                   'status_update','stock_reapplied','reopened')
);

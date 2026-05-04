-- Migration 43: Tabela `invoice_events` — auditoria de eventos NFe
-- (cancelamento, CCe, manifestação, inutilização)
-- Idempotente.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE invoice_events (
      id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      invoice_id          NUMBER NOT NULL,
      event_type          VARCHAR2(30) NOT NULL
                              CONSTRAINT chk_invevt_type CHECK (
                                  event_type IN ('cancellation','correction_letter',
                                                  'manifestation','inutilization')),
      sequence_number     NUMBER,
      reason              VARCHAR2(2000),
      focus_ref           VARCHAR2(100),
      sefaz_protocol      VARCHAR2(50),
      sefaz_status_code   VARCHAR2(10),
      sefaz_message       VARCHAR2(2000),
      xml_url             VARCHAR2(1000),
      created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      created_by_user_id  NUMBER,
      CONSTRAINT fk_invevt_inv FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
      CONSTRAINT fk_invevt_user FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_invevt_invoice_type ON invoice_events(invoice_id, event_type)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

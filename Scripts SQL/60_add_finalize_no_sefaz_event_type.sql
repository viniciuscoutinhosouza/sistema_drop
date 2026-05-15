-- Migration 60: Adiciona 'finalize_no_sefaz' e outros tipos ao CHK_INVEVT_TYPE
-- O constraint original so permitia: cancellation, correction_letter, manifestation, inutilization
-- O endpoint finalize-no-sefaz usa 'finalize_no_sefaz' que nao estava na lista.

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
                   'status_update')
);

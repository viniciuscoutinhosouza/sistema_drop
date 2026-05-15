-- Migration 59: Adiciona status 'finalized' ao CHK_INV_STATUS
-- O endpoint finalize-no-sefaz seta status='finalized' mas o constraint original
-- so permitia: draft, queued, processing, authorized, rejected, cancelled, denied

DECLARE
  v_count NUMBER;
BEGIN
  -- Remove o constraint antigo (se existir)
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'CHK_INV_STATUS'
     AND table_name = 'INVOICES';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE invoices DROP CONSTRAINT chk_inv_status';
  END IF;
END;
/

ALTER TABLE invoices ADD CONSTRAINT chk_inv_status CHECK (
    status IN ('draft','queued','processing','authorized',
               'rejected','cancelled','denied','finalized')
);

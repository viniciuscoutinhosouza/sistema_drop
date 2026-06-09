-- Migration 91: % de imposto estimado para a DRE, na config fiscal da CMIG.
-- Usado para estimar a linha "Imposto ML" = faturamento * (tax_estimate_pct/100).
-- Idempotente.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_fiscal_config ADD tax_estimate_pct NUMBER(8,4) DEFAULT 0';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

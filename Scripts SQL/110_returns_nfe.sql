-- Fase B: Devoluções NF-e-driven. Vincula o Return à NF-e de devolução (entrada),
-- à nota de descarte (não-apto) e à chave da NF-e de venda referenciada (refNFe).
-- Idempotente (ORA-1430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE returns ADD devolution_invoice_id NUMBER]';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE returns ADD discard_invoice_id NUMBER]';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE returns ADD referenced_access_key VARCHAR2(50)]';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

-- Reclamações: foto de capa do anúncio na lista. Idempotente (ORA-1430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE claims ADD thumbnail VARCHAR2(1000)]';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

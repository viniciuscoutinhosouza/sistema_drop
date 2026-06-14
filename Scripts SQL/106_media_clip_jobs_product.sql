-- Associa o clip gerado ao produto (PG/CMIG) para listar por produto e deixá-lo
-- "pronto"/persistido para a publicação. Idempotente (ORA-1430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE media_clip_jobs ADD product_type VARCHAR2(10)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE media_clip_jobs ADD product_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

-- Atendimento/Mensagens: foto de capa e link do anúncio no item da conversa.
-- Idempotente (ORA-1430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE conversation_threads ADD item_thumbnail VARCHAR2(1000)]';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE conversation_threads ADD item_permalink VARCHAR2(1000)]';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

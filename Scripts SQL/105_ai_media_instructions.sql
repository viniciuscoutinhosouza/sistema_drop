-- Instruções/perfil de mídia: texto base aplicado a TODOS os prompts de geração
-- de foto e clip por IA (análogo a global_instructions do chat). Idempotente (ORA-1430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE ai_configs ADD media_instructions CLOB';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

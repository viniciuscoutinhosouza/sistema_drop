-- Fase B.1: provider de IA de MÍDIA (imagens) na config de IA (singleton ai_configs).
-- Separado do provider de chat (atendimento): permite usar Google/Gemini (Nano Banana)
-- só para imagens, sem mexer no provider de texto. Chave em base64 (mesmo padrão de api_key).
-- Idempotente: um bloco por coluna (ORA-01430 = coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE ai_configs ADD media_provider VARCHAR2(20) DEFAULT 'google']';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE ai_configs ADD media_api_key VARCHAR2(2000)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE ai_configs ADD media_image_model VARCHAR2(100) DEFAULT 'gemini-2.5-flash-image']';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

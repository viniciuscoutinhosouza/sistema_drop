-- 168_app_config.sql
-- Config GLOBAL chave/valor do sistema (ajustes simples sem tabela de domínio própria).
-- 1º uso: separation.finish_photos_code (código que o operador bipa para encerrar as fotos
-- no modo Bipagem automática). Global — não por galpão. Idempotente (ORA-00955).

DECLARE
  e_obj_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_obj_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE app_config (
      key        VARCHAR2(100) PRIMARY KEY,
      value      VARCHAR2(1000),
      updated_by NUMBER REFERENCES users(id),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
    )';
EXCEPTION
  WHEN e_obj_exists THEN NULL;
END;
/

-- O default do código de fim ('FIM-FOTOS') é resolvido no service (get com fallback) quando a
-- chave ainda não existe — não precisa seed aqui.

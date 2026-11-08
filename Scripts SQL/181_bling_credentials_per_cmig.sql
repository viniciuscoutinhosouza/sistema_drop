-- 181_bling_credentials_per_cmig.sql
-- Credenciais do app Bling CONFIGURÁVEIS POR CMIG (ADR-0040): além do app padrão do .env
-- (BLING_CLIENT_ID/SECRET), cada CMIG pode ter o PRÓPRIO client_id/secret, editável na tela.
-- client_id não é segredo (fica em claro); client_secret CIFRADO (Fernet, services/crypto),
-- nunca em claro. Idempotente (ORA-01430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_bling_accounts ADD (client_id VARCHAR2(200))';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_bling_accounts ADD (client_secret_enc VARCHAR2(2000))';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

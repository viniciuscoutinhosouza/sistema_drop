-- Migration 92: Tabela `smtp_config` — configuração do servidor de e-mail (SMTP).
-- Singleton (uma linha): usada para enviar o código OTP de vínculo de conta de
-- marketplace e demais e-mails transacionais. Idempotente.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE smtp_config (
      id            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      host          VARCHAR2(255),
      port          NUMBER DEFAULT 587,
      username      VARCHAR2(255),
      password      VARCHAR2(500),
      use_tls       NUMBER(1) DEFAULT 1 CONSTRAINT chk_smtp_tls CHECK (use_tls IN (0,1)),
      use_ssl       NUMBER(1) DEFAULT 0 CONSTRAINT chk_smtp_ssl CHECK (use_ssl IN (0,1)),
      from_email    VARCHAR2(255),
      from_name     VARCHAR2(255),
      is_active     NUMBER(1) DEFAULT 0 CONSTRAINT chk_smtp_active CHECK (is_active IN (0,1)),
      updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

COMMIT;

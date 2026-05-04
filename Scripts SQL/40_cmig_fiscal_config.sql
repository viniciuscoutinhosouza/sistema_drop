-- Migration 40: Tabela `cmig_fiscal_config` — configuração de emissor NFe por CMIG
-- Idempotente.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE cmig_fiscal_config (
      id                          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cmig_id                     NUMBER NOT NULL,
      crt                         NUMBER(1) DEFAULT 1
                                      CONSTRAINT chk_cfc_crt CHECK (crt IN (1,2,3,4)),
      environment                 VARCHAR2(20) DEFAULT 'homolog'
                                      CONSTRAINT chk_cfc_env CHECK (environment IN ('homolog','production')),
      focus_company_token         VARCHAR2(200),
      focus_company_id            VARCHAR2(100),
      focus_registered_at         TIMESTAMP WITH TIME ZONE,
      certificate_uploaded_at     TIMESTAMP WITH TIME ZONE,
      certificate_expires_at      TIMESTAMP WITH TIME ZONE,
      certificate_subject         VARCHAR2(500),
      ie                          VARCHAR2(20),
      im                          VARCHAR2(20),
      cnae                        VARCHAR2(10),
      default_natureza_operacao   VARCHAR2(255) DEFAULT 'Venda de mercadoria',
      nfe_serie                   NUMBER DEFAULT 1,
      nfe_next_number             NUMBER DEFAULT 1,
      csc_id                      VARCHAR2(20),
      csc_token                   VARCHAR2(100),
      fiscal_email_copy           VARCHAR2(255),
      created_at                  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      updated_at                  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_cfc_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
      CONSTRAINT uq_cfc_cmig UNIQUE (cmig_id)
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

COMMIT;

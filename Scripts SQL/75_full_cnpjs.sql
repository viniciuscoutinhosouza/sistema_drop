-- 75_full_cnpjs.sql
-- Cadastro de CNPJs do ML Fulfillment por conta de marketplace.
-- Executar antes de 76_full_stock.sql.

DECLARE
  e_tab_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_tab_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE full_cnpjs (
      id                     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      marketplace_account_id NUMBER        NOT NULL REFERENCES marketplace_accounts(id),
      cmig_id                NUMBER        NOT NULL REFERENCES cmigs(id),
      cnpj                   VARCHAR2(18)  NOT NULL,
      label                  VARCHAR2(100),
      is_active              NUMBER(1)     DEFAULT 1 NOT NULL,
      created_at             TIMESTAMP     DEFAULT SYSTIMESTAMP
    )
  ';
EXCEPTION WHEN e_tab_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uix_full_cnpjs_account_cnpj ON full_cnpjs(marketplace_account_id, cnpj)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_full_cnpjs_cmig ON full_cnpjs(cmig_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

-- Verificação
SELECT COUNT(*) AS total_full_cnpjs FROM full_cnpjs;

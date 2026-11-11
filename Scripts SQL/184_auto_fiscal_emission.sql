-- 184_auto_fiscal_emission.sql
-- Emissão AUTOMÁTICA de NF-e + etiqueta com DANFE ao ficar "Pronto p/ Envio" (ADR-0041).
--
-- (1) marketplace_accounts.nfe_auto_emit — toggle OPT-IN por conta (default 0/desligado):
--     quando ligado, o pedido não-FULL que fica ready_to_ship/invoice_pending dispara a emissão
--     sozinho, roteada por nfe_emission_mode (own × marketplace, migration 151). Default 0 =
--     ZERO regressão (o deploy sozinho não muda comportamento de nenhuma conta).
-- (2) orders.auto_fiscal_* — "lane" de workflow/observabilidade do fluxo automático (NÃO é a
--     verdade fiscal; o SSOT da autorização continua em nfe_status/Invoice):
--       auto_fiscal_status  : NULL | emitting | emitted | done | error
--       auto_fiscal_error   : última mensagem de falha (falhar alto, nunca em silêncio)
--       auto_fiscal_attempts: contador p/ backoff com teto (não bate na SEFAZ no mesmo pedido
--                             doomed a cada tick).
-- Idempotente (ORA-01430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD (nfe_auto_emit NUMBER(1) DEFAULT 0 NOT NULL)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (auto_fiscal_status VARCHAR2(16))';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (auto_fiscal_error VARCHAR2(500))';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (auto_fiscal_attempts NUMBER DEFAULT 0 NOT NULL)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

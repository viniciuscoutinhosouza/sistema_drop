-- ============================================================
-- MIG ECOMMERCE – Script 70: Capacidades de Envio por Conta
-- ============================================================
-- Adiciona em marketplace_accounts colunas que indicam quais modalidades
-- de envio a conta tem habilitadas no marketplace (hoje: Flex e Full no ML).
--
-- Estratégia híbrida:
--   - has_flex / has_full: detectados automaticamente via API ML
--     (consulta items/search por logistic_type)
--   - has_flex_override / has_full_override: override manual do admin
--     (NULL = usa o detectado; TRUE/FALSE = sobrescreve)
--   - shipping_modes_checked_at: timestamp do último auto-detect
--     (cache de 24h pra evitar bater na API a cada consulta)
--
-- Idempotente.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD has_flex NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD has_full NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD has_flex_override NUMBER(1)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD has_full_override NUMBER(1)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD shipping_modes_checked_at TIMESTAMP WITH TIME ZONE';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

-- 132_shopee_account_fields.sql
-- Campos da loja Shopee preenchidos no callback (get_shop_info) e para multi-loja futura.
--
-- Contexto: o callback Shopee gravava só o shop_id e o token; nome/região/status da loja
-- ficavam vazios (platform_username nulo). A partir da Fase 1 (paridade Shopee, ADR-0020) o
-- get_shop_info popula região/status, e main_account_id fica reservado para conta principal
-- multi-loja (nulo por ora).
--
-- Idempotente: EXCEPTION WHEN e_col_exists (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);   -- ORA-01430: column already exists

  PROCEDURE add_col(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE marketplace_accounts ADD (shop_region VARCHAR2(10))');
  add_col('ALTER TABLE marketplace_accounts ADD (shop_status VARCHAR2(20))');
  add_col('ALTER TABLE marketplace_accounts ADD (main_account_id NUMBER)');
  COMMIT;
END;
/

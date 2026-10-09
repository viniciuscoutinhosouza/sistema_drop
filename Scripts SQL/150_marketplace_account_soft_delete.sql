-- 150_marketplace_account_soft_delete.sql
-- Exclusão lógica de CONTA de marketplace (ADR: reorg menu + marketplaces por CMIG).
-- Quando a conta tem histórico (pedidos/claims/mensagens/estoque FULL/anúncios) que o
-- banco não deixa apagar por FK, o "Excluir" ARQUIVA a conta: is_active=0 + is_deleted=1.
-- Nesse estado a conta some de toda a UI/seletor e nada deve reativá-la sem limpar is_deleted.
-- Invariante: is_deleted=1 IMPLICA is_active=0.
-- Idempotente (ORA-01430 = coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE marketplace_accounts ADD (is_deleted NUMBER(1) DEFAULT 0 NOT NULL)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE marketplace_accounts ADD (deleted_at TIMESTAMP WITH TIME ZONE)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

-- Backfill de segurança: nenhuma conta nasce excluída.
UPDATE marketplace_accounts SET is_deleted = 0 WHERE is_deleted IS NULL;
COMMIT;
/

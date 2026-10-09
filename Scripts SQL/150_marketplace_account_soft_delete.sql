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

-- Sem backfill: a coluna nasce NUMBER(1) DEFAULT 0 NOT NULL (nenhuma conta nasce excluída)
-- e a invariante is_deleted=1 ⇒ is_active=0 é garantida em código (purge_account).

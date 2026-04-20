-- ============================================================
-- MIG ECOMMERCE – Script 15: Corrige coluna orders.integration_id → account_id
-- Executar se o Script 12 foi rodado mas o passo 12 estava comentado
-- ============================================================

-- Renomear coluna
ALTER TABLE orders RENAME COLUMN integration_id TO account_id;

-- Remover FK antiga (nome pode variar — tente ambas)
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'FK_ORD_INTEGRATION'
     AND table_name = 'ORDERS';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE orders DROP CONSTRAINT fk_ord_integration';
  END IF;
END;
/

-- Adicionar nova FK
ALTER TABLE orders ADD CONSTRAINT fk_ord_account
    FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id);

COMMIT;

-- Validação
SELECT column_name, data_type FROM user_tab_columns
 WHERE table_name = 'ORDERS' AND column_name IN ('INTEGRATION_ID','ACCOUNT_ID');

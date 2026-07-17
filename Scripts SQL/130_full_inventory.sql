-- Migration 130: Inventário FULL (ADR-0019 Fase 2).
--
-- Permite catalog_type/product_type='full' no inventário e adiciona `account_id` ao
-- documento — o estoque FULL é por (CMIGProduct × conta ML), então um inventário FULL
-- pertence a UMA conta. A contagem do ML (na importação de anúncios FULL) vira um
-- inventário FULL em rascunho que o usuário finaliza como Baseline/Ajuste; o evento
-- entra no replay do `recompute_full_stock` (Fase 1).
--
-- Idempotente: COUNT-then-DROP nas CHECKs (padrão da 129), EXCEPTION para ADD COLUMN/FK.

-- 1) inventories.catalog_type aceitar 'full'
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'CK_INV_CATALOG' AND table_name = 'INVENTORIES';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE inventories DROP CONSTRAINT ck_inv_catalog';
  END IF;
END;
/

ALTER TABLE inventories ADD CONSTRAINT ck_inv_catalog
  CHECK (catalog_type IN ('pg','cmig','full'));

-- 2) inventory_items.product_type aceitar 'full'
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'CK_INVITEM_TYPE' AND table_name = 'INVENTORY_ITEMS';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE inventory_items DROP CONSTRAINT ck_invitem_type';
  END IF;
END;
/

ALTER TABLE inventory_items ADD CONSTRAINT ck_invitem_type
  CHECK (product_type IN ('pg','cmig','full'));

-- 3) inventories.account_id — conta ML do inventário FULL (NULL p/ pg/cmig)
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE inventories ADD (account_id NUMBER)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

-- 4) FK account_id → marketplace_accounts
DECLARE
  e_const_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_const_exists, -02264);
  e_dup_fk EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_dup_fk, -02275);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE inventories ADD CONSTRAINT fk_inv_account '
                 || 'FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id)';
EXCEPTION
  WHEN e_const_exists THEN NULL;
  WHEN e_dup_fk THEN NULL;
END;
/

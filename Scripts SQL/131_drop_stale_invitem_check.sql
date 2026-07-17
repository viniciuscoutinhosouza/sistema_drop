-- Migration 131: remove a CHECK constraint DUPLICADA/obsoleta de inventory_items.product_type.
--
-- A migration 130 adicionou CK_INVITEM_TYPE (pg/cmig/full), mas a constraint que a tabela JÁ
-- possuía chama-se CK_INVENTORY_ITEMS_TYPE (pg/cmig) — a 130 usou outro nome e criou uma
-- DUPLICATA em vez de alterar a real. Com as duas valendo, a antiga continuava rejeitando
-- product_type='full' (ORA-02290 CK_INVENTORY_ITEMS_TYPE) ao criar itens de inventário FULL.
--
-- Dropa a antiga; CK_INVITEM_TYPE (superset pg/cmig/full) permanece como a válida. Idempotente:
-- só dropa se existir. Em bancos criados do zero pelo model (que usa o nome ck_invitem_type) a
-- CK_INVENTORY_ITEMS_TYPE não existe → nada a fazer.

DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'CK_INVENTORY_ITEMS_TYPE' AND table_name = 'INVENTORY_ITEMS';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE inventory_items DROP CONSTRAINT ck_inventory_items_type';
  END IF;
END;
/

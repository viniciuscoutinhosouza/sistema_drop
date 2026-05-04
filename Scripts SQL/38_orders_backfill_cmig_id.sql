-- 38_orders_backfill_cmig_id.sql
-- Backfill da coluna orders.cmig_id a partir do marketplace_accounts.cmig_id.
-- A coluna já existe (FK para cmigs); só estamos populando valores ausentes.
-- Idempotente: só atualiza onde está NULL.

UPDATE orders o
SET o.cmig_id = (
    SELECT ma.cmig_id
    FROM marketplace_accounts ma
    WHERE ma.id = o.account_id
)
WHERE o.cmig_id IS NULL
  AND o.account_id IS NOT NULL;

COMMIT;

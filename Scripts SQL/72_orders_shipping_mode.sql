-- Migration 72: shipping_mode (bucket amigavel derivado do logistic_type do ML)
-- Valores possiveis: full | flex | agencia | correios | coletado | combinado | desconhecido

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD shipping_mode VARCHAR2(20)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Backfill a partir do shipping_method (logistic_type cru) ja gravado
UPDATE orders
SET shipping_mode = CASE
  WHEN shipping_method = 'fulfillment' THEN 'full'
  WHEN shipping_method = 'self_service' THEN 'flex'
  WHEN shipping_method IN ('xd_drop_off','drop_off') THEN 'agencia'
  WHEN shipping_method = 'cross_docking' THEN 'correios'
  WHEN shipping_method = 'xd_pickup' THEN 'coletado'
  WHEN shipping_method = 'not_specified' THEN 'combinado'
  WHEN (shipping_method IS NULL OR shipping_method = '') AND shipment_id IS NULL THEN 'combinado'
  ELSE 'desconhecido'
END
WHERE shipping_mode IS NULL;

COMMIT;

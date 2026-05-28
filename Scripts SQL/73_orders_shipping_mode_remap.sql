-- Migration 73: remapeamento de shipping_mode segundo doc oficial ML.
-- Corrige duas trocas que estavam na migration 72:
--   drop_off:      antes 'agencia'  -> agora 'correios' (vendedor leva nos Correios)
--   cross_docking: antes 'correios' -> agora 'coletado' (ML coleta no vendedor)
-- Mantem: self_service=flex, fulfillment=full, xd_drop_off=agencia (Places/Agil)

UPDATE orders
SET shipping_mode = CASE
  WHEN shipping_method = 'fulfillment'   THEN 'full'
  WHEN shipping_method = 'self_service'  THEN 'flex'
  WHEN shipping_method = 'drop_off'      THEN 'correios'   -- ERA 'agencia'
  WHEN shipping_method = 'xd_drop_off'   THEN 'agencia'    -- mantido (Places/Agil)
  WHEN shipping_method = 'cross_docking' THEN 'coletado'   -- ERA 'correios'
  WHEN shipping_method = 'xd_pickup'     THEN 'coletado'
  WHEN shipping_method = 'not_specified' THEN 'combinado'
  WHEN (shipping_method IS NULL OR shipping_method = '') AND shipment_id IS NULL THEN 'combinado'
  ELSE shipping_mode  -- preserva valores ja corretos / desconhecido
END
WHERE shipping_method IN ('drop_off', 'cross_docking');

COMMIT;

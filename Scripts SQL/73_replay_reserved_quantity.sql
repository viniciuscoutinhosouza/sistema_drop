-- 73_replay_reserved_quantity.sql
-- Preenche reserved_quantity nos produtos a partir dos pedidos ativos existentes.
-- Pedidos "ativos para reserva": não cancelados, não entregues, não despachados.
-- Executar UMA VEZ após o deploy da Fase 1 do sistema de controle de estoque.

-- 1. catalog_products — produtos PG diretamente vinculados a itens de pedido
UPDATE catalog_products cp
SET reserved_quantity = (
    SELECT COALESCE(SUM(oi.quantity), 0)
      FROM order_items oi
      JOIN orders o ON oi.order_id = o.id
     WHERE oi.catalog_product_id = cp.id
       AND o.status NOT IN ('cancelled', 'delivered', 'shipped')
       AND (o.shipment_status IS NULL
            OR o.shipment_status NOT IN ('shipped', 'delivered', 'in_transit',
                                         'out_for_delivery', 'first_visit'))
);

-- 2. cmig_products — produtos CMIG diretamente vinculados a itens de pedido
UPDATE cmig_products cmp
SET reserved_quantity = (
    SELECT COALESCE(SUM(oi.quantity), 0)
      FROM order_items oi
      JOIN orders o ON oi.order_id = o.id
     WHERE oi.cmig_product_id = cmp.id
       AND o.status NOT IN ('cancelled', 'delivered', 'shipped')
       AND (o.shipment_status IS NULL
            OR o.shipment_status NOT IN ('shipped', 'delivered', 'in_transit',
                                         'out_for_delivery', 'first_visit'))
);

-- 3. catalog_product_variants — variantes PG
UPDATE catalog_product_variants cpv
SET reserved_quantity = (
    SELECT COALESCE(SUM(oi.quantity), 0)
      FROM order_items oi
      JOIN orders o ON oi.order_id = o.id
     WHERE oi.catalog_variant_id = cpv.id
       AND oi.catalog_source = 'pg'
       AND o.status NOT IN ('cancelled', 'delivered', 'shipped')
       AND (o.shipment_status IS NULL
            OR o.shipment_status NOT IN ('shipped', 'delivered', 'in_transit',
                                         'out_for_delivery', 'first_visit'))
);

-- 4. cmig_product_variants — variantes CMIG
UPDATE cmig_product_variants cpv
SET reserved_quantity = (
    SELECT COALESCE(SUM(oi.quantity), 0)
      FROM order_items oi
      JOIN orders o ON oi.order_id = o.id
     WHERE oi.catalog_variant_id = cpv.id
       AND oi.catalog_source = 'cmig'
       AND o.status NOT IN ('cancelled', 'delivered', 'shipped')
       AND (o.shipment_status IS NULL
            OR o.shipment_status NOT IN ('shipped', 'delivered', 'in_transit',
                                         'out_for_delivery', 'first_visit'))
);

-- Grava movimentos de auditoria para os pedidos ativos existentes
-- (para que o histórico de stock_movements não fique vazio para pedidos antigos)
INSERT INTO stock_movements (product_type, product_id, order_id, movement_type, qty, field_affected, delta)
SELECT
    'pg'                      AS product_type,
    oi.catalog_product_id     AS product_id,
    o.id                      AS order_id,
    'reserve'                 AS movement_type,
    oi.quantity               AS qty,
    'reserved_quantity'       AS field_affected,
    oi.quantity               AS delta
  FROM order_items oi
  JOIN orders o ON oi.order_id = o.id
 WHERE oi.catalog_product_id IS NOT NULL
   AND o.status NOT IN ('cancelled', 'delivered', 'shipped')
   AND (o.shipment_status IS NULL
        OR o.shipment_status NOT IN ('shipped', 'delivered', 'in_transit',
                                     'out_for_delivery', 'first_visit'))
   AND NOT EXISTS (
       SELECT 1 FROM stock_movements sm
        WHERE sm.order_id = o.id AND sm.movement_type = 'reserve'
   );

INSERT INTO stock_movements (product_type, product_id, order_id, movement_type, qty, field_affected, delta)
SELECT
    'cmig'                    AS product_type,
    oi.cmig_product_id        AS product_id,
    o.id                      AS order_id,
    'reserve'                 AS movement_type,
    oi.quantity               AS qty,
    'reserved_quantity'       AS field_affected,
    oi.quantity               AS delta
  FROM order_items oi
  JOIN orders o ON oi.order_id = o.id
 WHERE oi.cmig_product_id IS NOT NULL
   AND oi.catalog_product_id IS NULL
   AND o.status NOT IN ('cancelled', 'delivered', 'shipped')
   AND (o.shipment_status IS NULL
        OR o.shipment_status NOT IN ('shipped', 'delivered', 'in_transit',
                                     'out_for_delivery', 'first_visit'))
   AND NOT EXISTS (
       SELECT 1 FROM stock_movements sm
        WHERE sm.order_id = o.id AND sm.movement_type = 'reserve'
   );

COMMIT;

-- Verificação: mostra o resultado
SELECT 'catalog_products' AS tabela, COUNT(*) AS produtos_com_reserva
  FROM catalog_products WHERE reserved_quantity > 0
UNION ALL
SELECT 'cmig_products', COUNT(*)
  FROM cmig_products WHERE reserved_quantity > 0;

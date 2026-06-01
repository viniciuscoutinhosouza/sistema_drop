-- 74_zero_all_stock.sql
-- Reset de estoque: zera todos os contadores de estoque para reconstrução a partir de eventos.
-- Executar antes de chamar POST /api/v1/stock/recompute-all.
-- ATENÇÃO: Ação irreversível. Fazer backup antes de executar.

-- 1. Zera stock_quantity (cache do replay de eventos)
UPDATE catalog_products SET stock_quantity = 0;
UPDATE cmig_products SET stock_quantity = 0;

-- 2. Zera colunas transacionais (reservation service)
UPDATE catalog_products SET
    reserved_quantity = 0,
    awaiting_return_quantity = 0,
    pending_validation_quantity = 0,
    unfit_quantity = 0;

UPDATE cmig_products SET
    reserved_quantity = 0,
    awaiting_return_quantity = 0,
    pending_validation_quantity = 0,
    unfit_quantity = 0;

-- 3. Reinicia flag stock_updated nas NF-e de entrada para que possam ser reprocessadas
--    pelo recompute_all_stock (que usa stock_updated=True para incluir a NF-e no replay)
UPDATE invoices
   SET stock_updated = 0
 WHERE direction = 'in'
   AND status IN ('finalized', 'authorized');

COMMIT;

-- Verificação
SELECT 'catalog_products' AS tabela,
       COUNT(*) AS total,
       SUM(stock_quantity) AS soma_stock
  FROM catalog_products
UNION ALL
SELECT 'cmig_products',
       COUNT(*),
       SUM(stock_quantity)
  FROM cmig_products
UNION ALL
SELECT 'invoices_reset',
       COUNT(*),
       0
  FROM invoices
 WHERE direction = 'in'
   AND stock_updated = 0;


   COMMIT;

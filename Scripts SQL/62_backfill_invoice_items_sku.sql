-- Migration 62: Backfill `invoice_items.sku` para itens existentes vinculados a CMIGProduct
-- A migration 61 adicionou a coluna mas não populou itens antigos.
-- Esta migration pega o SKU diretamente do CMIGProduct para todos os itens com
-- cmig_product_id setado e sku ainda NULL/vazio.
-- Idempotente — pode rodar várias vezes; só atualiza linhas vazias.

BEGIN
  UPDATE invoice_items ii
     SET sku = (
           SELECT cp.sku_cmig
             FROM cmig_products cp
            WHERE cp.id = ii.cmig_product_id
         )
   WHERE ii.cmig_product_id IS NOT NULL
     AND (ii.sku IS NULL OR ii.sku = '')
     AND EXISTS (
           SELECT 1
             FROM cmig_products cp
            WHERE cp.id = ii.cmig_product_id
              AND cp.sku_cmig IS NOT NULL
         );
  COMMIT;
END;

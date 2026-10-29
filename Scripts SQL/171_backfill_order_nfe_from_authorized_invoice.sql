-- Migration 171: backfill dos campos fiscais DENORMALIZADOS do pedido a partir da NF-e autorizada.
--
-- Contexto: a sincronização `order.nfe_status/nfe_key/invoice_id` vivia só no caminho de emissão
-- PELO PEDIDO (orders.py, após transmit_invoice). Quando uma NF-e rejeitada é RETRANSMITIDA direto
-- pela tela da nota (POST /invoices/{id}/transmit), a nota autorizava mas o pedido ficava preso em
-- "NF-e Pendente" com o botão "Gerar NFe" (o vínculo order->invoice não era gravado). O código já
-- foi corrigido (sincroniza no ponto único do transmit); este backfill conserta os pedidos que já
-- ficaram nesse estado (ex.: pedido 13636) — nota autorizada não pode ser re-transmitida.
--
-- Seguro/idempotente: só casa pedidos cuja NF-e própria de SAÍDA está AUTORIZADA em PRODUÇÃO
-- (invoices.order_id = orders.id), pegando a mais recente por pedido (ROW_NUMBER). NÃO toca notas
-- de marketplace/Faturador ML: `environment` só é preenchido na emissão própria SEFAZ, então as de
-- marketplace (upload de XML, environment NULL) ficam FORA da fonte do MERGE. O WHERE do WHEN MATCHED
-- torna a 2ª execução no-op; um pedido já 'authorized' só é tocado se o invoice_id divergir da
-- emissão própria mais recente (re-aponta para ela — comportamento desejado, não clobber indevido).

MERGE INTO orders o
USING (
  SELECT order_id, access_key, inv_id FROM (
    SELECT i.order_id,
           i.access_key,
           i.id AS inv_id,
           ROW_NUMBER() OVER (PARTITION BY i.order_id ORDER BY i.id DESC) AS rn
    FROM invoices i
    WHERE i.direction = 'out'
      AND i.status = 'authorized'
      AND i.environment = 'production'
      AND i.order_id IS NOT NULL
  )
  WHERE rn = 1
) src
ON (o.id = src.order_id)
WHEN MATCHED THEN UPDATE SET
    o.nfe_status = 'authorized',
    o.nfe_key = src.access_key,
    o.invoice_id = src.inv_id
  WHERE (o.nfe_status IS NULL OR o.nfe_status <> 'authorized' OR o.invoice_id IS NULL OR o.invoice_id <> src.inv_id)

# Pedidos, Packs e Envios

Como ler vendas, agrupamentos (packs) e gerenciar envios via API.

## Sumário

1. [Conceitos: Order, Pack, Shipment](#conceitos-order-pack-shipment)
2. [Consultar pedido](#consultar-pedido)
3. [Buscar vendas (lista)](#buscar-vendas-lista)
4. [Tags importantes](#tags-importantes)
5. [Packs (carrinho)](#packs-carrinho)
6. [Shipments (envios)](#shipments-envios)
7. [Modos de envio: ME1, ME2, Flex, Full](#modos-de-envio-me1-me2-flex-full)
8. [Pagamentos no contexto da order](#pagamentos-no-contexto-da-order)
9. [Cancelamentos e fraudes](#cancelamentos-e-fraudes)

## Conceitos: Order, Pack, Shipment

- **Order** (pedido) — uma compra de **um único item** (com possíveis múltiplas unidades). `order_id`.
- **Pack** — agrupamento de uma ou mais orders (carrinho). Toda compra **gera um pack_id**, mesmo as de uma única order.
- **Shipment** — envio. Relação 1:N com order (um shipment pode entregar várias orders do mesmo pack). Existe quando o item tem logística associada.

Relações:
- 1 Pack → N Orders
- 1 Pack → 0 ou 1 Shipment (`not_specified` pode não ter shipment)
- 1 Order → 1 Pack
- 1 Order → 0 ou 1 Shipment

## Consultar pedido

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/orders/2000008779458474
```

Resposta inclui:
- `id`, `status`, `status_detail`
- `date_created`, `date_closed`, `last_updated`
- `buyer` (apenas dados básicos — para nome completo/CPF use os endpoints específicos com cuidado de LGPD)
- `seller`
- `order_items` (array com `item`, `quantity`, `unit_price`, `currency_id`, `sale_fee`)
- `payments` (array, com `id`, `status`, `transaction_amount`, `payment_type`)
- `shipping` (objeto com `id` do shipment)
- `pack_id`
- `tags`
- `total_amount`
- `taxes`

**Header útil:**

```
x-format-new: true
```

Devolve resposta no formato novo (recomendado para integrações novas — campos mais consistentes, especialmente em `taxes` e `shipping`).

### Status possíveis

- `confirmed` — venda confirmada, aguardando pagamento.
- `payment_required` — pagamento pendente.
- `payment_in_process` — pagamento sendo processado.
- `partially_paid` — parcialmente pago.
- `paid` — pago, libera para envio.
- `cancelled` — cancelado.
- `invalid` — inválido (raro).

⚠️ **Não use `payments[].status` como única fonte de verdade.** O `order.status` consolida.

## Buscar vendas (lista)

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/orders/search?seller=SELLER_ID&order.status=paid'
```

⚠️ **`/orders/search` requer pelo menos um filtro** — sem filtro retorna lista vazia.

### Filtros úteis

| Filtro | Uso |
|---|---|
| `seller=SELLER_ID` | Vendas como vendedor |
| `buyer=BUYER_ID` | Compras como comprador |
| `order.status=paid` | Status |
| `order.date_created.from=2026-01-01T00:00:00.000-03:00` | Data inicial |
| `order.date_created.to=2026-01-31T23:59:59.999-03:00` | Data final |
| `tags=cart` | Apenas pedidos de carrinho |
| `tags.not=test_order` | Excluir tag |
| `q=...` | Busca genérica (item ID, nickname, título) |
| `sort=date_desc` | Ordenação |

### Paginação

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/orders/search?seller=SELLER_ID&offset=50&limit=50'
```

Limite máximo: 50 por página, offset máximo: 1000. Para datas mais antigas, use filtros de data progressivos (semana a semana).

⚠️ **Pedidos são salvos por 12 meses.** Para histórico mais antigo, use os relatórios de faturamento.

## Tags importantes

Tags em `order.tags` indicam características importantes:

- `paid` — pago.
- `not_paid` — não pago.
- `not_delivered` — não entregue.
- `delivered` — entregue.
- `cart` — pedido fez parte de carrinho.
- `fraud_risk_detected` — ⚠️ **alerta de fraude**. Cancelar imediatamente; **não enviar mercadoria**.
- `test_order` — pedido de teste (usuários de teste).

Sempre verificar `tags` antes de processar logisticamente.

## Packs (carrinho)

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/packs/PACK_ID
```

Resposta:

```json
{
  "id": 2000006181551917,
  "status": "released",
  "status_detail": null,
  "buyer": {...},
  "shipment": { "id": 43729529445 },
  "orders": [
    { "id": 2000009047722568 },
    { "id": 2000009047707726 }
  ]
}
```

Para múltiplos itens no mesmo pacote, **processe pelo pack_id**, não order por order — facilita logística e respostas a perguntas.

### Ready-to-ship (ME2)

Marcar "Já tenho o produto" para liberar despacho:

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/shipments/SHIPMENT_ID/process/ready_to_ship
```

⚠️ Apenas para **ordens ME2**. Não funciona para Flex ou Full.

### Subpacks (split de pacote)

Quando precisar dividir um pack em vários pacotes (depósitos diferentes, frágeis, caixas):

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{
    "subpacks": [
      { "package_id": "PKG-1", "orders": [{"id": 2000009047722568}] },
      { "package_id": "PKG-2", "orders": [{"id": 2000009047707726}] }
    ]
  }' \
  https://api.mercadolibre.com/shipments/SHIPMENT_ID/subpacks
```

**Regras:**
- Soma de subpacks tem que cobrir **todos** os itens do pack original (sem sobrar nem faltar).
- `package_id` ou está em todos ou em nenhum.
- Não funciona para Flex/Full.

## Shipments (envios)

### Consultar shipment

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'x-format-new: true' \
  https://api.mercadolibre.com/shipments/SHIPMENT_ID
```

### Status e substatus

| Status | Significado |
|---|---|
| `pending` | Aguardando ação inicial |
| `handling` | Vendedor está preparando |
| `ready_to_ship` | Pronto para retirada/postagem |
| `shipped` | Em trânsito |
| `delivered` | Entregue |
| `not_delivered` | Não entregue (problema) |
| `cancelled` | Cancelado |

Substatuses são muitos e variam por modo de envio. Sempre logar e exibir o substatus para debugar.

### Datas de SLA (importante)

Em `shipping_option.estimated_*`:
- `estimated_handling_limit` — data limite para vendedor despachar.
- `estimated_delivery_extended` — segunda promessa de entrega.
- `estimated_delivery_limit` — data limite para comprador cancelar com devolução.
- `estimated_delivery_final` — data final que define `delivered` ou `not_delivered`.

Atrasar `estimated_handling_limit` afeta reputação. Monitore.

### Histórico do shipment

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'x-format-new: true' \
  https://api.mercadolibre.com/shipments/SHIPMENT_ID/history
```

### Tracking (transportadora)

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'x-format-new: true' \
  https://api.mercadolibre.com/shipments/SHIPMENT_ID/carrier
```

Retorna nome da transportadora e URL de rastreio.

### Etiquetas de envio (PDF/ZPL)

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/shipment_labels?shipment_ids=SHIPMENT_ID&response_type=pdf'
```

Formatos: `pdf`, `zpl2` (impressoras Zebra).

## Modos de envio: ME1, ME2, Flex, Full

| Modo | Quem manda | Fluxo |
|---|---|---|
| **Não logístico** (`not_specified`) | Vendedor combina com comprador fora do ML | Sem shipment formal |
| **ME1** (Mercado Envios 1) | Vendedor escolhe transportadora, posta com etiqueta própria | Vendedor atualiza status manualmente |
| **ME2** | ML calcula frete, gera etiqueta, vendedor leva à agência ou usa coleta | Status atualizado automaticamente pelo ML |
| **Flex** | Vendedor entrega no mesmo dia, dentro de raio definido | Coleta + entrega same-day |
| **Full (Fulfillment)** | Vendedor envia estoque para CD do ML; ML faz tudo | Vendedor não toca em logística após envio inicial |

**Como descobrir o modo:**

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'x-format-new: true' \
  https://api.mercadolibre.com/shipments/SHIPMENT_ID
```

Procure `logistic_type`: `xd_drop_off` (ME2 agência), `self_service` (Flex), `fulfillment` (Full), `cross_docking` (ME2 padrão).

⚠️ **Para Full e Flex, NÃO atualize status manualmente**, NÃO envie mensagens de "produto despachado", NÃO chame `ready_to_ship` — o ML gerencia tudo. Atualizações manuais geram reclamações.

## Pagamentos no contexto da order

`order.payments[]` traz os pagamentos. Para detalhes (estornos, antifraude, dados de cartão mascarados):

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadopago.com/v1/payments/PAYMENT_ID
```

⚠️ **Importante**: cupons e descontos **não vêm em `payments[].discount`**. Para detalhes precisos use endpoints de descontos/promoções específicos.

## Cancelamentos e fraudes

### Detectar fraude

Webhook `orders_v2` com tag `fraud_risk_detected`:

```json
{
  "topic": "orders_v2",
  "resource": "/orders/2195160686",
  ...
}
```

Ao buscar a order:

```json
{
  "id": 2195160686,
  "tags": ["fraud_risk_detected", ...],
  ...
}
```

**Ação obrigatória:** **NÃO enviar a mercadoria**. Cancelar pelo painel ou API. Se já enviou, comprovar no painel.

### Cancelar pedido

```bash
curl -X PUT \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{ "status": "cancelled", "reason_id": "out_of_stock" }' \
  https://api.mercadolibre.com/orders/ORDER_ID
```

**Reasons válidos** variam por contexto. Os principais:

- `out_of_stock` — sem estoque.
- `customer_request` — comprador pediu.
- `seller_request` — vendedor desistiu.
- `fraud_risk_detected` — fraude.

Cancelar gera **impacto na reputação**. Use só quando necessário.

### Re-compras (failed payments)

Se um pagamento original falhou e o comprador refez:
- O `shipment` original pode mudar.
- Se virou `cancelled` com substatus `closed_by_user`, a venda precisa ser cancelada.
- Sempre conferir após webhook `orders_v2` se é a mesma order ou re-compra.

## Cálculo de total considerando taxes

Para vendas com taxas (Argentina, alguns casos do Brasil):

```
total = order.total_amount + order.taxes.amount + shipping.lead_time.cost
```

**`taxes.amount`** vem em `/orders/{id}` com `x-format-new: true`.
**`lead_time.cost`** vem em `/shipments/{id}`.

Se `taxes.currency_id` for diferente de `items.currency_id`, converter antes:

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/currency_conversions/search?from=ARS&to=USD'
```

## Boas práticas

1. **Sempre buscar a order/shipment fresco** após webhook — payload do webhook só indica que algo mudou.
2. **Idempotência**: webhooks chegam mais de uma vez. Use `notification._id` ou `(resource, last_updated)` como chave única para não processar 2x.
3. **Não pollar `/orders/search`** se webhooks estão configurados. Use só como redundância para missed feeds.
4. **Para reconciliação financeira**, use os endpoints de Billing Reports (`/billing/integration/...`) com `group=ML` ou `group=MP`.
5. **Para Full**, nunca tente atualizar estoque manualmente — use `/stock/fulfillment` ou os webhooks de estoque.

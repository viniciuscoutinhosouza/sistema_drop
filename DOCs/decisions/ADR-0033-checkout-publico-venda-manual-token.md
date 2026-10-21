# ADR-0033 — Checkout público da venda manual por token + re-análise de desconto (Fase 3)

## Status
Aceita (2026-10-21). Fase 3 do subsistema de recebimento/checkout (ADR-0031 Fase 1, ADR-0032 Fase 2). Fase 4 (crédito CMIG×Galpão) virá depois.

## Contexto
O dono quer que, ao registrar uma **venda manual**, o sistema gere um **link** para o cliente **ver o pedido, ajustar os itens e pagar** (via ASAAS, reusando a Fase 2) — sem precisar de login. Estágios da venda manual: **1. Pedido → 2. Pagamento → 3. Separação → 4. Enviado → 5. Entregue** (o dono **adiou** 3-5 nesta fase). Regra do dono: **se o cliente reduzir/remover itens e o pedido tinha desconto, re-analisar o desconto**.

O modelo não tem campo de desconto: o desconto é o operador pôr `unit_price` abaixo do `suggested_price` do produto (ver `manual_orders.create_manual_order`). Então "tinha desconto" = algum item com `unit_price < preço de referência`.

## Decisão
1. **Token público por pedido** (`orders.public_token`, migration 154): opaco (`secrets.token_urlsafe`), **único**, gerado sob demanda pela ação do operador "Enviar link" (`POST /manual-orders/{id}/public-link`, autenticado). Dá acesso **sem login** só àquele pedido. Revogável (regerar troca o token).
2. **Snapshot do preço de referência** (`order_items.list_price`, migration 154): grava o `suggested_price` do produto **no momento da venda**. Detecta desconto de forma estável (preço do produto muda). `unit_price < list_price` ⇒ item com desconto.
3. **Página pública** (`FRONTEND`, rota fora do `DashboardLayout`, sem `requiresAuth`): mostra itens, quantidades, total e o estado de pagamento; o cliente pode **mudar a quantidade** de itens existentes (**0 = remover**). **Escopo desta fase:** só itens **já no pedido** — o cliente **não** adiciona produtos novos do catálogo (expor catálogo+estoque+preço a um anônimo é superfície grande; fica como **follow-up** com decisão do dono). "Editar" = ajustar/remover.
4. **Re-análise de desconto = revisão do operador, não recálculo automático** (não há motor de regras de desconto). Quando o cliente mexe num item **com desconto** (`unit_price < list_price`), o pedido ganha `needs_price_review=1` e o **pagamento fica bloqueado** até o operador re-analisar (`POST /manual-orders/{id}/price-review/approve`). É o **"falhar alto, nunca em silêncio"**: não deixamos um preço com desconto de volume valer num pedido reduzido sem um humano decidir. Mexer em item **sem desconto** apenas recalcula o total (comprar menos é permitido).
5. **Recálculo do total**: toda edição recomputa `sale_amount`/`product_cost` a partir dos itens (SSOT = itens). Edição é **bloqueada** quando o pedido já está pago ou há cobrança `CONFIRMED/RECEIVED` viva.
6. **Pagamento público reusa a Fase 2**: `POST /public/checkout/{token}/pay` chama o **ponto único** `services/charge_service` (mesmo caminho do endpoint autenticado) — resolve o Galpão pela CMIG do pedido (ADR-0026), reentrante. **Correção herdada da auditoria da Fase 2:** o valor da cobrança passa a ser `sale_amount + shipping_cost` (antes o frete ficava de fora — cliente sub-cobrado). Centralizado no `charge_service` para os dois caminhos.
7. **Estágios derivados** (sem coluna redundante que colida com `status`/`payment_status`): `pedido` (sem link/cobrança), `pagamento` (link gerado/cobrança viva), `pago` (`payment_status=paid`). Separação/Enviado/Entregue mapeiam para o `status` existente (`separated`/`shipped`) quando o dono retomar as fases 3-5.
8. **Segurança do endpoint público** (sem JWT): token inadivinhável e escopado; nenhuma informação sensível além do necessário (itens/total/estado); nunca expõe CPF completo nem dados de outros pedidos; mutação só via o token do próprio pedido; a criação de cobrança herda a resolução estrita de Galpão da Fase 2.

## Consequências
- **Verificação real** só com o dono: gerar link, o cliente abrir, ajustar item, disparar `price-review`, e pagar via ASAAS (depende de credencial ASAAS real + Fase 2 exercida).
- O flag `manual_sale_requires_payment` (Fase 1) passa a ter uso: quando ligado, o pedido não avança para separação sem `payment_status=paid` (enforcement no ponto de separação, que entra com as fases 3-5 adiadas).
- `charge_service` vira o ponto único de cobrança (o endpoint autenticado da Fase 2 é refatorado para usá-lo — fim da duplicação).

## Follow-ups
- Cliente **adicionar** produto novo do catálogo na página pública (precisa expor catálogo+estoque+regra de preço a anônimo — decisão do dono).
- Expiração/limite de tentativas do token; rate-limit no endpoint público.
- Enforcement de `manual_sale_requires_payment` no gate de separação (fases 3-5).

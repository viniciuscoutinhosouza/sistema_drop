# ADR-0037 — Cancelamento de venda direta: crédito do cliente + NF-e de devolução emitida

**Status:** Aceita (implementada — 2026-10-26; emissão SEFAZ da devolução a validar em homologação)
**Relaciona/emenda:** [ADR-0009](ADR-0009-devolucao-nfe-driven.md) (devolução NF-e-driven), [ADR-0015](ADR-0015-emissao-propria-nfe-sefaz.md)/[ADR-0028](ADR-0028-emissor-multiregime-fiscal-por-produto.md) (emissão própria), [ADR-0034](ADR-0034-credito-cmig-galpao-extrato.md) (crédito CMIG×Galpão), [ADR-0026](ADR-0026-papel-galpao-unificado.md) (escopo), [ADR-0036](ADR-0036-capacidade-nunca-se-amarra-em-escopo.md) (capacidade = permissão)

## Contexto

Duas necessidades do dono na **venda direta** (pedido `platform='manual'`):

1. **Etiqueta de envio não pode identificar o produto** — o transportador não pode saber o que está
   carregando. A etiqueta de venda direta trazia um bloco "PRODUTO" (nome, SKU, EAN + 2 códigos de
   barras).
2. **Botão para cancelar/reverter o pedido na tela do pedido**, com três consequências conforme o
   estado:
   - não pago e sem NF-e → cancelar;
   - já pago → gerar um **crédito ao cliente** para devolução futura do valor;
   - NF-e já emitida → oferecer **emitir a NF-e de devolução**.

Não existia: botão/endpoint de cancelamento com liberação de reserva; razão de crédito **por
cliente** (só havia `cmig_warehouse_credits` CMIG×Galpão, ADR-0034, e `ACProfile.balance` — conceitos
distintos); nem emissão (ao contrário da **importação**, ADR-0009) de NF-e de devolução.

## Decisão

### 1. Etiqueta sem identificação do produto
Remoção do bloco "PRODUTO" das etiquetas de **envio** de venda direta (PDF A4, PDF térmico, ZPL) em
`services/label_service.py`. O produto permanece **apenas** na etiqueta de **conferência interna** do
pedido ML (`ML_CONF_HEADER`), que fica no galpão e não acompanha a carga.

### 2. Cancelamento (soft) — `POST /orders/{id}/cancel`
Só venda direta. **Soft-cancel** (`status='cancelled'`, preserva histórico — âncora de crédito e
devolução). Capacidade por **permissão de ação** `pedido_cancelar` (ADR-0036) + **escopo** de dados
(AC vê os seus; galpão por `warehouse_id`; admin tudo). Fluxo:
- **Com NF-e autorizada** → `409 {code:"requires_devolution"}`: **nunca** cancela em silêncio uma
  venda fiscal — o front oferece emitir a devolução ("falhar alto").
- **Sem NF-e, não despachado** → libera a reserva (`release_reservation`, idempotente por
  `StockMovement`), cancela cobranças ASAAS vivas não-pagas (`charge_service.cancel_open_charges`),
  e (se **pago**) gera **crédito ao cliente** = `charge_value` (venda+frete) **idempotente por
  `order_id`**. Marca `cancelled`.
- **Guardas (fail-loud):** FULL fora deste fluxo (ADR-0022); DC-e emitida (CPF) ainda não suportada;
  despachado → "registre uma devolução"; pago sem cliente vinculado → bloqueia (exige `person`).

### 3. Crédito do cliente — razão append-only (NOVO)
`customer_credits` (migration 163): `(cmig_id, person_id, entry_type credit|debit, amount, order_id,
description, created_by)`. Saldo = Σcred − Σdéb por `(cmig_id, person_id)`. **Terceiro razão** do
sistema (distinto de `cmig_warehouse_credits`/ADR-0034 e de `ACProfile.balance`): é o **passivo com o
comprador**. `services/customer_credit_service` (ponto único, espelha `credit_service`); endpoints
`GET/POST /api/v1/customer-credits` escopados por `assert_cmig_access` (ADR-0026); POST exige
`credito_cliente_gerenciar` (ADR-0036). Append-only (sem update/delete). Gerado no cancelamento de
pedido pago; **baixado** (`debit`) quando o operador devolve o valor ou abate numa compra.

### 4. NF-e de devolução EMITIDA — `POST /orders/{id}/devolution-nfe`
Cria o **rascunho** de uma NF-e de **entrada** de devolução de venda, espelhando os itens da nota de
saída original (snapshot fiscal — ADR-0028) com **CFOP de entrada 1202/2202** (devolução de venda que
*nós* emitimos para receber de volta do consumidor não-contribuinte; **não** é o 5202/6202 de
`suggest_cfop`, que é devolução de compra), `finalidade=4` (via `purpose='devolucao'` → `tpNF=0`) e
**`refNFe`** = chave da nota original. O operador revisa e transmite pelo fluxo existente
(`POST /invoices/{id}/transmit`). Capacidade: `nfe_gerenciar` (reusada).

Para o `refNFe` entrar no XML, a `Invoice` ganhou `referenced_access_key` (migration 165) e
`sefaz_service.build_nota_emissao` passa `chave_referenciada` quando `finalidade==4`.

### Invariante de estoque (crítico — ADR-0004/0009)
A NF-e de devolução nasce **`stock_updated=False`** e `_apply_stock_movement` ganhou um **guard**:
`purpose=='devolucao'` é **inerte ao replay** de estoque. O retorno ao estoque vendável passa por
**uma única fonte canônica**: a **inspeção** (apto/não-apto) da ADR-0009 — **nunca** pela nota. Sem
isso haveria **dupla-contagem** (o replay credita toda NF-e de entrada `stock_updated=True`, e a
inspeção creditaria de novo). Na emissão: se o pedido **não** foi despachado, a mercadoria nunca saiu
(só reserva) → libera a reserva; se foi despachado, o retorno físico passa pela inspeção.

## Consequências
- **Positivas:** transportador não vê o conteúdo; cancelamento seguro com liberação de reserva e
  estorno de cobrança; passivo com o cliente rastreável (razão append-only); devolução fiscal própria
  reutilizando o emissor SEFAZ, sem dupla-baixa de estoque.
- **Custos/limites:** a **transmissão SEFAZ da devolução** (CFOP 1202/2202, emitente×destinatário,
  tPag=90) precisa de validação com a contabilidade **em homologação** antes de produção ("você
  orienta, o contador assina"). Para **conta CPF (DC-e)** o cancelamento fiscal ainda não é suportado
  (bloqueado, fail-loud). O crédito do cliente exige `buyer_person_id` vinculado.

## Follow-ups
- Após a devolução **autorizada**, fechar o ciclo de inspeção automaticamente (criar o `Return` em
  `awaiting_validation` a partir da emissão) e, quando validado, baixar o pedido para `cancelled`.
- Baixa automática do crédito do cliente ao abater numa nova compra.
- Cancelamento fiscal de DC-e (CPF) — hoje bloqueado.
- UI de extrato do crédito do cliente (há GET/POST; falta tela dedicada).

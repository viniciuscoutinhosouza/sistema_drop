# Memória de Trabalho — Sistema Drop

> Registro de continuidade entre os locais de trabalho do dono (**CASA**, **ESCOL**, **NOTEBOOK**).
> Mantém apenas os **últimos 5 dias** de trabalho. Cada tarefa concluída vira uma entrada com local, data/hora e o resumo entregue.
> **Entrada mais recente no topo** — ao baixar o projeto do GitHub, a Claude apresenta a primeira entrada abaixo.

---

## 2026-10-31 — CASA — Endereçamento Fase 2.5: Débito do endereço ao despachar (ADR-0039) — ✅ EM PRODUÇÃO (commit `5d70a5b`)

> **Deploy feito em 2026-11-01:** fast-forward `f750a05..5d70a5b`; **migration 175** aplicada (5 blocos/0
> erro, idempotente; `product_allocation_movements` criada, COUNT=0); PM2 online sem erro; build do front
> OK; `/docs` e domínio 200; rota `/api/v1/storage/allocation-movements` no OpenAPI. Zero-regressão (tabela
> nasce vazia; hooks só agem em pedidos despachados após o deploy).

**O que:** a SUGESTÃO da Fase 2 virou MOVIMENTO. Ao DESPACHAR (entrega da gaiola → `confirm_dispatch`,
mesmo gatilho do saldo escalar) o endereço físico é **debitado**; no RETORNO ao vendável, **creditado**
de volta. **Nunca grava saldo escalar** (ADR-0004 intocado) — só move `product_allocations.qty_units`
e loga em `product_allocation_movements` (migration 175).

**Entregue:**
- `services/storage_debit_service.py` (ponto único): `debit_order_addresses` (staged — o
  `confirm_dispatch` commita; idempotente por `(order_id,'dispatch')`; atômico plan/apply; best-effort,
  nunca derruba o despacho) debita na ordem do picking (reusa `storage_picking.order_allocations`),
  **preservando a variante vendida**, expandindo **kit→componentes**, consumindo **solta antes de abrir
  caixa** (+desativa `StorageBoxLabel`). `credit_order_addresses` devolve a qtd REAL por produto, **só
  no ramo aprovado**, idempotente por `return_id`, sem super-creditar (teto = debitado − devolvido).
- 3 hooks em `stock_reservation_service.py` (`confirm_dispatch` débito; `confirm_pending_return` e
  `validate_return`/`validate_return_items` crédito). Extrato `GET /storage/allocation-movements`.
- Migration 175 + `ProductAllocationMovement`. ADR-0039 (Status/Faseamento/Invariante) + emenda ADR-0005.

**Auditoria (trio):** ADR-checker APROVADO; consistency 0 crítico/alto (2 CRÍTICOS+4 ALTOS do plano
incorporados); quality 0 crítico/alto. 3 MÉDIOS corrigidos (qty_units negativo em over-débito
cross-target → acumulador por alocação; rollback que descartava estado do chamador → débito virou
staged sem rollback; `validate_return` não-NF-e passou a creditar o endereço). Follow-up documentado:
retorno de KIT não credita componentes (espelha o escalar) + reconcile-fix admin. Verificado: pytest
**345 ok** (2 pré-existentes em test_orders).

**Deploy PENDENTE do dono:** rodar **migration 175** em produção + deploy do backend. Sem migration o
endpoint/hook não funcionam. Não deployado ainda.

---

## 2026-10-31 — CASA — Endereçamento Fase 2: Picking por endereço (ADR-0039) — ✅ EM PRODUÇÃO (commit `f750a05`)

**O que:** a lista de separação e a bipagem do Carrinho Gaiola passam a dizer **onde pegar cada item
e em que ordem** — SUGESTÃO (não debita; débito fica p/ Fase 2.5, conforme decisão do dono).

**Entregue:**
- `services/storage_picking.py` (ponto único `pick_plan_for` + ordenação pura `order_allocations`):
  **FEFO → `pick_order` → caixa aberta → `pick_sequence` → `full_code`**. FEFO = mesmo ORDER BY do
  débito de lote (ADR-0027); alocação rastreável sem lote vai ao fim; inclui alocações de variante.
- Rotas de leitura escopadas: `GET /storage/products/{pt}/{id}/pick-plan` e
  `GET /separation/carts/{id}/pick-plan`. Coluna "Endereço (ordem)" no PDF + painel "Rota de picking"
  na bipagem (`SeparationView.vue`). `get_cart` intocado. Anotação blindada (try/except — nunca
  derruba a separação). **Sem migration** (só leitura).

**Auditoria (trio):** ADR aprovado; consistency 0 crítico/alto; quality 0 crítico/alto (1 MÉDIO de
blindagem corrigido). Verificado: pytest **336 ok**, build OK. ADR-0039 Fase 2 + emenda ADR-0005.

**Deploy (feito 2026-10-31):** commit `f750a05` em produção (`/home/ubuntu/app`, fast-forward
`01ac132..f750a05`); **sem migration** (Fase 2 é só leitura). PM2 `sistema-drop-backend` online sem
erro; `npm run build` OK (bundle novo `SeparationView-*.js`); `/docs` e domínio **200**; as 2 rotas
`pick-plan` (`/storage/products/{pt}/{id}/pick-plan` e `/separation/carts/{id}/pick-plan`) ativas no
OpenAPI. Follow-ups: Fase 2.5 (débito do endereço ao separar/despachar); Fase 3 (inventário por
endereço, transferência em massa, box tracking).

---

## 2026-10-30 23:59 — CASA — Endereçamento Físico de Estoque (Fase 1, ADR-0039) — ✅ EM PRODUÇÃO (31/10, commit `01ac132`)

> **Deploy feito em 2026-10-31:** migrations 173 (15 blocos/0 erro) e 174 (1 bloco/0 erro) aplicadas
> no Oracle; 5 tabelas + `product_eans.source` + 4 permissões (admin/go) confirmadas; PM2 online sem
> erro; bundle novo no nginx; `/docs` e domínio 200; rotas `/api/v1/storage` no OpenAPI. **Pendente do
> dono:** habilitar `endereco_configurar`/`endereco_movimentar` em perfis não-sistema (ex.:
> `go.harmonyexpress`) pela tela Perfil, se quiser que operadores específicos usem. Próximo: **Fase 2** (picking).


**Pedido:** estrutura para organizar fisicamente o galpão, com vários modelos (salas com
armários/estantes, porta-pallet com estante→coluna→altura→pallet, e misto), hierarquia do maior ao
menor, **identificação por ramo** (Sala Mickey estantes 1..8; Pateta 1..5; letras A..C ou A..F),
**caixas** homogêneas/heterogêneas (5×12, ou 3×10+4×8+1×20), produto em vários endereços com ordem
de picking, FEFO para rastreáveis, **etiqueta/QR nas caixas fechadas** e **código interno** p/
produto sem EAN. Usabilidade apresentada e aprovada; decisões: aditivo / Fase 1
(estrutura+alocação+mapa) / caixas padrão+livre. Picking (rota+FEFO) é Fase 2 — regra do dono:
esgotar caixa aberta primeiro, preservar fechada (facilita contagem).

**Entregue (camada ADITIVA — nada grava saldo; reconcilia com o escalar, balde "sem endereço"):**
- Migrations **173** (6 tabelas + `product_eans.source`) e **174** (seed permissões, zero-regressão).
- Backend: `models/storage.py`, `services/storage_service.py` (full_code+recompute subárvore, geração
  em massa por ramo, EAN-13 interno prefixo 2+DV único, reconciliação), `services/product_scope.py`,
  `routers/storage.py` (`/api/v1/storage`, 23 rotas), permissões `endereco_configurar`/`endereco_movimentar`.
- Frontend: `StorageAddressingView.vue` + `StorageNode.vue` recursivo, rota `estoque/enderecamento`,
  menu Estoque; QR/código de barras via CDN (sem dep no bundle).
- Escopo por galpão em toda resolução de id (anti-IDOR). ADR-0039 criada; prefixo no CLAUDE.md.

**Auditoria (trio):** ADR-checker APROVADO; consistency 1 CRÍTICO + 2 médios; quality 1 CRÍTICO
(XSS→roubo de token na impressão de etiqueta) + 2 ALTO + médios — **TODOS corrigidos**. Verificado:
pytest **327 ok** (2 pré-existentes), build OK.

**Pendente (decisão do dono):** rodar **migrations 173/174** + deploy (DEV não conecta no Oracle —
wallet ausente — então o caminho real só roda em produção). Nada commitado ainda.

---

## 2026-10-29 23:46 — ESCOL — Sincronização de produtos da nota (multi-EAN) + reconciliação de entrada

**Pedido:** na tela Compra/Entrada, um ícone que indique que a nota tem produtos não sincronizados;
clicar abre um modal para vincular o produto da nota a um já cadastrado (adicionando o EAN — produto
pode ter 1+ EANs — ou corrigindo), ou cadastrar produto novo.

**Entregue e em produção:**
- **Multi-EAN** (`product_eans`, migration 172, CMIG + PG) consultado nas 3 superfícies de casamento
  de estoque (detector + 2 do replay) — aditivo, zero-regressão (tabela nasce vazia).
- **Bug de ordem corrigido** em `update_stock_from_invoice`: marcava `stock_updated` DEPOIS do
  recompute, então a própria nota não entrava no seu replay e o saldo não creditava na hora. Agora
  marca ANTES (igual `_apply_stock_movement`). **Corrige a contabilização de qualquer nota casada.**
- **Endpoints** (routers/invoices.py, `require_permission estoque_movimentar` + `_check_cmig_access`):
  `GET /{id}/stock-match`, `POST /{id}/items/{item_id}/link-product` (add/replace EAN, seta FK,
  re-contabiliza), `POST .../create-product` (reusa create_cmig_product; PG no galpão da CMIG;
  bloqueia KIT), `GET /product-eans/list`, `DELETE /product-eans/{id}`. `list_invoices` expõe
  `has_unmatched_items`.
- **Frontend:** coluna Estoque com ícone 🔗 vermelho quando `has_unmatched_items` → abre
  `ProductSyncModal` (lista itens, busca produto, vincular/criar, contabilizar). Ícone 📦 laranja =
  pendente de contabilizar; ✓ verde = contabilizado.

**Auditoria (trio):** adr-checker APROVADO; quality-guardian reprovou com 2 CRITICAL + 4 HIGH, TODOS
corrigidos e re-verificados: (C1) recontabilização nunca dá 500 cru; (C2) `replace_product` preserva
o EAN antigo como adicional (não rouba histórico no replay); (HIGH) casamento/deleção de PG por EAN
escopados por galpão (anti-IDOR cross-galpão); link/create PG falham alto sem galpão; ADR-0027
(lotes) espelha multi-EAN.

**Verificado em produção:** 60 testes (stock/invoice/fiscal/trace) passando; fluxo real exercitado
(stock-match → vincular add/replace → credita, com limpeza); migration 172 aplicada; 5 rotas no
OpenAPI; site 200. **10 das últimas 30 entradas** têm produto não sincronizado (inclui a 13001).

**Correção de deploy:** `EntradasView.vue` + `fiscal.js` tinham ficado fora dos commits → o bundle
não tinha a feature. Commitados (`a3380ff`) e rebuildados; bundle agora contém o ícone/modal.

**Follow-up:** criar produto por aqui usa `estoque_movimentar`; quando o follow-up do ADR-0036
fechar uma permissão própria de "criar produto", alinhar. Dono: hard-refresh (Ctrl+Shift+R) p/
carregar o bundle novo.

---

## 2026-10-29 20:48 — CASA — NF-e do Pedido 13636 (ciclo completo) + pull do projeto

**Commit:** `de6e158` · **em produção**

Pedido já tinha NF-e emitida mas a tela continuava mostrando "NF-e Pendente" + botão "Gerar NFe a
partir do Pedido". Resolvido ponta a ponta:

1. **`<xPag>` no XML quando tPag=99** → corrige a Rejeição 441 da SEFAZ ("Descrição do pagamento
   obrigatória para meio de pagamento 99 - outros"). `xml_builder` emite `<xPag>` entre `<tPag>` e
   `<vPag>` só quando forma=99; `sefaz_service` manda "Pago no marketplace".
2. **Botão "Retransmitir à SEFAZ"** na nota rejeitada (`InvoiceDetailView.vue`) — a lacuna de UI que
   impedia o dono de reautorizar.
3. **Sincronização do pedido no `transmit`** (best-effort) + **migration 171** de backfill (MERGE)
   para pedidos que já estavam presos nesse estado.
4. **`GET /orders/{id}` passou a devolver `invoice_id`** — a serialização do detalhe omitia o campo,
   então o `v-if="order.invoice_id"` era sempre falso e o botão não alternava para "Ver NFe vinculada".

Verificado em produção: commit no servidor, `/docs` 200, nginx 200, logs limpos.

---

# Memória de Trabalho — Sistema Drop

> Registro de continuidade entre os locais de trabalho do dono (**CASA**, **ESCOL**, **NOTEBOOK**).
> Mantém apenas os **últimos 5 dias** de trabalho. Cada tarefa concluída vira uma entrada com local, data/hora e o resumo entregue.
> **Entrada mais recente no topo** — ao baixar o projeto do GitHub, a Claude apresenta a primeira entrada abaixo.

---

## 2026-11-04 22:20 — CASA — Fix: telas travando em "carregando" (deadlock no refresh do token) — ✅ EM PRODUÇÃO (commit `d53a478`)

**Relato do dono:** dashboard, dashboard Marketplace e outras telas ficavam só "carregando", não atualizavam.

**Diagnóstico (NÃO era o servidor travado):** backend saudável e respondendo rápido; o `/auth/refresh`
inclusive respondeu 200 de outro IP. O IP do dono (CASA) tomava **401 em tudo**, inclusive no
`POST /auth/refresh`. Causa imediata: o **refresh token da sessão CASA venceu** (7 dias parado — o dono
vinha trabalhando da ESCOL). Causa do "trava" (em vez de ir pro login): **deadlock no interceptor Axios**.

**Bug (causa-raiz):** o refresh era feito pela instância `api` (que tem o interceptor de 401). Quando o
refresh respondia 401, o PRÓPRIO interceptor interceptava esse 401 e, com `refreshing===true`, enfileirava
o refresh em vez de deixar o erro subir → o `await` nunca lançava → o `catch` (removeItem + redirect
`/login`) nunca rodava → tela carregando pra sempre. Cada F5 do dono reiniciava e re-travava (por isso
vários `auth/refresh 401` no log).

**Fix (EM PRODUÇÃO — commit `d53a478`, só frontend):** o refresh passa a usar **axios PURO** (sem
interceptor), URL completa `/api/v1/auth/refresh`, em `composables/useApi.js` E no gêmeo
`stores/auth.js::doRefresh` (estava exportado sem chamador — armadilha pronta). Rede de segurança: guard
no interceptor que desloga direto se um 401 vier do próprio `/auth/refresh`. Pré-audit (consistency-auditor)
aprovou + exigiu o fix do gêmeo (incorporado). Verificado: `npm run build` OK; deploy em produção
(fast-forward `5cbf46b..d53a478`, bundle novo `index-a4b2e161.js` servido pelo nginx, domínio 200,
backend intacto sem restart). **Follow-up (não bloqueante):** unificar refresh/logout numa fonte única;
o interceptor atualizar o estado reativo do Pinia (hoje só o localStorage).

---

## 2026-11-04 20:25 — ESCOL — Fix: Separar Pedidos não mostrava nenhum pedido (ML) + modal de ajuda

**Pedido do dono:** em Logística > Separar Pedidos não aparecia nenhum pedido; e criar um "?" explicando
a Logística.

**Causa:** o filtro de elegibilidade (`_eligibility_conditions`) exigia `Order.payment_status=='paid'`
para TODOS os pedidos (regra "só PAGOS" que o dono pediu). Mas o pedido do **Mercado Livre** já é pago
**no marketplace** e chega com `payment_status='pending'` no nosso banco (o sync ML não carimba 'paid') —
então o filtro escondia **todos os 48 pedidos ML** (40 coletado + 5 flex + 3 correios).

**Fix (EM PRODUÇÃO — commit `5cbf46b`):** a regra "pago" passa a valer só para venda **manual** (não
separar antes de o cliente pagar); pedido ML **dispensa** `payment_status='paid'`. Também criei
`SeparationHelpModal.vue` (botão "?" no cabeçalho) explicando o fluxo (gaiola → separar → NF-e → etiqueta
→ despacho), quais pedidos aparecem (pago/não-FULL/não-Shopee/não-despachado/fora de gaiola/do galpão) e
o "não aparece nenhum?". **Verificado em produção:** código deployado roda `_eligibility_conditions` →
**48 pedidos elegíveis** (antes: 0); backend restart health 200; build front OK (SeparationView novo).

---

## 2026-11-04 20:04 — ESCOL — Ajustes do Endereçamento (etiquetas + alocação zerada)

Três ajustes sobre a feature de etiquetas (todos EM PRODUÇÃO):
1. **Remover confirmação ao gerar etiqueta** (commit `88e893f`): o dono não quer o `confirm()` — removido do
   lote e do botão individual.
2. **Etiqueta de endereço no tamanho selecionado + lote** (commit `a965bb0`): a etiqueta de endereço
   (ícone tag) passa a usar o tamanho (100×50/100×150); novo botão **"Etiquetas de endereço"** na barra
   gera a etiqueta de TODOS os endereços marcados (qualquer nó) numa página só. A barra tem os 2 lotes.
3. **Alocação zerada sai do endereço** (commit `3a7fa90`): ao mover a caixa, a qtd zerou mas o produto
   continuava no endereço (0). `location_contents` e `product_allocations` passam a filtrar `qty_units>0`
   — o registro fica ATIVO em 0 no banco (reuso ao re-endereçar + FK do ledger `ProductAllocationMovement`;
   convenção Fase 3b não envenena o slot da UNIQUE), só não aparece mais. Verificado: location 99 banco
   `qty=0` mas `location_contents` exibe 0 alocações; 29 testes storage ok; health 200.

---

## 2026-11-04 19:41 — ESCOL — Etiquetas de caixa em LOTE + tamanho (100×50/100×150) + Rótulo

**Pedido do dono:** checkbox em cada endereço; emitir as etiquetas das caixas de todos os marcados numa
página só; imprimir o Rótulo na etiqueta; opção de tamanho 100×50mm ou 100×150mm.

**Feito (EM PRODUÇÃO — commit `46937f2`):**
- **Backend:** ponto único `storage_box_service.recreate_box_labels` ("emitir = recriar": desativa as
  ativas → consumed, cria 1 por caixa dos packs, carimba o RÓTULO pelo pack de origem; invariante Fase
  3c). Single refatorado p/ reusar. Novo `POST /storage/box-labels/print-batch` (require_permission
  endereco_movimentar): valida CADA endereço por escopo, expande SUBTREE, dedup por alocação, teto 500
  **pré-checado antes de recriar**, devolve lista plana {token,units_per_box,rotulo,sku,title,location}.
- **Frontend:** checkbox por nó na árvore (gated endereco_movimentar), barra com seletor de tamanho
  (100×50 / 100×150) + botão "Emitir (N)" (com confirmação — é destrutivo, substitui QR antigos).
  `printLabels` ganhou `opts.size` (@page só quando size; retrocompatível) + renderiza Rótulo+endereço.
  Single de caixa também passa rótulo+tamanho.
- **Auditoria (trio):** adr OK (ADR-0039 Fase 3c.1 documentada); quality 0 CRITICAL, **2 HIGH corrigidos**
  (pré-check de volume; confirmação no lote) + skip defensivo upb<=0.
- **Verificado em produção:** 21 testes storage ok; print-batch exercitado (location 99 → 1 etiqueta com
  rótulo "Barra de Porta Cromada", sku 5267, endereço "A / 1 / 01"); build front OK; site 200.

---

## 2026-11-04 19:11 — ESCOL — Fix: "Endereçar produto" não achava por SKU

**Pedido do dono:** no modal "Endereçar produto", digitar um SKU não encontrava o produto.

**Causa:** `GET /storage/scan/{code}` resolvia produto só por **EAN / código interno**
(`catalog_product_id_by_ean` + `CMIGProduct.ean` + `product_eans`) — não buscava por SKU.

**Fix (EM PRODUÇÃO — commit `f31c51c`):** fallback por **SKU** no scan — PG por `CatalogProduct.sku`
(escopado por galpão) e CMIG por `CMIGProduct.sku_cmig` (escopado pelas CMIGs acessíveis),
**case-insensitive**. Rótulo/placeholder do campo e o modal de ajuda passam a dizer "EAN, SKU ou
código interno". Verificado em produção: SKU exato e minúsculo resolvem o produto. Backend restart
health 200, build front OK, site 200. (ruff organizou imports pré-existentes do storage.py.)

---

## 2026-11-04 15:05 — ESCOL — Modal de ajuda "?" no "Endereçar produto" (campos + como vira estoque)

**Pedido do dono:** um "?" no modal "Endereçar produto" explicando a tela, os campos e como o
endereçamento se comporta como estoque dos produtos.

**Feito (frontend, EM PRODUÇÃO — commit `f6025a5`):** botão **?** no cabeçalho do modal → abre
`StorageAllocHelpModal.vue` (novo). Explica: para que serve; cada campo (Localizar produto/EAN/código
interno, Quantidade, Ordem de picking, Lote-rastreável, Composição de caixas = caixas×un/caixa);
e **o ponto-chave** — o endereçamento é camada de LOCALIZAÇÃO: **não altera o saldo** (que vem das
NF-e/pedidos); Σ endereços + "Sem endereço" = saldo (aba Mapa & Reconciliação); transferência é soma
zero; picking FEFO→ordem→caixa; débito do endereço ao despachar e crédito no retorno; inventário por
endereço corrige ONDE está, não o contábil. Ilustrado com diagrama SVG (saldo = endereços + sem-endereço)
+ exemplo de composição de caixas (3×10+1×5=35). Build OK, bundle novo, site 200.

**Follow-up (15:20, commit `c1d688d`):** o dono perguntou pra que serve o campo **"Rótulo"** — adicionei
a explicação no modal: é o nome opcional do tipo de caixa (ex.: Caixa master/Display/Fardo de 10),
aparece na etiqueta e vira embalagem-padrão reutilizável do produto; não altera a quantidade.

---

## 2026-11-04 14:48 — ESCOL — Campo da geração em massa vira "Qtd. dígitos" (Endereçamento)

**Pedido do dono:** o campo numérico de preenchimento (antes "Zeros à esq.") deve se chamar
**"Qtd. dígitos"** e usar largura total: 1 → 1,2,3…; 2 → 01,02,03…

**Feito (EM PRODUÇÃO — commit `a124b91`):** `storage_service.generate_bulk_codes` usa `zfill(pad)`
(largura total) e o rótulo do formulário + o modal de ajuda passam a dizer **"Qtd. dígitos"**
(exemplo 1/8/2 → 01..08). (Revertida a tentativa anterior de interpretar como "zeros à esquerda".)
Testes ajustados (pytest 2 ok), backend restart health 200, build front OK, site 200.

**Pendente do dono:** a "Coluna" criada antes com 1 dígito pode ser corrigida apagando e gerando de
novo com **Qtd. dígitos = 2**, ou editando a Identificação na mão (1→01).

---

## 2026-11-04 13:49 — ESCOL — Modal de ajuda "?" na Árvore de Endereçamento

**Pedido do dono:** em Estoque > Endereçamento > Árvore de Endereço, um botão "?" que abre um modal
explicando como funciona a árvore e para que serve cada campo, com imagens.

**Feito (frontend, EM PRODUÇÃO — commit `0041dfd`):** botão **?** no cabeçalho do card "Árvore de
endereços" → abre `StorageHelpModal.vue` (novo componente). Conteúdo ilustrado (SVG + mockups, sem
arquivos externos): para que serve; hierarquia maior→menor (diagrama Área→Estante→Coluna→Altura→
Pallet/Caixa); código completo (ex. MICKEY-E01-A-3); tabela explicando cada campo (Tipo de nível,
Identificação, Tipo de área, Armazenável, Sequência de picking); Gerar em massa (exemplo faixa
numérica → Estante 01..08); e 2 exemplos de montagem (sala com estantes / porta-pallet). Build OK,
bundle novo, site 200.

---

## 2026-11-04 13:29 — ESCOL — Desligar mensageria do ASAAS (notificações cobradas) nos clientes

**Pedido do dono:** desligar o serviço de mensageria nos clientes do ASAAS (existentes) e em todos os
clientes que forem cadastrados.

**Contexto:** ao criar cobrança, `asaas_service.upsert_customer` criava o cliente no ASAAS SEM
`notificationDisabled` → o ASAAS mandava notificações (e-mail/SMS, que podem ser cobradas).

**Feito:**
- **Código (EM PRODUÇÃO, commit `7721036`):** `upsert_customer` cria o cliente ASAAS com
  `notificationDisabled: true` e, ao reencontrar um cliente existente com notificação ligada, desliga
  (best-effort, nunca derruba a cobrança). Backend reiniciado, health 200.
- **One-off (produção):** desliguei via API as notificações de TODOS os clientes ASAAS das 2 contas
  (warehouses 1 e 22): banco 1 = 14 desligados; banco 21 = 14 já estavam desligados (mesma conta).
  Verificado: **0 clientes com notificação ligada**.

**Default novos clientes:** nascem com `notificationDisabled: true`. Registrado como instrução
permanente (junto com a IA de atendimento desligada em 13:05).

---

## 2026-11-04 13:05 — ESCOL — Desabilitar mensageria/IA (envio de mensagem cobrado) para todos os clientes

**Pedido do dono:** desabilitar a mensageria/envio de mensagem em todos os clientes (serviço cobrado,
não usa) e cadastrar novos clientes sem envio habilitado.

**Diagnóstico (produção):** o envio automático/cobrado é a **IA de atendimento**. Estado: `ai_configs.is_active=1`
(IA global LIGADA — OpenAI gpt-4o-mini) e `cmig_ai_configs` com **0 registros** (nenhum cliente com
auto-resposta; default já é off). O auto-envio só ocorre se `is_active` **E** `auto_respond` (ambos) —
então não havia auto-envio por cliente, mas a IA global ligada cobra quando usada (sugestão/auto-resposta).

**Feito (produção, data-only — sem código):** `UPDATE ai_configs SET is_active=0` (desliga a IA global:
fim do auto-envio e da sugestão IA = fim da cobrança OpenAI) + `UPDATE cmig_ai_configs SET auto_respond=0`
(belt-and-suspenders; já era 0). Verificado: is_active=0, 0 auto_respond ligados.

**Default novos clientes:** já nascem OFF (`CMIGAIConfig.auto_respond` default `False`, criado sob demanda;
nenhum caminho liga). Registrado como instrução permanente: **nunca religar** `is_active`/`auto_respond`
sem o dono pedir.

**Ainda disponível (grátis, não mexido):** resposta MANUAL do operador na Central de Atendimento e o job
de sync (ver mensagens recebidas, 15 min). Se quiser parar o sync também, é só pedir.

---

## 2026-11-03 20:05 — ESCOL — Fix: botão "Área/Raiz" sumia no Endereçamento (admin sem galpão)

**Pedido do dono:** em Estoque > Endereçamento não conseguia criar a árvore — não tinha o botão de adicionar.

**Causa:** para **admin**, ao abrir a tela o galpão não era auto-selecionado (o backend exige escolher),
então `warehouseId` ficava nulo e a aba Estrutura INTEIRA (com os botões **Área/Raiz** e **Gerar em
massa**) ficava escondida atrás de "Selecione um galpão para começar" (`v-if="isAdmin && !warehouseId"`
vs `v-else-if` da aba). Perfis `admin` e `go` já têm `endereco_configurar` (seed migration 174); só o
perfil `gc` (ac) não tem.

**Fix (frontend, EM PRODUÇÃO — commit `6229c1f`):** admin passa a **auto-selecionar o 1º galpão** no
`onMounted` (`StorageAddressingView.vue`) → árvore + botões aparecem na hora; o seletor do topo continua
trocando. Build OK, site 200.

**Se ainda não aparecer:** (1) logado como conta/gestor (perfil `gc`/ac) → esse perfil não tem
`endereco_configurar`; habilitar em Perfil de Acesso ou usar admin/go. (2) Sessão antiga (login antes de
31/10, quando a permissão foi seedada) → logout+login resolve.

---

## 2026-11-03 — CASA — Endereçamento Fase 3c: Rastreio por caixa física (ADR-0039) — ✅ EM PRODUÇÃO (commit `564adac`)

**O que:** a etiqueta/QR (já uma caixa física) ganha CICLO DE VIDA ('closed'|'open'|'consumed') e vira
unidade MOVÍVEL de endereço. Camada ADITIVA: a caixa carrega N unidades JÁ contadas no `qty_units` do
endereço → **nunca grava saldo escalar** (ADR-0004) nem lotes (ADR-0027). Mover caixa é net-zero.

**Entregue:**
- **Migration 178**: `storage_box_labels` += `status` (invariante `is_active==(status=='closed')`; backfill
  `is_active=0→consumed`), `moved_at`/`moved_by`, CHECK, índice. Sem coluna de saldo, sem `location_id`,
  **sem 6º reason** (reusa `transfer_out`/`transfer_in` da 177).
- `services/storage_box_service.py` (ponto único): `move_box` (caixa FECHADA muda de endereço do mesmo
  galpão com o MESMO token; credita destino como CAIXA/pack — não solto → resolve o follow-up da 3b;
  debita origem tratando caixa defasada fail-loud; origem zerada fica ativa; ledger net-zero; 409 em
  corrida) + `open_box` (closed→open, soltas no MESMO endereço, qty inalterado, sem ledger).
- `storage_service.py`: `box_labels_to_close` virou o ESCRITOR do estado (is_active+status juntos);
  novo `log_allocation_move`. Rotas `POST /storage/box-labels/{id}/move|open`, `GET /storage/boxes` (mapa
  fail-closed), `/scan` enriquecido (localizar por QR). Front: aba **Caixas** (registro + Localizar +
  Mover/Abrir).

**Auditoria (trio):** ADR aprovado; consistency 0 bloqueador; quality 0 CRÍTICO, **1 HIGH corrigido**
(`/boxes` vazava cross-galpão p/ não-global sem galpão → trocado por `_resolve_wh` fail-closed). Riscos
conhecidos (perfil das 3b): lost-update em move concorrente; backfill 'open'→'consumed' cosmético.
Verificado: pytest **369 ok** (2 pré-existentes), build front OK. 10 testes novos.

**Deploy feito em 2026-11-03 (CASA):** fast-forward `e08997a..564adac` (11 arquivos); **migration 178**
aplicada antes do restart (`run_migration.py`, 6 blocos/0 erro, idempotente; `STORAGE_BOX_LABELS` ganhou
`STATUS NOT NULL`/`MOVED_AT`/`MOVED_BY` — tabela vazia, backfill sem alvo); `npm run build` OK; PM2
`sistema-drop-backend` online sem traceback/ImportError; `/docs` e domínio público **200**; rotas
`/api/v1/storage/boxes`, `/api/v1/storage/box-labels/{id}/move` e `/open` no OpenAPI. **Fase 3 do
Endereçamento FECHADA por completo** (1, 2, 2.5, 3a, 3b, 3c). Pendente só exercício funcional real das
rotas de caixa quando o dono criar a 1ª etiqueta (`storage_box_labels` vazia hoje).

---

## 2026-11-01 — CASA — Endereçamento Fase 3b: Transferência entre endereços (ADR-0039) — ✅ EM PRODUÇÃO (commit `e08997a`)

> **Deploy feito em 2026-11-03 (CASA):** fast-forward `0e4978e..e08997a` (10 arquivos, +523/-22);
> **migration 177** aplicada (`run_migration.py`, 2 blocos/0 erro, idempotente; constraint
> `CK_PALLOC_MOV_REASON` confirmada no Oracle = `('dispatch','return','adjust','transfer_out','transfer_in')`
> — superset do antigo, zero-regressão); `npm run build` OK; PM2 `sistema-drop-backend` online sem
> traceback/ImportError; `/docs` e domínio público **200**; rotas `/api/v1/storage/transfer` e
> `/api/v1/storage/locations/{loc_id}/transfer-all` no OpenAPI. Follow-up restante da Fase 3: **box
> tracking** (rastreio por caixa física).

**O que:** move estoque de um endereço para outro **no mesmo galpão**. Interno: muda só o local, Σ
`qty_units` do produto **não muda** → **nunca toca o saldo escalar** (ADR-0004) nem lotes. Loga
`transfer_out`(−N) + `transfer_in`(+N) = net-zero.

**Entregue:**
- **Migration 177**: CHECK `reason` += `transfer_out`/`transfer_in` (5 valores).
- `services/storage_transfer_service.py` (ponto único): `transfer_quantity` (atômico, fail-loud, 409 em
  corrida) + `transfer_location_all` (esvaziar endereço, all-or-nothing). Dois caminhos exclusivos:
  **reassign** (move total p/ destino vazio → só `location_id`, preserva caixas) × **geral** (parcial/merge
  → debita origem via `_plan_pack_open`+`box_labels_to_close`, credita solto no destino; origem zerada fica
  ativa em 0 (convenção do débito, não envenena o slot da UNIQUE; sem hard-delete). Trava mesmo-galpão (admin);
  `lot_id` preservado; `base_product_*` via `resolve_base_product`.
- `routers/storage.py`: `POST /storage/transfer`, `POST /storage/locations/{id}/transfer-all`;
  `move_allocation` delega (ganhou ledger + merge); regex `reason` do extrato → 5 valores.
- Front: botão **Transferir** por alocação (qty + destino) + **Esvaziar para…** no nó.

**Auditoria do plano (trio):** ADR aprovado c/ ressalvas; consistency C1 (invariante) + ALTOS — TODOS
incorporados (caminhos exclusivos, regex, snapshot do local, etiquetas, contrato do move, trava
mesmo-galpão). Trio sobre a implementação: ADR aprovado (0 bloqueador); consistency C1+ALTOS
resolvidos (1 MÉDIO = teste net-zero adicionado); quality 0 crítico, **1 HIGH corrigido** (slot
envenenado — origem zerada agora fica `is_active=True`, alinhada ao débito da Fase 2.5). Verificado:
pytest **359 ok** (2 pré-existentes), build front OK.

---

## 2026-11-01 — CASA — Endereçamento Fase 3a: Inventário por endereço (ADR-0039) — ✅ EM PRODUÇÃO (commit `0e4978e`)

> **Deploy feito em 2026-11-01:** fast-forward `5d70a5b..0e4978e`; **migration 176** aplicada (4 blocos/0
> erro, idempotente; CHECK `ck_palloc_mov_reason` = `('dispatch','return','adjust')`; colunas
> `last_counted_at/by` em `storage_locations` confirmadas); PM2 online sem erro; build front OK
> (`StorageAddressingView-*.js` novo); `/docs` e domínio 200; rotas `/storage/locations/{id}/count` e
> `/storage/inventory/to-count` no OpenAPI. Smoke funcional (bipar contagem logado) a exercitar na tela.

**O que:** o operador conta fisicamente um endereço e o sistema ajusta `product_allocations.qty_units`
para bater com o contado (movimento `reason='adjust'`). Corrige **ONDE** o estoque está — **nunca o
saldo escalar** (ADR-0004) nem `product_lots` (ADR-0027). Inventário de endereço ≠ inventário contábil:
a divergência aparece (flag **`over`** = endereçado > saldo = físico lançado além do contábil).

**Entregue:**
- **Migration 176**: CHECK `reason` += `'adjust'`; `storage_locations` += `last_counted_at/by`.
- `services/storage_inventory_service.py` (ponto único): `apply_count` fail-loud, atômico, bloqueia kit,
  conta por `(produto, lot_id)` com SEM-LOTE, cria alocação p/ produto achado (upsert anti-corrida
  `.is_(None)`+409), pula `delta=0`, abre caixa reusando `_plan_pack_open` + desativa `StorageBoxLabel`
  pelo helper **compartilhado** com o débito; devolve divergência pós-contagem (contábil × endereçado).
- `storage_service.py`: `resolve_base_product` + `box_labels_to_close`. Débito (Fase 2.5) refatorado p/
  usar o helper. Rotas: `POST /storage/locations/{id}/count`, `GET /storage/inventory/to-count`, filtro
  `reason`/`location_id` no `/allocation-movements`. Front: aba **Inventário** (lista a contar + painel de
  contagem + adicionar produto + resultado destacando `over` + ajustes recentes).

**Auditoria do plano (trio):** ADR aprovado c/ ressalvas; consistency/ADR 0 bloqueador — ALTOS
incorporados (divergência visível/`over`, desativar etiqueta no decréscimo via helper único, upsert
anti-corrida, `resolve_base_product`). Verificado: pytest **345 ok** (2 pré-existentes), build front OK.
Trio sobre a implementação em curso.

**Deploy PENDENTE do dono:** rodar **migration 176** em produção + deploy. Não deployado ainda.

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

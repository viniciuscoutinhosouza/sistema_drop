# ADR-0039 — Endereçamento Físico de Estoque como sub-ledger aditivo de localização

## Status
Aceita — Fase 1 em produção (2026-10-31, commit `01ac132`); Fase 2 (sugestão de picking) em produção
(2026-10-31, commit `f750a05`); Fase 2.5 (débito do endereço ao despachar) em produção (2026-11-01,
commit `5d70a5b` + migration 175); Fase 3a (inventário por endereço) em produção (2026-11-01, commit
`0e4978e` + migration 176); Fase 3b (transferência entre endereços) implementada (2026-11-01).

## Contexto
O galpão precisa organizar fisicamente onde cada produto fica. Há **vários modelos** de galpão:
salas com armários/estantes, estruturas de porta-pallet (estante → coluna → altura → pallet), e
galpões **mistos**. Existe uma **hierarquia do maior ao menor espaço**, e a identificação de cada
nível é **definida por ramo** (a Sala "Mickey" tem estantes 1..8; a "Pateta", 1..5; umas por letra
A..C, outras A..F). Produtos ficam em **caixas** homogêneas (5×12) ou heterogêneas (3×10 + 4×8 +
1×20), e podem ocupar **mais de um endereço** (com ordem de picking). Rastreáveis (lote/validade)
precisam ser agrupados/ordenados por FEFO no picking.

O estoque já é **escalar event-sourced** (ADR-0004) e os lotes são um **sub-ledger paralelo aditivo**
(ADR-0027). O risco de uma camada de localização é virar uma **segunda verdade** de saldo que diverge
do SSOT e quebrar estoque/fiscal.

## Decisão
Endereçamento como **camada ADITIVA de LOCALIZAÇÃO** — diz **ONDE** o estoque está, **reconcilia**
com o saldo escalar e **NUNCA grava saldo** (mesmo espírito do SEM-LOTE da ADR-0027).

### Modelo
- **Árvore de endereços** (`storage_locations`) por galpão: um só conceito cobre todos os modelos.
  `level_type` é **texto livre por nó** (Sala/Armário/Estante/Coluna/Altura/Pallet…), `code` é a
  identificação (nome/número/letra), `full_code` é derivado (caminho) e **recomputado na subárvore**
  quando um pai é renomeado. `is_storable` marca a folha que recebe produto. `area_kind`
  (pallet|cabinet|other) só na raiz da área → galpão misto = dois ramos. `pick_sequence` = rota.
  UNIQUE `(warehouse_id, full_code)`.
- **Alocação** (`product_allocations`): produto (±`lot_id`) num local, com `qty_units` e `pick_order`
  (ordem entre locais do mesmo produto). `product_type` = enum de stock_movements/traceability
  (`pg|cmig|variant_pg|variant_cmig`). UNIQUE `(location, product, NVL(lot,0))`.
- **Caixas** (`product_allocation_packs`): composição por alocação (N linhas = heterogênea); unidades
  soltas = `qty_units − Σ(box·upb)`. **Embalagem-padrão** reutilizável por produto
  (`product_pack_defaults`) sugere no modal, mas o endereço aceita composição livre.
- **Etiqueta/QR** (`storage_box_labels`): token no QR da caixa fechada → alocação (base da bipagem/
  contagem da Fase 2). Renderização de QR/código de barras no **frontend** (qrcode.js + jsbarcode via
  CDN) — **sem dependência nova no backend**.
- **Código interno** p/ produto sem EAN: `product_eans.source` (`ean|internal`); o interno é um
  **EAN-13 na faixa de uso interno (prefixo 2 + DV)**, reusa o matcher multi-EAN existente
  (ADR/migration 172). Único **só para `internal`** (índice funcional — UNIQUE global em `ean` seria
  regressão: dois galpões podem ter o mesmo EAN de fabricante). Gerar código interno **dispara
  recompute** do estoque (o replay passa a casar notas antigas por ele).

### Invariante
Σ `qty_units` ativas por produto **reconcilia** com `stock_quantity` LOCAL (ADR-0019; FULL fica de
fora — `full_stock` é outra tabela). Diferença = balde **"sem endereço"** (calculado na leitura).
**Kit** (ADR-0023, saldo derivado) é excluído do endereçamento e da reconciliação. Na Fase 1 `qty_units`
só muda por alocação manual do operador; a partir da **Fase 2.5** também se move no **despacho** (débito)
e no **retorno ao vendável** (crédito), e na **Fase 3a** pela **contagem física** (inventário `reason='adjust'`,
que corrige a localização, não o escalar), e na **Fase 3b** pela **transferência** entre endereços
(`transfer_out`/`transfer_in`, **net-zero**: só muda o local, Σ inalterado) — mas a camada segue
**incremental-only** (não acompanha o replay do escalar; o balde "sem endereço" absorve o drift até a
reconciliação). `unaddressed ≥ 0` é endereçamento parcial, **não** drift.

### Autorização (ADR-0036)
Capacidade = **permissão de ação editável por perfil** (`endereco_configurar` monta a árvore,
`endereco_movimentar` aloca/caixas/código/etiqueta; default `go`+`admin`, migration 174). **Escopo
por galpão** (ADR-0026) continua no `data_scope` (intocado): o galpão é **derivado do usuário**,
nunca confiado no path; toda resolução de id (location/allocation/produto/código) checa o galpão
(anti-IDOR cross-galpão). Leitura gateada por login+escopo, não por permissão de escrita.

## Faseamento
- **Fase 1 (esta):** estrutura (árvore) + alocação + caixas + mapa/consulta + reconciliação +
  etiqueta/QR + código interno. Migrations 173 (schema) / 174 (seed). Router `/api/v1/storage`.
- **Fase 2 (implementada):** SUGESTÃO de picking no `PickingCart` (ADR-0005) — **não debita** (débito
  é Fase 2.5). Ponto único `services/storage_picking.py::pick_plan_for` (ordenação em função PURA
  `order_allocations`, testável). **Precedência:** (1) FEFO rastreável — `expiry_date asc nulls_last,
  lot_id asc`, o MESMO ORDER BY do débito de lote (`traceability_service.allocate_fefo`), e alocação
  rastreável **sem lote identificado** vai para o fim (não finge validade); (2) `product_allocations.pick_order`
  (intenção manual por produto); (3) endereço com **unidade solta / caixa aberta primeiro** (preserva
  caixa fechada p/ contagem — pedido do dono); (4) `location.pick_sequence` (rota física); (5) `full_code`.
  Inclui alocações feitas no nível de **variante** do produto-base (senão apareceria "sem endereço"
  falso). `warehouse_id` derivado do próprio produto (`resolve_product_meta`), não do pedido. Rotas de
  LEITURA escopadas: `GET /storage/products/{pt}/{id}/pick-plan` e `GET /separation/carts/{id}/pick-plan`;
  coluna "Endereço (ordem)" no PDF da lista + painel "Rota de picking" na bipagem. Emenda a ADR-0005.
- **Fase 2.5 (implementada):** DÉBITO do endereço dirigido pelo pedido — move `product_allocations.qty_units`,
  **NUNCA** o saldo escalar (ADR-0004 intocado). Gatilho ÚNICO = o MESMO do débito escalar: `confirm_dispatch`
  (entrega da gaiola, ADR-0005) no ramo **não-FULL** (FULL de fora, ADR-0019). Ponto único
  `services/storage_debit_service.py`: `debit_order_addresses` (commit próprio, idempotente por
  `(order_id,'dispatch')`, best-effort — nunca derruba o despacho; atômico via plan/apply + rollback) debita
  na ORDEM do picking (reusa `storage_picking.order_allocations`: FEFO = mesmo ORDER BY do débito de lote),
  **preservando a variante vendida** (mira `variant_pg/variant_cmig`, fallback base — não agrega no base como
  `allocate_order_lots`), expandindo **kit→componentes** (ADR-0023, kit sem alocação), consumindo **solta antes
  de abrir caixa** (reduz `box_count` menor `upb` primeiro e desativa a `StorageBoxLabel` da caixa aberta).
  `credit_order_addresses` (NÃO commita — router orquestra em `validate_return_items`; best-effort) devolve ao
  endereço a qtd REAL devolvida por produto (devolução parcial NF-e), **só no ramo aprovado** (`approved=True`;
  unfit não volta ao vendável), idempotente por `return_id` (ou `(order_id,'return')` no cancelamento), creditando
  de volta as MESMAS alocações debitadas e **sem super-creditar** (teto = debitado − já devolvido). Razão
  append-only `product_allocation_movements` (migration 175) carrega `base_product_*` (produto-lógico, bridge p/
  o crédito reencontrar débitos de variante) e `allocation/location/lot_id` (fidelidade de recall). Extrato de
  leitura `GET /storage/allocation-movements` (escopado por galpão, ADR-0026). Produto **sem endereço = no-op**
  (o balde "sem endereço" absorve; `unaddressed ≥ 0` é endereçamento parcial, não drift). A camada é
  **incremental-only**: `qty_units` NÃO é reconstruído pelo replay do escalar (ADR-0019) — uma nota
  cancelada/editada ou "Recalcular Estoque" move o escalar sem mover o endereço, e o balde absorve até a
  reconciliação. Emenda a ADR-0005. **Caminho de retorno:** `confirm_pending_return` (pedido inteiro),
  `validate_return_items` (NF-e-driven parcial) e `validate_return` (devolução não-NF-e legada) creditam
  o endereço **só no ramo aprovado**; `receive_*`/`mark_awaiting_return` ficam de fora (ainda não voltam
  ao vendável). **Follow-ups:** (a) endpoint admin de reconcile-fix (replay do débito p/ pedidos
  despachados sem movimento de endereço); (b) retorno de **KIT** não credita o endereço dos COMPONENTES
  (o crédito é chaveado no id do kit; `base_product_*` do débito é o componente → no-op) — **espelha o
  escalar** (que credita o `stock_quantity` derivado/0 do kit, ADR-0023, sem restaurar componentes),
  então os dois ficam coerentes e o balde "sem endereço" absorve; corrigir exige tratar escalar+endereço
  juntos.
- **Fase 3a (implementada):** INVENTÁRIO POR ENDEREÇO (migration 176). O operador conta fisicamente um
  endereço e o sistema ajusta `product_allocations.qty_units` para bater com o contado, logando movimento
  `reason='adjust'` (3º vetor de `qty_units`, além de alocação manual / dispatch / return). Corrige **ONDE**
  o estoque está — **NUNCA** o saldo escalar (ADR-0004) nem `product_lots` (ADR-0027). Ponto único
  `services/storage_inventory_service.py::apply_count`: **fail-loud** (não best-effort — ação direta do
  operador; o router valida escopo/produto/lote/kit/packs e passa dados validados), commita atômico (a
  contagem inteira ou nada), **bloqueia kit** (ADR-0023), conta **por `(produto, lot_id)`** com SEM-LOTE
  (`lot=NULL`), pode **criar alocação** p/ produto achado não registrado (upsert com `.is_(None)` no lote +
  `IntegrityError`→409 anti-corrida), pula movimento de `delta=0`, seta `created_by`. Abertura de caixa no
  decréscimo reusa `_plan_pack_open` + desativa `StorageBoxLabel` pelo helper **compartilhado** com o débito
  (`storage_service.box_labels_to_close`, sem QR órfão). Devolve por produto a **divergência pós-contagem**
  (contábil `stock_quantity` × endereçado Σ`qty_units`, `unaddressed`, flag **`over`** = endereçado > contábil
  = físico lançado além do saldo, caso acionável) — **visível** (CLAUDE.md fail-loud), NÃO corrige o escalar:
  isso é o inventário CONTÁBIL (ADR-0004), fluxo distinto na API/UI. Rotas: `POST /storage/locations/{id}/count`
  (permissão `endereco_movimentar`), `GET /storage/inventory/to-count` (ciclo de contagem, NULLS FIRST),
  `reason='adjust'` no `GET /storage/allocation-movements` (relatório de divergências). `storage_locations`
  ganha `last_counted_at/by`. `resolve_base_product` (variante→base, MESMA semântica do débito) preenche o
  `base_product_*` do movimento.
  _Follow-ups da 3a (não-bloqueantes):_ (a) contagem concorrente do mesmo endereço é last-writer-wins
  (estado final correto; só o `delta` logado de uma contagem com `before` defasado fica impreciso — lock
  otimista se o extrato virar trilha contábil); (b) a divergência reportada agrega por produto, não por
  lote (inventário-por-lote fica para depois).
- **Fase 3b (implementada):** TRANSFERÊNCIA ENTRE ENDEREÇOS (migration 177; `reason` += `transfer_out`/
  `transfer_in`). Movimento **INTERNO** — muda só o local, o Σ `qty_units` do produto **não muda** →
  **nunca toca o saldo escalar** (ADR-0004) nem `product_lots`/`stock_lot_allocations` (ADR-0027);
  `transfer_out(−N)` + `transfer_in(+N)` = **net-zero intra-galpão** (mais forte que dispatch/adjust, que
  o balde "sem endereço" absorve). Ponto único `services/storage_transfer_service.py`: `transfer_quantity`
  (commit atômico, fail-loud, `IntegrityError`→409) + `transfer_location_all` (esvaziar endereço,
  all-or-nothing). **Dois caminhos mutuamente exclusivos** (Σ preservado em ambos): *reassign* (move TOTAL
  p/ destino sem o slot → só reatribui `location_id`, carrega packs/etiquetas intactos) × *geral* (parcial,
  ou destino que já tem o slot → debita a origem reusando `_plan_pack_open` + `box_labels_to_close`, credita
  **solto** no destino via `_find_allocation`; origem zerada **fica ativa em 0** — mesma convenção do
  débito da Fase 2.5 (a UNIQUE do slot não filtra `is_active`, então desativar envenenaria o slot e
  travaria transferir o produto de volta; linha 0-qty é inócua na reconciliação; sem hard-delete, preserva
  o FK dos movimentos históricos). **Trava mesmo-galpão no service** (admin é global; `to.warehouse_id ==
  from.warehouse_id` fail-loud 400) além do escopo por usuário no router (ADR-0026). `lot_id` preservado
  ponta a ponta; `base_product_*` via `resolve_base_product`; `transfer_*` são ortogonais à matemática de
  crédito de devolução (`_outstanding_by_base` só olha dispatch/return). Rotas: `POST /storage/transfer`,
  `POST /storage/locations/{id}/transfer-all`; `POST /allocations/{id}/move` passou a delegar (ganhou
  ledger + merge, fim do 409 "una as alocações"); `reason` do extrato aceita os 5 valores. _Follow-ups:_
  (a) transferência parcial chega **solta** no destino (recompor caixas é manual; box tracking é a Fase 3
  restante); (b) `qty_units` é lido-e-reescrito sem `with_for_update` — duas transferências concorrentes na
  MESMA alocação podem perder um débito (mesmo perfil pré-existente do débito/inventário; a reconciliação
  detecta, lock otimista fecharia de vez); (c) linhas 0-qty ativas acumulam em endereços esvaziados
  (inócuas na reconciliação; uma limpeza/prune é opcional).
- **Fase 3 (restante):** rastreio individual por caixa física (box tracking).

## Consequências
- Zero regressão no motor de estoque/fiscal (nada grava saldo; tabelas nascem vazias).
- `services/product_scope.assert_pg_scope` extraído de `invoices.py` (ponto compartilhado).
- Código interno de **variante** não é suportado na Fase 1 (`product_eans` não tem FK p/ variante) —
  bloqueado com erro claro (fail-loud).
- Convive com ADR-0004 (escalar), ADR-0027 (lotes/FEFO), ADR-0005 (picking), ADR-0026 (escopo),
  ADR-0019 (FULL/local), ADR-0023 (kit derivado), ADR-0036 (capacidade por perfil).

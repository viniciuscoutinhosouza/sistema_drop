# LOG de alterações — Sistema Drop

> Resumo cronológico das alterações feitas via Claude. Mais recente no topo.

---

## 2026-05-30 — feat(catalog): anúncios com variações (ML) — publicar, editar e sincronizar estoque por variação

**Pedido:** Botão "Anúncio com Variações" na tela Catálogo. Cada anúncio agrupa N variações (cor/tamanho/voltagem) com produtos simples vinculados (PG **ou** CMIG, origem única por anúncio). Sistema valida se a categoria do ML aceita variações, lê os atributos de combinação e popula SKU/EAN/estoque/preço sugerido a partir do produto vinculado. Usuário pode editar preço e fotos por variação. Estoque sempre = estoque disponível do produto vinculado; quando zera, variação fica "sem estoque" na VIP e volta sozinha quando o estoque cresce.

**Backend:**
- `BACKEND/routers/anuncios.py` — novos endpoints:
  - `GET /anuncios/{id}` — listing único (para modo edição)
  - `GET /anuncios/categories/{id}/variation-support` — detecta suporte a variações via atributos com tag `allow_variations` (e/ou `settings.attribute_types == "variations"`). Retorna `variation_combination_attrs`, `variation_own_attrs`, `max_variations_allowed`, `max_pictures_per_item_var`, flag `allows_custom_variations`.
  - `POST /anuncios/publish-with-variations` — valida (origem única, combinações únicas, mesmos atributos em todas), monta payload ML em 2 passos (POST `/items` + PUT `/items/{id}` com `picture_ids` resolvidos via `pictures` retornado pelo ML).
  - `PUT /anuncios/{id}/variations` — edição completa com a regra de ouro do ML (enviar lista completa de `variations`).
  - Helpers `_validate_variations_input`, `_load_variation_product`, `_build_ml_variation_obj`, `_prepare_variations_for_ml`, `_enrich_variations_json`, `_consolidate_unique_pictures`, `_resolve_picture_ids_for_variation`.
- `BACKEND/services/ml_service.py` — `update_item_variations(access_token, item_id, variations)` e `update_item_status(...)` para PUT atômicos.
- `BACKEND/routers/cmigs.py` — `GET /cmigs/{id}/products` ganhou `search` (ilike por título/SKU) e `simple_only` (exclui kits).
- `BACKEND/tasks/sync_variation_stock.py` (novo) + `BACKEND/tasks/scheduler.py` — job a cada 30min: para cada listing com `variations_json` lê stock do PG/CMIG via `_source`/`_catalog_product_id`/`_cmig_product_id`, envia `available_quantity = max(stock, 0)` (variações com 0 ficam "Sem estoque" — preservam histórico). Quando todas zeram pausa item; quando alguma volta positiva reativa.

**Frontend:**
- `FRONTEND/src/views/catalog/CatalogVariationsFormView.vue` (novo) — view única para publicar e editar. 4 seções: (1) conta/origem PG-CMIG/tipo classico-premium em ícones quadrados 80×80, (2) título/modelo/categoria com path completo (ex.: `Esportes › Fitness › Bolas`), (3) tabela editável de variações com selects para combinação, picker de produto, SKU/EAN/estoque readonly, preço editável (default = `suggested_price`), editor de fotos por variação, (4) frete + publicar.
- `FRONTEND/src/components/catalog/VariationProductPicker.vue` (novo) — typeahead com `<Teleport to="body">` (evita corte pelo `.table-responsive`), posicionamento fixo via `getBoundingClientRect()`, largura mínima 320px, fonte alterna entre `/catalog?search=...` (PG) e `/cmigs/{id}/products?search=...&simple_only=true` (CMIG).
- `FRONTEND/src/components/catalog/VariationPicturesEditor.vue` (novo) — modal por variação com galeria do produto vinculado, adicionar por URL, upload, drag/remove. Respeita `max_pictures_per_item_var` da categoria.
- `FRONTEND/src/views/catalog/CatalogView.vue` — botão "Anúncio com Variações" (sempre clicável; leva `account_id` na query quando há ML selecionado).
- `FRONTEND/src/router/index.js` — rotas `/catalog/anuncios-variacoes/new` e `.../:listing_id/edit`.

**Decisões alinhadas:**
- Origem única por anúncio: ou todas variações PG ou todas CMIG (nunca misturado). Validado client + server.
- KITs (`is_composite=true`) excluídos dos pickers.
- CMIG pode ser usado com ou sem vínculo PG.
- Preço default = `suggested_price` (cai pra `cost_price` se nulo), sempre editável.
- Quando variação fica com estoque 0: envia `available_quantity=0` (preserva histórico ML) em vez de deletar+recriar.
- Variações personalizadas (`name` livre) fora da fase 1.

**Bug corrigido na sessão (categoria MLB123037 / Bolas):**
- Detecção de variações estava confiando só em `settings.attribute_types == "variations"`. Categoria de Bolas tem esse setting `None` mas tem atributo `COLOR` com tag `allow_variations` e aceita variações. Critério corrigido para priorizar atributos com `allow_variations` (fonte de verdade).

---

## 2026-05-29 — feat(cmig-reports): submenu Relatórios em MINHAS CONTAS com 2 PDFs (tabela de preços + estoque)

**Pedido:** Novo submenu "Relatórios" em MINHAS CONTAS abrindo tela com cards/ícones de relatórios para impressão em PDF. Usuário escolhe a CMIG num dropdown e dispara: (1) Tabela de Preços (foto, SKU, EAN, título, preço de venda) ou (2) Relatório de Estoque (foto, SKU, EAN, título, estoque, custo unitário e custo total + total geral no rodapé).

**Backend:**
- `BACKEND/services/cmig_report_service.py` (novo) — `build_price_table_pdf()` e `build_stock_report_pdf()` usando ReportLab (já presente em `requirements.txt`). Layout A4 paisagem, fotos de capa embutidas via path local em `static/uploads/cmig-products/`, total geral no PDF de estoque (Decimal para evitar erro de float).
- `BACKEND/routers/cmig_reports.py` (novo) — `GET /price-table` e `GET /stock` retornando `Response(application/pdf)` com `Content-Disposition: attachment`. Query string `?include_zero_stock=true|false`.
- `BACKEND/main.py` — registrado em `prefix=/api/v1/cmigs/{cmig_id}/reports` (mesmo padrão de `fiscal_config`).
- Autorização replicada do `_check_cmig_access` de `routers/cmigs.py`: admin libera tudo; UGO precisa do mesmo `warehouse_id`; AC precisa ser administrador da CMIG via `CMIGAdministrator`.
- Preço de venda = `cmig_products.suggested_price` (decisão alinhada com o usuário — `product_listings.sale_price` ignorado para esta versão).
- Render do PDF roda em `asyncio.to_thread()` para não bloquear o event loop.

**Frontend:**
- `FRONTEND/src/views/cmig-reports/CmigReportsView.vue` (novo) — dropdown popula via `useCmigStore().fetchCmigs()`; toggle "Incluir produtos sem estoque" (default: marcado); grid de 2 cards (`col-md-6 col-xl-4`) com ícone, título, descrição e botão "Gerar PDF". Download por blob + `URL.createObjectURL`.
- `FRONTEND/src/components/common/AppSidebar.vue` — novo `<li>` "Relatórios" (ícone `fa-file-pdf`) dentro do bloco `MINHAS CONTAS` visível a AC e admin.
- `FRONTEND/src/router/index.js` — rota `'cmig-reports'` com `meta.role: 'ac'`.

**Decisões alinhadas:**
- Preço de venda = `suggested_price` do CMIG.
- PDF no backend com ReportLab (sem dependência nova).
- Custo total por item + total geral no rodapé do PDF de estoque.
- Toggle no frontend para incluir produtos sem estoque (default: incluir).

**Follow-up no mesmo dia:**
- Botão dos cards passa a exibir o nome do relatório ("Gerar Tabela de Preços" / "Gerar Relatório de Estoque") em vez de "Gerar PDF" genérico.
- Fotos não apareciam no PDF porque o resolvedor de imagem só aceitava URLs `/static/...`. Refatorado `cmig_report_service.py`: agora também baixa imagens remotas (`http://`, `https://`) em paralelo via `httpx.AsyncClient`, normaliza via PIL (RGBA/P → RGB → JPEG) e passa BytesIO para o ReportLab. Pré-fetch acontece no `build_*_pdf` async antes do `asyncio.to_thread()` que renderiza o PDF.

---

## 2026-05-28 — feat(stock-movements): redesign do modal + correcao de pedidos diretos no PG (sprints 1-4)

**Pedido:** Tela de Movimentacao de Estoque nao exibia pedidos vendidos do PG quando o pedido apontava direto ao `OrderItem.catalog_product_id` (sem CMIG intermediario). Estudo amplo revelou multiplos gaps; pacote evoluiu em 4 sprints.

**Bug-fix raiz** (pedido 2000016606129626, PG 66):
- `calculate_pg_product_stock` em `services/fiscal/stock_calculator.py` so contava pedidos por overflow CMIG ou kit. Pedidos diretos ao PG ficavam orfaos (cache desatualizado e tabela vazia).
- Adicionado 4o caminho que conta `OrderItem.catalog_product_id == pg.id` em shipped/delivered, excluindo via NOT EXISTS os ja cobertos por CMIG. Sem dupla contagem (regra: pedido com NFe vinculada conta 1x pelo pedido, NFe-out linked ignora; pedido sem NFe conta 1x).
- Funcao gemea `_fetch_direct_pg_order_events` em `services/stock_history.py` para exibir esses eventos no modal (corrigido cartesian join inicial usando exclusao identica a do balanco).
- Recompute retroativo: 6 PGs corrigiram saldo (PG 66: 8 -> 7).

**Sprint 1 — coerencia visual:**
- Banner de reconciliacao (cache vs calculado) no topo do modal.
- Cards redesenhados: 3 cards de Estado Atual (Saldo / Reservado / Disponivel) + 4 cards de Movimentacao do Periodo (Entradas NFe / Saidas NFe / Saidas Pedidos / Variacao liquida).
- Corrigida formula `current_balance_available`: cache - reservado (sem subtrair `moved_in_orders_no_nfe` que duplicava saidas).
- Sub-badge na coluna Origem: `Direto PG` / `Overflow CMIG` / `Kit`.
- Novo campo `origin_kind` em `StockEvent`.

**Sprint 2 — auditoria + kit (M4 + M5):**
- Migration 75 `Scripts SQL/75_stock_manual_adjustments.sql` (aplicada via DDL direto no Oracle): tabela `stock_manual_adjustments(id, product_type, product_id, old_value, new_value, delta, reason, user_id, adjustment_kind, created_at)`.
- Model `BACKEND/models/stock_adjustment.py` + helper `BACKEND/services/fiscal/stock_audit.py::log_adjustment`.
- Hooks de auditoria em 4 endpoints: `PUT /pg/{id}/stock` (manual_override), `POST /pg/{id}/recalculate-stock`, `POST /cmigs/.../recalculate-stock` (ambos recompute), `POST /pg/recalculate-all-stock` (batch_recompute).
- `_fetch_kit_component_events`: pedidos vendendo um KIT do qual o PG e componente aparecem no modal com sub-badge "Kit" e linha "Kit: {nome do kit}".
- Ajustes manuais aparecem na tabela como badge cinza (`Ajuste Manual` / `Recalculo` / `Recalculo em Lote`), informativos — nao alteram running_balance.

**Sprint 3 — UX (M7 + M8 + M9):**
- Toolbar de 5 checkboxes (NFe Entrada / NFe Saida / Pedidos / Reservados / Ajustes), filtragem client-side.
- 2 linhas-resumo na tabela: "Saldo no fim do periodo" no topo + "Saldo no inicio do periodo" no fim (ordem DESC). Backend retorna `period_initial_available` e `period_final_available` com snapshot considerando ajustes.
- Botao "Exportar CSV" com BOM UTF-8 + separador `;` (Excel BR). Respeita filtros ativos.

**Sprint 4 — refator (M10 + M11):**
- `FRONTEND/src/components/stock/StockMovementsModal.vue` — componente reutilizavel parametrizado por `productType: 'pg' | 'cmig'`. Encapsula filtros, banner, cards, tabela, recalc, export.
- `BACKEND/services/stock_movements.py::build_movements_response` — funcao unica que constroi o response dos 2 endpoints. Mantem todos os campos legados + adiciona unificados (`current_balance`, `reserved`).
- Endpoints `GET /pg/{id}/stock-movements` e `GET /cmigs/{cmig_id}/products/{id}/stock-movements` reduzidos a ~14 linhas cada. ~780 linhas duplicadas eliminadas (backend + frontend).

**Validacoes:** PG 66 cache=7 / calculated=7 / movements=2 ✓. CMIG 2 cache=0 / calculated=0 / has_pg_link=True ✓. Build frontend OK (StockMovementsModal 23kB).

---

## 2026-05-28 — feat(scheduler-monitoring): tela de monitoramento + persistencia + recalculo automatico de estoque

**Pedido:** (1) Recalcular estoque sempre que um pedido for recebido, com explosao de kits para recalcular componentes. (2) Tela de monitoramento das rotinas automatizadas exclusiva para Operador (UGO), Gestor (GO) e Admin, com janela default de ultimas 3h, indicadores por rotina e proxima execucao.

**Mudancas:**

- **Migration 74** `Scripts SQL/74_scheduler_job_executions.sql`: tabela `scheduler_job_executions(id, job_id, started_at, finished_at, duration_ms, status, result_json, error_message, triggered_by)` + indices.

- **Wrapper** `BACKEND/tasks/_job_wrapper.py::tracked_job` — context manager que grava 1 linha por execucao em sessao isolada (sobrevive a rollback do job). Captura inicio/fim/duracao/status/erro/resultado.

- **8 jobs APScheduler refatorados** para usar `tracked_job` e retornar dict de contadores: sync_orders, sync_stock, refresh_tokens, sync_dfe, sync_messages, check_subscriptions, fiscal_alerts, refresh_ml_reputation.

- **Novo job** `BACKEND/tasks/prune_logs.py::prune_job_executions` — cron diario 04:00 UTC, apaga execucoes > 30 dias.

- **Trigger event-driven** `services/fiscal/stock_calculator.py::trigger_stock_recompute_on_order_created` — recalcula PG + CMIG + kits afetados ao criar pedido. Registra como execucao `stock_recompute_on_order` com `triggered_by='event'`. Chamado em 3 caminhos: `process_ml_order` e `process_shopee_order` (webhook + polling) e `routers/manual_orders.create_manual_order`.

- **Router** `BACKEND/routers/scheduler_monitoring.py` com prefixo `/api/v1/scheduler` (require_role("ugo","go","admin")):
  - `GET /jobs?hours=N` — 10 rotinas com last_run, next_run (do APScheduler), success_rate, avg_duration.
  - `GET /executions?date_from=...&date_to=...&job_id=...&status=...&page=...&size=...` — historico paginado, default ultimas 3h.
  - `GET /executions/{id}` — detalhe com result_json + error_message completo.

- **Frontend tela** `FRONTEND/src/views/monitoring/SchedulerMonitoringView.vue` (rota `/monitoring/jobs`, `meta.role: 'ugo'` — guard ja cobre GO e admin) + entrada na sidebar (`<template v-if="isUGO || isGO">` secao MONITORAMENTO). Cards de KPI por rotina + tabela paginada + modal de detalhe. Auto-refresh 30s.

**Indicadores por rotina (10 monitoradas):** `accounts_processed`, `orders_imported_*`, `tokens_refreshed/failed`, `listings_processed/updated`, `dfes_new`, `tokens_checked`, `subscriptions_overdue`, `notifications_sent`, `alerts_sent`, `messages_fetched`, `sellers_updated`, `kits_recomputed`, etc.

**Validacoes:** Build frontend OK (`SchedulerMonitoringView` 42kB). Backend imports OK. Migration 74 aplicada via DDL direto.

---

## 2026-05-28 — feat(pedido-manual): refatoracao Drop Manual -> Pedido Manual (catalogo + carrinho + cliente)

**Pedido:** Renomear "Drop Manual" para "Pedido Manual"; adotar o mesmo padrao visual do Catalogo (grid + toggle PG/CMIG); permitir carrinho com varios itens; selecionar cliente cadastrado ou criar novo via modal.

**Decisoes acordadas:**
- Adicionada FK `buyer_person_id` em `orders` (rastreabilidade) — snapshot textual (`buyer_name`/email/document/shipping_address) continua sendo preenchido.
- Carrinho mistura PG + CMIG. Nova FK `cmig_product_id` em `order_items` para itens CMIG sem `pg_product_id`.

**Mudancas:**

- **SQL** `Scripts SQL/76_pedido_manual_person_cmig_item.sql` (novo) — adiciona `orders.buyer_person_id` (FK `people`) e `order_items.cmig_product_id` (FK `cmig_products`), com blocos `DECLARE...EXCEPTION` idempotentes.

- **Backend models** `BACKEND/models/order.py` — `Order` ganha `buyer_person_id` + relacionamento `buyer_person`; `OrderItem` ganha `cmig_product_id`.

- **Backend router** `BACKEND/routers/manual_orders.py` — reescrito. `POST /api/v1/manual-orders` agora recebe `{cmig_id, buyer_person_id, items: [{kind, id, quantity}]}` onde `kind = 'pg' | 'cmig'`. Valida acesso a CMIG via `CMIGAdministrator`, carrega produtos em batch (Catalog + CMIG), cria `Order` com `cmig_id` e snapshot do comprador (Person), cria 1 `OrderItem` por entrada com `catalog_product_id` (PG) ou `cmig_product_id` (CMIG, com `catalog_product_id` espelhado quando ha `pg_product_id`). Mantem trigger de recalculo de estoque.

- **Frontend rename:**
  - `FRONTEND/src/components/common/AppSidebar.vue` — label "Drop Manual" -> "Pedido Manual" (icone `fa-hand-paper` mantido, regra `v-if="isAC"` mantida).
  - `FRONTEND/src/router/index.js` — `meta.title` da rota `/manual-orders` -> "Pedido Manual". Path inalterado.

- **Frontend componentes novos:**
  - `FRONTEND/src/components/people/PersonSearchModal.vue` — modal `teleport` (padrao `ConfirmModal`), busca por nome/CPF/CNPJ via `usePeopleStore.fetchPeople({cmig_id, is_customer: true, search, page})` com paginacao.
  - `FRONTEND/src/components/people/PersonFormModal.vue` — modal `teleport` enxuto (PF/PJ, doc, nome, contato, endereco), com botao de lookup CNPJ na BrasilAPI; salva via `usePeopleStore.createPerson(...)` forcando `is_customer = true`.

- **Frontend view** `FRONTEND/src/views/manual-orders/ManualOrderView.vue` — reescrito em 4 cards verticais:
  1. CMIG: select carregado por `GET /orders/cmigs/available` (auto-seleciona se houver so 1).
  2. Selecionar Produtos: `btn-group` PG/CMIG (visual identico ao `CatalogView`), grid `col-xl-2 col-lg-3 col-md-4 col-sm-6` com cards (thumb 130px, SKU, titulo 50ch, preco verde, botao "Adicionar ao carrinho"). PG via `GET /catalog` (paginado), CMIG via `GET /cmigs/{cmig_id}/products` (filtro em memoria).
  3. Cliente: botoes "Buscar cliente" e "+ Novo cliente"; ao selecionar exibe card com nome/doc/cidade e botao "Trocar".
  4. Carrinho: tabela com thumb, SKU + badge PG/CMIG, qtde editavel, subtotal, total. Botao "Fechar pedido" (desabilitado sem cliente ou carrinho vazio) -> `POST /api/v1/manual-orders` -> redirect `/orders/{id}`.

  Estado do carrinho em `ref([])` local (sem store global). Reabertura do mesmo produto incrementa quantidade em vez de duplicar.

**Validacoes:** `npm run build` OK em 25.82s (`ManualOrderView` 21.31kB). Backend imports OK (`models.Order.buyer_person_id` e `models.OrderItem.cmig_product_id` presentes).

**Proximo passo manual:** rodar a migration `Scripts SQL/76_pedido_manual_person_cmig_item.sql` no Oracle ATP antes de subir o backend novo.

---

## 2026-05-28 — feat(auth): opcao "Trocar senha" no menu do usuario (modal)

**Pedido:** Permitir que o usuario logado troque a propria senha pelo dropdown do nome no canto superior direito.

**Solucao:** Item "Trocar senha" adicionado no dropdown do `AppTopbar`. Ao clicar, abre modal (teleport para body, padrao Bootstrap 5 + AdminLTE) com 3 campos: senha atual, nova senha (min 6 chars) e confirmacao. Submit chama `POST /api/v1/auth/change-password` (endpoint ja existente em `routers/auth.py`), com toast de sucesso/erro. Inputs ficam desabilitados durante o submit; cancelar / esc fecha o modal e limpa o form.

**Arquivo:** `FRONTEND/src/components/common/AppTopbar.vue` (unico arquivo alterado).

**Backend:** sem mudanca — endpoint `POST /api/v1/auth/change-password` ja existia com schema `ChangePasswordRequest` validando `new_password == new_password_confirm`.

---

## 2026-05-28 — fix(pedidos): colaborador CMIG nao via pedidos na tela de Pedidos

**Problema:** Usuarios com `role="ac"` que sao colaboradores (nao proprietarios) de uma CMIG nao viam nenhum pedido — a lista vinha vazia. Proprietarios da mesma CMIG viam tudo normalmente.

**Causa raiz:** `BACKEND/routers/orders.py` filtrava pedidos via `Order.dropshipper_id == current_user.id` em **14 endpoints distintos** (list, detalhes, summary, kanban, exports, dashboards). Esse campo aponta para o AC dono original que recebe o pedido via webhook/sync das marketplaces — o id do colaborador nunca aparece la, por isso a query retornava 0 linhas. O proprio arquivo ja tinha o padrao correto no endpoint `/orders/cmigs/available`, que usa `CMIGAdministrator.user_id == current_user.id`.

**Solucao:** Helper `_ac_visible_filter(current_user)` em `routers/orders.py` que retorna o predicado SQL `dropshipper_id = :uid OR cmig_id IN (SELECT cmig_id FROM cmig_administrators WHERE user_id = :uid)`. As 14 ocorrencias do filtro defeituoso foram substituidas pela chamada ao helper. Isso cobre:
- AC proprietario (via `dropshipper_id` — backward compat)
- AC colaborador da CMIG (via `cmig_administrators`)
- Mantem isolamento — AC sem vinculo continua sem ver os pedidos

**Arquivo:** `BACKEND/routers/orders.py` (unico arquivo alterado).

**Fora de escopo:** Atribuicao de `dropshipper_id` na CRIACAO de pedidos manuais (linhas 876, 1824, 1969, 2143) — decisao de produto pendente sobre se colaborador vira dono direto ou se atribuir ao `owner_ac_id` da CMIG. Com o filtro hibrido nao ha regressao.

---

## 2026-05-27 — feat(envio): paleta canonica de cores para shipping_mode (Full/Flex/Agencia/Correios/Coletado/Combinado)

**Problema:** FULL (badge-success) e FLEX (badge-info) tinham cores muito parecidas (verde claro vs ciano), alem de cores divergentes entre OrderListView, ShipmentModal, DeliveryModal e AnunciosView. Cada arquivo tinha seu proprio mapa de cores.

**Solucao:** centralizada UMA paleta em `FRONTEND/src/utils/constants.js` (`SHIPPING_MODE_STYLE` + helper `shippingModeStyle(mode)`). Todos os badges importam dela. Cada modo tem `bg` (background), `fg` (texto), `icon` e `title`.

### Paleta canonica — NAO duplicar cores em outros arquivos

| Modo         | Cor (bg)   | Texto (fg) | Icone               | Significado                                  |
|--------------|-----------|------------|---------------------|----------------------------------------------|
| **full**     | `#00a650` | `#ffffff`  | fa-warehouse        | Verde ML oficial (Fulfillment)              |
| **flex**     | `#f97316` | `#ffffff`  | fa-bolt             | Laranja Flex (Mercado Envios Flex)          |
| **agencia**  | `#7c3aed` | `#ffffff`  | fa-store            | Roxo (Mercado Envios Places/Ágil)           |
| **correios** | `#facc15` | `#1f2937`  | fa-truck            | Amarelo Correios (vendedor leva na agência) |
| **coletado** | `#0891b2` | `#ffffff`  | fa-people-carry     | Ciano/Teal (ML coleta no vendedor)          |
| **combinado**| `#6b7280` | `#ffffff`  | fa-handshake        | Cinza neutro (acordo direto vendedor↔comprador) |
| **desconhecido** | `#e5e7eb` | `#4b5563` | fa-truck         | Cinza claro (modo nao identificado ainda)   |

### Arquivos atualizados

- `FRONTEND/src/utils/constants.js` — fonte unica da paleta (`SHIPPING_MODE_STYLE`, `shippingModeStyle()`).
- `FRONTEND/src/views/orders/OrderListView.vue` — badge da lista de pedidos.
- `FRONTEND/src/components/orders/ShipmentModal.vue` — campo "Logística" no modal de envio.
- `FRONTEND/src/components/orders/DeliveryModal.vue` — campo "Tipo" no modal de entrega.
- `FRONTEND/src/views/anuncios/AnunciosView.vue` — badges Full/Flex inline na linha do anuncio.

**Regra:** qualquer view nova que mostre forma de entrega DEVE importar `shippingModeStyle` de `@/utils/constants`. NUNCA hardcodar cor de badge de shipping_mode em outro lugar — se a paleta mudar, vai dessincronizar.

---

## 2026-05-26 — feat(faturador): integração com /items/fiscal_information (endpoint correto do Faturador ML)

**Descoberta:** O endpoint de debug `/debug-fiscal-sync` (PUT /items com atributo `ICMS_CSOSN`) confirmou que **o ML droppa silenciosamente** `ICMS_CSOSN` e `TIPO_DE_ORIGEM` com warning `item.attributes.invalid - was dropped because does not exists`. Os atributos NCM/CEST/GTIN/ORIGIN persistem (são atributos de categoria), mas CSOSN não é atributo de item.

Pesquisa em [https://developers.mercadolivre.com.br/pt_br/envio-dos-dados-fiscais](https://developers.mercadolivre.com.br/pt_br/envio-dos-dados-fiscais) revelou o endpoint correto: **`POST/PUT /items/fiscal_information`** (indexado por SKU, não por item_id).

**Teste de debug confirmou:** SKU 5505 cadastrado com sucesso, `status: 201`, `can_invoice: true`, todos os campos (`ncm`, `csosn=102`, `origin_type=reseller`, `origin_detail=2`, `cest`, `ean`, `net_weight`, `gross_weight`) persistidos.

**Mudanças:**

`BACKEND/services/ml_service.py`:
- `origin_detail_to_type(origin_detail)`: mapeia 0-8 → "manufacturer" | "imported" | "reseller" conforme tabela CST/CSOSN origem.
- `register_or_update_fiscal_information(access_token, sku, payload)`: tenta POST `/items/fiscal_information`; fallback PUT `/items/fiscal_information/{sku}` se POST falhar. **Best-effort** — retorna dict `{ok, status_code, method, body, error}` sem levantar exception.
- `build_fiscal_information_payload(**kwargs)`: monta payload no formato esperado do endpoint, com `tax_information` apenas com campos preenchidos (evita reset acidental por chave vazia).

`BACKEND/routers/anuncios.py`:
- `_build_fiscal_payload_from_product(product, sku, cmig_crt, overrides)`: helper que extrai fiscal do produto + overrides + fallback CRT→CSOSN.
- `_parse_fiscal_json(raw)`: aceita string JSON ou dict.
- **NOVO endpoint** `POST /{listing_id}/sync-fiscal`: empurra fiscal_information para o ML manualmente, útil para anúncios antigos sem precisar reabrir o wizard.
- **NOVO endpoint** `POST /{listing_id}/debug-fiscal-information`: variante do sync com overrides via Swagger. Tenta POST→PUT, retorna `attempts[]` + GET pós-operação para validar persistência.
- `publish_anuncio` (`mode=create`): após `_create_ml_item_with_retry`, chama `register_or_update_fiscal_information`. Falha vira `fiscal_sync_warning` no response.
- `update_listing`: após `update_item`, chama a mesma rotina. Mesmo padrão de warning.
- Removido bloco `ICMS_CSOSN` do `_build_ml_payload` (ML droppava com warning — atributo não existe na categoria).

**Como testar:**
1. **Reemitir NFe** do pedido travado anteriormente — agora o SKU 5505 está cadastrado no Faturador (`can_invoice: true`).
2. Para outros anúncios já publicados: `POST /api/v1/anuncios/{listing_id}/sync-fiscal` via Swagger.
3. Para novos anúncios: o publish já sincroniza fiscal automaticamente. Se faltar NCM no produto, retorna `fiscal_sync_warning` no response.

**Deploy:** scp + `pm2 restart sistema-drop-backend`. Backend online sem erros.

**Pendências futuras:**
- UI para mostrar warning de fiscal_sync_warning no toast pós-save do wizard.
- Botão "Sincronizar fiscal" no menu de ações por anúncio (chama `/sync-fiscal`).
- Endpoint em lote para sincronizar fiscal de múltiplos anúncios de uma vez.

---

## 2026-05-26 — feat(anuncios,products): suporte a CSOSN + endpoint de debug fiscal

**Contexto:** Mesmo após enviar NCM/CEST/GTIN/ORIGIN no `PUT /items`, os dados fiscais não apareciam no painel "Edite os dados fiscais do anúncio" do ML. O usuário identificou que o formulário do ML exige um campo **CSOSN do ICMS** (Código de Situação da Operação no Simples Nacional, ex: "102 - Tributada pelo Simples") que não existia no nosso schema.

**Mudanças backend:**
- `Scripts SQL/71_add_csosn_to_products.sql` (NOVO): coluna `csosn VARCHAR2(3)` em `cmig_products` e `catalog_products`. Idempotente. Aplicado em produção (3 blocos OK).
- `BACKEND/models/cmig.py` e `BACKEND/models/product.py`: novo campo `csosn = Column(String(3))`.
- `BACKEND/schemas/cmig.py`: `csosn` em `CMIGProductCreate`, `CMIGProductUpdate`, `CMIGProductOut`.
- `BACKEND/routers/supplier_products.py`: aceita `csosn` no create/update/duplicate e inclui no serialize.
- `BACKEND/routers/cmigs.py`: idem para CMIGProduct + duplicate + import-to-pg + sync-pg.
- `BACKEND/routers/anuncios.py`:
  - Helper `_resolve_cmig_crt(account, db)` consulta o CRT da CMIG vinculada à conta.
  - `_build_ml_payload`: novo bloco que envia atributo ML `ICMS_CSOSN` com prioridade `fiscal_json.csosn → product.csosn → derivado do CRT (1/2 → "102")`.
  - `publish_anuncio` e `update_listing` injetam `cmig_crt` no `ml_form`.
  - **NOVO endpoint** `POST /{listing_id}/debug-fiscal-sync`: monta payload fiscal completo (com overrides opcionais e extra_attributes), faz `PUT /items` direto no ML e retorna `payload_sent`, `ml_status_code`, `ml_response_body`, `ml_error_causes` e `fiscal_attributes_persisted_after_put` (GET pós-PUT). Não commita nada no DB. Exposto em Swagger `/docs`.

**Mudanças frontend:**
- `FRONTEND/src/components/products/ProductFiscalFields.vue`: novo `<select>` CSOSN com 10 opções comuns + helper text explicando o fallback automático.
- `FRONTEND/src/views/supplier/PgProductFormView.vue` e `cmig-products/CmigProductFormView.vue`: campo `csosn: null` no form ref.
- `FRONTEND/src/views/anuncios/AnunciosView.vue`: select CSOSN na aba Fiscal do wizard + `wizardFiscal.csosn` no ref + parse/serialize via `fiscal_json` + resets atualizados.

**Como testar:**
1. Acessar `https://ecommerce.madeingroup.com.br/docs`
2. Autenticar com JWT
3. Executar `POST /api/v1/anuncios/{listing_id}/debug-fiscal-sync` com body `{"overrides": {"csosn": "102"}}`
4. Observar `ml_status_code` e `fiscal_attributes_persisted_after_put` para confirmar se ML aceita o atributo `ICMS_CSOSN`
5. Se ML rejeitar, ajustar via `extra_attributes: [{"id": "CSOSN", "value_name": "102"}]` para testar IDs alternativos

**Deploy:** migration 71 aplicada + scp dos arquivos + `pm2 restart sistema-drop-backend`. Backend online às 03:09:43 UTC. Bundle frontend ativo: `index-c67c41ee.js`.

**Riscos conhecidos:** o ID `ICMS_CSOSN` é palpite — o endpoint de debug é precisamente para confirmar o ID correto via tentativa-e-erro pelo Swagger. Pode ser `CSOSN`, `ICMS_CSOSN` ou um endpoint dedicado a fiscal_data que ainda não conhecemos.

---

## 2026-05-25 — refactor(anuncios): mover badge Flex/Full para a linha de info

**Pedido do usuário:** o badge informativo de logistic_type (⚡ Flex, etc) estava sendo renderizado dentro do bloco de Ações de cada anúncio, no meio dos botões pause/Flex-toggle/external-link. Visualmente confuso porque misturava informação com ação.

**Mudança em `FRONTEND/src/views/anuncios/AnunciosView.vue`:**
- O `<span>` do `logisticBadge(a)` foi movido da área de Ações (~linha 396) para a linha de info do anúncio, entre `logisticLabel(a)` (ME2 Drop Off) e `Frete Grátis` (~linha 204).
- O **botão** de toggle Flex (`canToggleFlex` + `fa-bolt`) permanece na área de Ações — é ação, não label.

**Deploy:** `npm run build` (20.97s) + scp do `FRONTEND/dist/`. Bundle ativo: `index-cec1e9fc.js`.

---

## 2026-05-25 — docs(ean): alinhar tooltips/toasts/docstring com prefixo real 789

**Inconsistência:** tooltips, toasts e docstring diziam "prefixo **200**" (in-store/restricted GS1), mas o código real em `FRONTEND/src/utils/ean.js:8` usa `const INTERNAL_PREFIX = '789'` (GS1 Brasil, comercial). O usuário ficou em dúvida se o gerador estava gerando EAN inválido — não estava (checksum sempre OK), mas o prefixo divergia da documentação.

**Verificação:** rodei o gerador 10 vezes via Node — todos os EANs gerados (`7892856056200`, `7898865820092`, etc.) passaram no checksum. O EAN ruim `7890614555133` do erro anterior **não saiu do gerador** — provavelmente foi digitado manualmente ou veio de import.

**Decisão (do usuário):** manter prefixo `789` no código (ML aceita; baixo risco de colisão com 9 dígitos aleatórios) e corrigir a documentação.

**Mudanças (só strings, sem alteração de lógica):**
- `FRONTEND/src/utils/ean.js`: docstring de `generateEan13` atualizada explicando 789/GS1 Brasil + aviso sobre o trade-off.
- `FRONTEND/src/views/supplier/PgProductFormView.vue`: tooltip e toast.
- `FRONTEND/src/views/cmig-products/CmigProductFormView.vue`: tooltip e toast.

**Deploy:** `npm run build` (16.58s) + scp do `FRONTEND/dist/`. Sem restart de backend.

---

## 2026-05-25 — fix(anuncios): valida checksum EAN-13 antes de enviar GTIN ao ML

**Erro observado:** `Aviso ML: Erro ao atualizar anúncio ML: ... "code":"item.attribute.product_identifier.invalid_format" ... "Product Identifier [GTIN] contains values with invalid format: [7890614555133]"` ao salvar anúncio com fiscal preenchido.

**Causa raiz:** GTIN `7890614555133` falha no checksum EAN-13 (esperado terminar em `2`, não `3`). Provavelmente typo do usuário. Como nosso backend enviava o GTIN bruto sem validar, o ML rejeitava o PUT inteiro com 400 e os outros campos fiscais (NCM/CEST/ORIGIN) também não eram salvos.

**Mudanças:**
- `BACKEND/routers/anuncios.py`: nova função `_is_valid_ean13(s)` (algoritmo idêntico ao `FRONTEND/src/utils/ean.js:ean13Checksum`). No `_build_ml_payload`, se o GTIN coletado falhar no checksum, atributo é pulado com warning no log — NCM/CEST/ORIGIN seguem sendo enviados. Evita derrubar o update inteiro por causa de 1 GTIN errado.
- `FRONTEND/src/views/supplier/PgProductFormView.vue`: import de `isValidEan13`, computed `eanInvalid`, classe `is-invalid` no input e mensagem de erro visual quando o checksum falha.
- `FRONTEND/src/views/anuncios/AnunciosView.vue`: mesmo padrão para o campo EAN/GTIN da aba Fiscal do wizard (`wizardEanInvalid`).

**Deploy:** scp backend + scp frontend/dist + `pm2 restart sistema-drop-backend`. Backend online, build do frontend passou (7.15s).

---

## 2026-05-25 — fix(anuncios,simulator): marca requires_reauth imediatamente em invalid_grant

**Problema:** ao salvar anúncio, ML retornava `invalid_grant` (refresh token revogado). O sistema mostrava o toast de erro mas não setava `MarketplaceAccount.requires_reauth=True` — esse flag só era marcado pelo job `tasks/sync_tokens.py` (1x/h), então o usuário ficava sem o alerta vermelho de "Reconectar" até o background job rodar.

**Fix:** em `BACKEND/routers/anuncios.py:_get_valid_token` e `BACKEND/routers/simulator.py`, envolver a chamada `ml_service.refresh_ml_token()` com try/except — se receber HTTPException 401 com detail contendo `invalid_grant`, marcar `account.requires_reauth=True` e commit antes de re-raise. UI passa a mostrar o alerta de reconexão imediatamente.

**Deploy:** scp + `pm2 restart sistema-drop-backend`. Backend online, sintaxe validada.

---

## 2026-05-25 — fix(anuncios): publish/update ML agora envia NCM/CEST/GTIN/ORIGIN

**Erro observado:** ao tentar emitir NFe pelo Faturador do ML, retornou `{"message":"Sku not found by sku: 5505 and caller.id: 2471116577","error_code":"10316"}`.

**Causa raiz:** o Faturador do ML tem um cadastro fiscal próprio (SKU → NCM/CEST/GTIN/Origem). Nosso fluxo de publicação enviava apenas `SELLER_SKU`, `BRAND`, `MODEL`, dimensões e fotos via `POST /items`. NCM/CEST/GTIN/ORIGIN ficavam só no nosso DB (`listing.fiscal_json` e campos do produto) e nunca eram empurrados ao ML. Resultado: o SKU existia no anúncio do ML, mas sem dados fiscais → Faturador rejeitava a emissão.

**Mudanças em `BACKEND/routers/anuncios.py`:**
- `_build_ml_payload`: novo bloco que extrai NCM/CEST/GTIN/ORIGIN com prioridade `form.attributes (manual) > form.fiscal_json > product.fiscal` e injeta como atributos do item ML. NCM e CEST normalizados (remove `.` e `-`).
- `publish_anuncio`: passa `fiscal_json` e `sku` no `ml_form` antes de chamar `_build_ml_payload`.
- `update_listing`: passa `fiscal_json` no `form` (com fallback no DB: `body.get("fiscal_json") or listing.fiscal_json`), garantindo que anúncios editados também sincronizam fiscal.

**Mapeamento usado:**
- NCM → atributo ML `NCM` (skip se já tiver `NCM` ou `FISCAL_CLASSIFICATION` manual)
- CEST → atributo ML `CEST`
- EAN/GTIN → atributo ML `GTIN` (skip se já tiver `GTIN` ou `EAN`)
- Origem → atributo ML `ORIGIN` (numérico 0-8)

**Deploy:** scp do arquivo + `pm2 restart sistema-drop-backend`. Backend subiu em 02:01:35 UTC, application startup complete, sem stack trace.

**Próximo passo do usuário:** para anúncios já publicados sem fiscal (ex: o que travou a NFe do SKU 5505), abrir o wizard de edição e clicar Salvar — vai disparar o PUT no ML com os atributos fiscais e desbloquear a emissão.

---

## 2026-05-25 — fix(product-categories): índices únicos colidiam em rows com owner NULL

**Erro observado em produção:** `500 Internal Server Error` em `POST /api/v1/product-categories` ao tentar adicionar a categoria "Bolas" (MLB123037) em um segundo produto PG. Toast genérico "Erro ao adicionar categoria" no frontend porque o backend levantou `IntegrityError` sem `detail` HTTP.

**Causa raiz (via `pm2 logs`):** `ORA-00001: unique constraint (ADMIN.UQ_PMC_CMIG) violated`. Os índices únicos da migration 69 — `uq_pmc_catalog (catalog_product_id, marketplace, category_id)` e `uq_pmc_cmig (cmig_product_id, marketplace, category_id)` — indexavam **toda** linha porque `marketplace` e `category_id` são NOT NULL. Resultado: duas linhas PG com `cmig_product_id=NULL`, mesmo marketplace e mesmo `category_id` colidiam entre si (e vice-versa para linhas CMIG no índice catalog).

**Fix:** `Scripts SQL/70_fix_pmc_unique_null_handling.sql` — DROP dos dois índices e CREATE de novos usando `CASE WHEN col IS NULL THEN NULL ELSE col END` em todas as colunas. Quando o owner é NULL, as três colunas da chave do índice ficam NULL → Oracle não indexa a linha ("does not index keys composed entirely of nulls"), eliminando a falsa colisão.

**Como aplicar:** subir o `.sql` para o servidor e rodar `python BACKEND/run_migration.py "Scripts SQL/70_fix_pmc_unique_null_handling.sql"`. Idempotente (sobrevive a re-runs).

**Aplicado em produção 2026-05-25 01:25 UTC** — verificado via `user_indexes`: `UQ_PMC_CATALOG` e `UQ_PMC_CMIG` agora são `FUNCTION-BASED NORMAL` com expressão `CASE WHEN ... IS NULL THEN NULL ELSE col END` nas três colunas. Sem restart do backend necessário (mudança só em DDL).

---

## 2026-05-24 — fix(anuncios): Flex é opt-out automático — check-then-act + alert explicativo

**Erro observado:** `403 Forbidden` (HTML do tengine/WAF) ao clicar ⚡ Flex no anúncio `MLB6833247070`.

**Causa real (correção da premissa anterior):** Flex no ML é **opt-OUT automático** — se a conta tem Flex habilitado e o item é elegível pela categoria/região/atributos, o checkbox no Seller Center já vem **marcado por padrão**. O anúncio já oferece Flex sem ação alguma. O POST `/sites/MLB/shipping/selfservice/items/{id}` é necessário só para REATIVAR Flex que foi explicitamente desativado antes (raro). Chamar POST num item que já tem `self_service_in` causou o 403 do WAF (estado inconsistente).

**Mudanças:**
- `BACKEND/services/ml_service.py`: `set_item_flex` agora faz **check-then-act**:
  1. `GET /items/{id}?attributes=shipping,status` → lê `shipping.tags` atual
  2. Se já no estado desejado → retorna `{already_in_state: True, logistic_type}` SEM chamar `/selfservice`
  3. Senão → chama POST/DELETE com headers completos (`User-Agent`, `Accept`, `Content-Type`)
  4. Detecta resposta HTML do WAF → mensagem amigável citando causas prováveis
- `BACKEND/routers/anuncios.py` (endpoint `/toggle-flex`): usa `already_in_state` da resposta — reutiliza `logistic_type` do GET inicial sem refetch; expõe `_already_in_state: True` no response.
- `FRONTEND/src/views/anuncios/AnunciosView.vue` (`toggleFlex`):
  - Alert na **ativação** explica o opt-out: "O Flex é AUTOMÁTICO… use APENAS se desativou antes".
  - Sem alert extra na desativação.
  - Se `_already_in_state` → `toast.info` "Flex já estava ativo/desativado" em vez de "Flex ativado".

**Outcome:** evita chamada inútil ao endpoint dedicado (que provavelmente causou o 403), educa o usuário sobre o comportamento real do Flex, e mantém compatibilidade total com o caso legítimo (item que estava `self_service_out` e usuário quer reativar).

---

## 2026-05-24 — feat(anuncios): toggle Flex por anúncio via endpoint dedicado

**Correção da refatoração anterior:** o commit `3f8f760` removeu o toggle por item assumindo que Flex era só por conta, mas o Seller Center do ML claramente expõe checkbox de Flex por anúncio. A causa real do erro `field_not_updatable` era usar o endpoint errado (`PUT /items` com `shipping.tags`).

**Endpoint correto encontrado** (doc oficial `developers.mercadolivre.com.br/en_us/mercado-envios-flex`):
- Ativar: `POST /sites/{SITE_ID}/shipping/selfservice/items/{ITEM_ID}`
- Desativar: `DELETE /sites/{SITE_ID}/shipping/selfservice/items/{ITEM_ID}`
- Pré-condição: item deve estar `active`

**Mudanças:**
- `BACKEND/services/ml_service.py`: nova função `set_item_flex(item_id, enable, site_id="MLB")` usando POST/DELETE no endpoint dedicado.
- `BACKEND/routers/anuncios.py`: reintroduzido endpoint `POST /{listing_id}/toggle-flex` (Body `{"enable": true|false}`). Valida: anúncio é ML, não é Full, conta tem Flex, anúncio está publicado. Re-busca o item no ML pós-toggle para gravar `logistic_type` real.
- `FRONTEND/src/views/anuncios/AnunciosView.vue`: botão ⚡ separado do badge informativo, ao lado dos botões pause/reativar. Visível só se `canToggleFlex` (conta tem Flex, não é Full, item publicado, tem platform_item_id). `logisticBadge` permanece como indicador passivo do estado.

**Sem migration, sem mudança de schema.** Endpoints e modelo de `shipping-capabilities` por conta (commit `5b33dbc`) continuam intactos.

---

## 2026-05-24 — refactor(anuncios): Flex é resolvido pelo ML (não por item) + badge informativo

**Erro reportado:** `field_not_updatable` ao tentar habilitar Flex via `PUT /items/{id}` com `shipping.tags=['self_service_in']`.

**Causa raiz (pesquisa do usuário):** Flex (`self_service`) é um **sub-tipo de me2**, não modalidade separada. O Mercado Livre decide automaticamente se um anúncio aparece como Flex baseado em 3 camadas:
1. Conta tem Flex habilitado? → `GET /users/{id}/shipping_preferences` (procurar `mode:me2` com `type:self_service`)
2. Categoria aceita Flex? → `GET /categories/{id}/shipping_preferences`
3. Produto tem atributos exigidos (peso/dimensões)? → `GET /catalog_domains/{dom}/shipping_attributes`

Não há flag booleana por anúncio. A tentativa de `PUT /items` com `shipping.tags` é rejeitada.

**Refatoração:**
- `BACKEND/services/ml_service.py`:
  - `detect_shipping_capabilities()` trocada da heurística items/search para `/users/{id}/shipping_preferences` (oficial). Funciona em contas novas.
  - **Removida** `toggle_item_flex()` (não suportado pela API).
  - **Nova** `get_category_shipping_preferences(category_id)` para uso futuro de validação de elegibilidade.
- `BACKEND/routers/anuncios.py`:
  - **Removido** endpoint `POST /{listing_id}/toggle-flex`.
  - `_build_ml_payload` não envia mais `shipping.tags` (ML rejeita no update e ignora no create).
  - `publish_anuncio` não propaga mais `use_flex`.
- `FRONTEND/src/views/anuncios/AnunciosView.vue`:
  - Botão ⚡ clicável da linha do anúncio → **badge informativo não-clicável** (`Flex`, `ME2`, `Full`) baseado em `listing.logistic_type` real.
  - Função `toggleFlex`/`isFlexActive` → **substituídas** por `logisticBadge(listing)`.
  - Wizard aba 5 (Envio): toggle Flex **removido**. Substituído por: (a) badge read-only do logistic_type atual (no edit); (b) info-box explicando que ML resolve automaticamente, citando se a conta tem Flex/Full disponível.

**Decisões:**
- Endpoints `/accounts/{id}/shipping-capabilities` (GET/PUT/POST refresh) **mantidos** — agora consomem o endpoint oficial em vez da heurística.
- Override manual (`has_flex_override`/`has_full_override`) **mantido** — útil quando endpoint shipping_preferences não retorna info confiável.
- Sem mudança de schema (migration 70 segue válida).

---

## 2026-05-24 — feat(anuncios): modalidades de envio por conta ML (Flex/Full) + botão Flex inline

**Problema:** O wizard de publicação não diferenciava modalidades de envio (ME2, Flex, Full) por conta. Anúncios eram sempre publicados como ME2 cross-docking padrão. Usuários com contas que tinham Flex habilitado precisavam ativar manualmente no Seller Center.

**Solução:**
- `Scripts SQL/70_account_shipping_capabilities.sql` — colunas `has_flex`, `has_full`, `has_flex_override`, `has_full_override`, `shipping_modes_checked_at` em `marketplace_accounts`.
- `BACKEND/models/integration.py` — campos + properties `effective_has_flex`/`effective_has_full` (override > detectado).
- `BACKEND/services/ml_service.py`:
  - `detect_shipping_capabilities(seller_id, token)` — heurística via `GET /users/{id}/items/search?logistic_type=...&limit=1` (se total>0, tem). Limitação documentada: contas novas sem itens precisam override manual.
  - `toggle_item_flex(item_id, enable)` — `PUT /items/{id}` com `shipping.tags=['self_service_in']` para ativar ou `[]` para desativar.
- `BACKEND/routers/integrations.py`:
  - `GET /accounts/{id}/shipping-capabilities` — cache TTL 24h, auto-redetecta se expirou.
  - `POST /accounts/{id}/shipping-capabilities/refresh` — força redetecção.
  - `PUT /accounts/{id}/shipping-capabilities` — override manual de `has_flex_override`/`has_full_override`.
  - Serialização da conta agora retorna `has_flex/has_full` (efetivo).
- `BACKEND/routers/anuncios.py`:
  - `POST /anuncios/{id}/toggle-flex` — ativa/desativa Flex em anúncio existente. Bloqueia em Full e em conta sem Flex.
  - `_build_ml_payload` agora aceita `use_flex` no form (adiciona `shipping.tags=['self_service_in']`).
  - `publish_anuncio` propaga `body.use_flex` ao payload ML.
- `FRONTEND/src/views/anuncios/AnunciosView.vue`:
  - Nova ref `accountCapabilities` carregada via `loadAccountCapabilities()` ao selecionar conta.
  - Aba 5 do wizard: nova seção "Mercado Envios Flex" (toggle), visível só se `accountCapabilities.has_flex`.
  - Default `use_flex=true` ao criar novo anúncio se conta tem Flex (decisão de produto).
  - Edit do listing pré-popula `use_flex` a partir de `listing.logistic_type === 'self_service'`.
  - Novo botão Flex inline na linha do anúncio (⚡): toggle on/off, só aparece se conta tem Flex e anúncio não é Full.

**Decisões:**
- Detecção: híbrida — auto-detecta + admin pode overrider (campo `*_override` nullable: null = usa detectado).
- UX padrão: Flex marcado por padrão quando conta tem (usuário desmarca se não quiser).
- Não tocar em Flex no fluxo de update — Flex tem endpoint próprio (`/toggle-flex`) por separação de concerns.

**Próximo passo:** rodar migration 70 em produção; testar com conta ML real que tem Flex.

---

## 2026-05-24 — feat(products): múltiplas categorias por marketplace + 2 bugfixes ML

**Bugfixes (commits anteriores `cee5fae` e `499a850`):**
- `feat(ean)`: prefixo do EAN gerado mudou de 200 (interno GS1) para 789 (Brasil GS1) — produz códigos no formato público (ex: 7896585254999).
- `fix(anuncios)`: `pictures_json` agora é persistido após publicar anúncio (extrai `pictures` da resposta do ML POST /items ou GET /items/{id}). Antes a tela de gestão ficava sem fotos.
- `fix(anuncios)`: `attributes_json` agora é derivado de `attributes` (lista) quando o frontend só envia um dos dois — antes o campo ficava nulo no DB se o cliente esquecesse a versão serializada.

**Feature: múltiplas categorias de marketplace por produto:**
- `Scripts SQL/69_product_marketplace_categories.sql` — nova tabela `product_marketplace_categories` (FK exclusiva pra `catalog_products` OU `cmig_products`, unique por (owner, marketplace, category_id)). Idempotente.
- `BACKEND/models/product.py` — nova classe `ProductMarketplaceCategory` + relationship `marketplace_categories` em `CatalogProduct`.
- `BACKEND/models/cmig.py` — relationship `marketplace_categories` em `CMIGProduct`.
- `BACKEND/routers/product_categories.py` — CRUD em `/api/v1/product-categories` (GET por owner, POST, PUT, DELETE).
- `BACKEND/main.py` — registro do router.
- `FRONTEND/src/components/products/MarketplaceCategoriesCard.vue` — componente reutilizável que lista categorias salvas, permite adicionar (busca ML pela API existente), expandir e preencher atributos da categoria.
- `FRONTEND/src/views/cmig-products/CmigProductFormView.vue` e `PgProductFormView.vue` — integração do componente (só visível após salvar produto).
- `FRONTEND/src/views/anuncios/AnunciosView.vue` — aba 3 do wizard de publicação ganhou seção "Categorias salvas neste produto" com botões de atalho que pré-preenchem `category_id` + atributos.

**Decisões de produto:**
- Inicialmente só Mercado Livre (Shopee virá depois — estrutura já preparada).
- Atributos pré-cadastrados são template/sugestão; o usuário sempre pode editar/pular na hora de publicar.
- Edição de atributos no momento de publicar **não** sobrescreve o cadastro do produto (vai só pro `ProductListing.attributes_json`).

**Próximo passo:** rodar migration 69 em Oracle; testar fluxo end-to-end (cadastrar categoria num produto PG → publicar anúncio reutilizando atalho → confirmar atributos chegam ao ML).

---

## 2026-05-21 — feat(products): suporte completo a produto Simples, Kit e Variante

**Mudanças:**

**Etapa 1 — Banco + Modelos:**
- `Scripts SQL/64_product_type.sql` — coluna `product_type` em `catalog_products`; backfill `kit` onde `is_composite=1`.
- `Scripts SQL/65_product_listing_variants.sql` — nova tabela `product_listing_variants` (mapeamento `listing_id` + `ml_variation_id` ↔ `catalog_variant_id`).
- `Scripts SQL/66_order_items_ml_variation.sql` — coluna `ml_variation_id` em `order_items`.
- `BACKEND/models/product.py` — `product_type` em `CatalogProduct`, nova classe `ProductListingVariant`, relationship `listing_variants` em `ProductListing`.
- `BACKEND/models/order.py` — `ml_variation_id` em `OrderItem`.

**Etapa 2 — Kit: dedução de estoque idempotente:**
- `BACKEND/services/fiscal/stock_calculator.py` — `calculate_pg_product_stock()` soma consumo de kits por componente via SQL; `affected_products_from_order()` inclui componentes de kits; `recompute_after_order_change()` recalcula estoque virtual do kit (min de componentes); nova função `recompute_variant_stocks_for_order()`.

**Etapa 3 — Variante: publicação no ML:**
- `BACKEND/services/ml_service.py` — `build_variations_payload()`, `sync_kit_stock_to_ml()`, `sync_variant_stocks_to_ml()`.
- `BACKEND/routers/anuncios.py` — suporte a `variations` no payload de publicação; salva `ProductListingVariant` pós-publicação via `_save_listing_variants()`; reconcilia variantes na importação; endpoint `POST /{listing_id}/sync-variant-stocks`.

**Etapa 4 — Variante: webhook + scheduler:**
- `BACKEND/services/webhook_service.py` — popula `catalog_variant_id` e `ml_variation_id` em `OrderItem` ao processar pedido ML com `variation_id`.
- `BACKEND/tasks/sync_stock.py` — roteia listings com `listing_variants` para `sync_variant_stocks_to_ml`.

**Etapa 5 — Frontend:**
- `SupplierProductListView.vue` — badge `VARIANTE` (badge-info).
- `PgProductFormView.vue` — seletor de tipo (Simples / Kit / Variante) ao criar; redireciona para edição após criar variante.
- `ProductVariantsCard.vue` — coluna estoque com badge colorido (verde/amarelo/vermelho); coluna ML ID.
- `AnunciosView.vue` — tabela inline de variantes locais (SKU, cor, tam., volt., estoque, ML Var. ID); botão "Sincronizar estoque por variação" (`fa-swatchbook`).

**Serialização:** `_serialize_listing` inclui `listing_variants[]` com `catalog_variant` aninhado.

**Verificação:** `pytest tests/ -m "not integration" --ignore=tests/test_orders.py` — 9/9 passando. `npm run build` — sem erros.

---

## 2026-05-18 — feat(anuncios): sync-stock envia estoque do produto para o marketplace

**Commit:** `5102fc7`

**Mudancas:**
- `BACKEND/routers/anuncios.py` — novo endpoint `POST /anuncios/sync-stock`: percorre listings publicados com `stock_mode=product`, le `stock_quantity` do CMIG/PG vinculado e atualiza a quantidade no ML (via `ml_service.update_item_stock`) ou Shopee. Pula `fixed`, `fulfillment`, sem `platform_item_id` e sem produto vinculado. Retorna `{updated, skipped, errors, error_details}`. Idempotente.
- `FRONTEND/src/views/anuncios/AnunciosView.vue` — botao "Sincronizar Estoque" (verde, `fa-sync-alt`) com spinner durante execucao, toast de resultado e recarga da lista.

**Deploy:** git pull + pm2 restart + npm run build no servidor. Concluido sem erros as 14:19 (servidor).

---

## 2026-05-18 — Refactor: estoque como derivação de eventos (`stock_quantity` vira cache)

**Motivação:** Conceito anterior tratava `stock_quantity` como fonte de verdade e mutava direto durante NFe finalize. Usuário pediu refactor: estoque deve ser **calculado** a partir de NFes + Pedidos; o campo passa a ser apenas cache do resultado.

**Decisões confirmadas:**
- Regra de double-count: **Pedido sempre conta; NFe-out vinculada a pedido NUNCA conta** (`Order.invoice_id == invoice.id` = vinculado).
- Ajustes manuais via NFe de entrada/saída — sem tabela própria.
- Cache atualizado por evento (não recálculo em cada leitura).
- Reservados (handling/ready_to_ship) NÃO contam no cache físico (são compromissos).

**Mudanças:**

### Backend — novo helper canônico
- [BACKEND/services/fiscal/stock_calculator.py](BACKEND/services/fiscal/stock_calculator.py) — **NOVO**:
  - `calculate_cmig_product_stock(cp, db)` / `calculate_pg_product_stock(pg, db)`: replay determinístico a partir de zero. Não muta cache.
  - `recompute_cmig_product_stock(id, db)` / `recompute_pg_product_stock(id, db)`: chamam calculate + atualizam o campo `stock_quantity`.
  - `affected_products_from_invoice(inv, db)`, `affected_products_from_order(order, db)`: helpers pra identificar quais CMIG/PG são afetados por um evento (resolve via cmig_product_id, source_type+SKU/EAN, ProductListing).
  - `recompute_after_invoice_change(inv, db)`, `recompute_after_order_change(order, db)`: orquestram detect + recompute.
  - `recompute_all_stock(db)`: backfill global.

### Backend — refator
- [BACKEND/services/stock_history.py](BACKEND/services/stock_history.py): StockEvent ganha `invoice_linked_to_order`. `_fetch_nfe_events_for_cmig_product` e `_fetch_direct_pg_events` pré-computam quais invoices têm `Order.invoice_id` apontando. `_apply_split_replay` pula NFe-out linked no cálculo.
- [BACKEND/routers/invoices.py](BACKEND/routers/invoices.py) `_apply_stock_movement` agora chama `recompute_after_invoice_change` (deixa de mutar direto). `_update_stock_from_items` (XML import) também redireciona ao recompute.
- [BACKEND/services/fiscal/dfe_service.py](BACKEND/services/fiscal/dfe_service.py) `update_stock_from_invoice` (webhook de manifestação) idem.
- [BACKEND/services/webhook_service.py](BACKEND/services/webhook_service.py) `_apply_shipment_to_order` retorna bool de status_changed. Quando muda, dispara `recompute_after_order_change` — pedidos shipped/delivered/cancelled atualizam estoque automaticamente.

### Backend — endpoints novos
- `POST /cmigs/{cmig_id}/products/{id}/recalculate-stock` (qualquer user autenticado).
- `POST /pg/{id}/recalculate-stock`.
- `POST /pg/recalculate-all-stock` (admin) — recalcula tudo. Útil pra backfill pós-deploy.

### Frontend
- [CmigProductFormView.vue](FRONTEND/src/views/cmig-products/CmigProductFormView.vue) e [PgProductFormView.vue](FRONTEND/src/views/supplier/PgProductFormView.vue): botão "Recalcular estoque" (azul, ícone `fa-calculator`) no header em modo edição. Toast informa `old → new (delta)`.

**Comportamento esperado:**
- Após NFe finalizada: estoque dos CMIGs/PGs afetados é recalculado a partir do zero usando todos os eventos. Resultado salvo em `stock_quantity`.
- Após pedido marketplace mudar pra shipped/delivered/cancelled: webhook dispara recompute dos produtos afetados.
- `stock_quantity` continua sendo lido nas listagens (rápido). Pra forçar reconciliação, usuário usa o botão.

**Pendente em produção:**
- Pull + restart backend.
- **CRÍTICO**: rodar `POST /pg/recalculate-all-stock` (admin) após deploy pra resetar cache de todos os produtos com a nova fórmula.

**Verificação:** import backend OK. `npm run build` → `✓ built in 16.90s`.

**Limitações documentadas:**
- Performance: recompute de 1 produto faz O(N) eventos. Ok pra N pequeno. Job futuro: índice em `invoice_items(cmig_product_id, source_type)` e `orders(cmig_id, shipment_status, shipped_at)`.
- Ajuste de estoque "manual" (não via NFe) deixa de funcionar — passa a exigir NFe. `PUT /pg/{id}/stock` mantido como deprecated pra compat.

---

## 2026-05-17 — Fix: estoque PG não atualizava ao finalizar NFe + endpoint reaplicar

**Motivação:** Usuário criou NFe entrada #44 com mix de itens CMIG e PG. Só o CMIG teve estoque atualizado; os itens PG foram silenciosamente ignorados. Causa: 3 funções backend (`_apply_stock_movement`, `_update_stock_from_items`, `dfe_service.update_stock_from_invoice`) só buscavam `CMIGProduct` por `cmig_product_id` ou EAN. `CatalogProduct.stock_quantity` nunca era tocado por NFe.

**Mudanças:**

### Backend
- [BACKEND/services/fiscal/stock_apply.py](BACKEND/services/fiscal/stock_apply.py) — **NOVO** helper compartilhado:
  - `apply_stock_for_item(item, sign, cmig_id, db)` — roteia por `source_type`. PG: match SKU→EAN no `CatalogProduct`. CMIG: FK ou EAN no `CMIGProduct` (preserva comportamento legacy quando `source_type` é NULL).
- [BACKEND/routers/invoices.py](BACKEND/routers/invoices.py):
  - `_apply_stock_movement` (usado por `finalize-no-sefaz` e Focus webhook) e `_update_stock_from_items` (XML import) refatorados pra usar o helper. Retornam `matched_cmig + matched_pg`.
  - **NOVO** endpoint `POST /invoices/{id}/reapply-stock` (admin/UGO). Reaplica **APENAS itens com `source_type='pg'`** — evita dupla contagem em itens CMIG que já contaram. Registra evento `stock_reapplied` no histórico.
- [BACKEND/services/fiscal/dfe_service.py](BACKEND/services/fiscal/dfe_service.py) — `update_stock_from_invoice` (webhook de manifestação) também usa o helper.
- [Scripts SQL/63_invevt_stock_reapplied.sql](Scripts SQL/63_invevt_stock_reapplied.sql) — **NOVO** migration idempotente que adiciona `stock_reapplied` à CHK do `invoice_events.event_type`.
- [BACKEND/services/stock_history.py](BACKEND/services/stock_history.py):
  - StockEvent ganha `item_id: Optional[int]` pra dedup confiável.
  - **NOVO** `_fetch_direct_pg_events(pg_product, db)` — busca `InvoiceItem` com `source_type='pg'` que casam por SKU ou EAN com o PG.
  - `replay_stock_events_for_pg_product` agrega: NFes dos CMIGs vinculados + NFes diretas em PG. Dedup por `item_id` evita duplicação quando um item match por ambos caminhos.

### Frontend
- [FRONTEND/src/views/fiscal/InvoiceDetailView.vue](FRONTEND/src/views/fiscal/InvoiceDetailView.vue) — novo botão "Reaplicar estoque PG" (amarelo, ícone `fa-sync-alt`):
  - Aparece em notas `finalized`/`authorized` que têm pelo menos 1 item `source_type='pg'`.
  - Confirm prompt explica que só PG é reaplicado.
  - Chama `POST /invoices/{id}/reapply-stock`. Toast informa `N items PG atualizados` ou `nenhum item PG`.

**Pendente em produção:**
- Rodar `Scripts SQL/63_invevt_stock_reapplied.sql` no Oracle ATP.
- Reiniciar PM2.
- Rodar reapply na NFe #44 pra corrigir o estoque dos SKUs 5505 (+8) e 5508 (+26) no PG.

**Verificação:**
- `python -c "from services.fiscal.stock_apply import apply_stock_for_item"` → OK.
- `python -c "import routers.invoices"` → OK. Endpoint `/{invoice_id}/reapply-stock` registrado.
- `npm run build` → `✓ built in 8.16s`.

**Limitação documentada:**
- Reapply é narrow (só PG). Se um item CMIG falhou por outro motivo (EAN errado, produto deletado), reapply não corrige — usuário tem que reverter/recriar a NFe.
- NFes futuras (após o fix) processam CMIG + PG na 1ª chamada; reapply só é necessário em NFes antigas.

---

## 2026-05-17 — Anúncio: fallback de foto + recalcular frete quando dims presentes

**Motivação:** Usuário reportou anúncio sem foto na listagem (embora o produto vinculado tenha foto) e mensagem "sem dims." mesmo com dimensões preenchidas no card (cache de custos antigo retornou 0 e ficou preso).

**Mudanças:** [FRONTEND/src/views/anuncios/AnunciosView.vue](FRONTEND/src/views/anuncios/AnunciosView.vue):
- `listingThumb(a)`: helper que retorna `a.thumbnail` OU primeira imagem de `cmig_product.images` OU `catalog_product.images`. Funciona porque o serializer já retorna esses campos (mudança da rodada anterior).
- `hasDimensions(a)`: helper boolean.
- Bloco de frete vendedor agora tem 3 estados:
  - `shipping_cost > 0` → mostra valor
  - `!hasDimensions(a)` → "sem dims."
  - `hasDimensions(a) && shipping_cost == 0` → "recalcular" (clicável, ícone sync) com tooltip explicando que ML retornou 0
- `forceRefreshCosts(listing)`: limpa cache local, chama `POST /anuncios/{id}/refresh-costs` e refetcha `/costs`. Toast informa o resultado (valor recalculado ou aviso se ML continuou retornando 0).

**Backend não precisou de mudança** — `_serialize_listing` (rodada anterior) já retornava `cmig_product.images`/`catalog_product.images`, e o endpoint `/refresh-costs` já existia.

**Verificação:** `npm run build` → `✓ built in 16.06s`.

---

## 2026-05-17 — Permitir editar SKU em CMIG/PG/Anúncio + cascata pra itens vinculados

**Motivação:** Forms de Produto CMIG e PG bloqueavam o campo SKU em edição (`:disabled="isEdit"`). Usuário precisava poder alterar. Adicionalmente: quando um produto está vinculado entre CMIG ↔ PG ↔ Anúncios, alterar o SKU em um lugar deve perguntar se quer propagar para os outros.

**Mudanças:**

### Backend
- [BACKEND/schemas/cmig.py](BACKEND/schemas/cmig.py) — `CMIGProductUpdate` ganha `sku_cmig` e `cascade_sku_to_linked`.
- [BACKEND/routers/cmigs.py](BACKEND/routers/cmigs.py) — `update_cmig_product` valida unicidade do novo SKU (dentro da CMIG) e, se `cascade=True`, propaga para `CatalogProduct.sku` do PG vinculado + todos `ProductListing.sku` com `cmig_product_id` = X. Retorna `_cascade: {pg_updated, listings_updated}`.
- [BACKEND/routers/supplier_products.py](BACKEND/routers/supplier_products.py) — `update_product` aceita mudança de SKU (não estava na lista de campos atualizáveis), valida unicidade global e, se cascata, propaga para todos os `CMIGProduct.sku_cmig` vinculados (com check de unicidade por CMIG) + todos `ProductListing.sku` com `catalog_product_id` = X.
- [BACKEND/routers/anuncios.py](BACKEND/routers/anuncios.py) — `update_listing` ganha cascata: se `cascade_sku_to_linked` e o listing tem `cmig_product_id`/`catalog_product_id`, atualiza o produto vinculado (com check de unicidade). Em todos os casos: erro 409 se houver conflito.

### Frontend
- [CmigProductFormView.vue](FRONTEND/src/views/cmig-products/CmigProductFormView.vue), [CmigCompositeFormView.vue](FRONTEND/src/views/cmig-products/CmigCompositeFormView.vue), [PgProductFormView.vue](FRONTEND/src/views/supplier/PgProductFormView.vue), [PgCompositeFormView.vue](FRONTEND/src/views/supplier/PgCompositeFormView.vue): removido `:disabled="isEdit"` no input SKU.
- CMIG e PG simple forms guardam `originalSku` no load; ao salvar com SKU alterado, `confirm()` pergunta sobre cascata. Toast indica o que foi propagado.
- [AnunciosView.vue](FRONTEND/src/views/anuncios/AnunciosView.vue) — wizard salva `originalSku` ao abrir edição; pergunta sobre cascata pro produto vinculado (CMIG ou PG) ao salvar com SKU mudado.

**Importante:**
- Cascata é **opt-in** (usuário responde no prompt).
- Backend aborta com 409 se a propagação criar duplicidade em qualquer destino. Mensagem informa qual conflito.

**Verificação:** `python -c "from schemas.cmig import CMIGProductUpdate; ..."` → schema OK. `npm run build` → `✓ built in 16.98s`.

---

## 2026-05-17 — Fix: SKU não enviado pro ML como SELLER_SKU

**Motivação:** Usuário reportou que o SKU não estava sendo enviado pro ML, mesmo configurado no produto/listing.

**Causa raiz:** `_build_ml_payload` não incluía o atributo `SELLER_SKU` no payload. Além disso, o `form` montado no fluxo de update não passava o `sku` do listing/body para o builder.

**Mudanças:** [BACKEND/routers/anuncios.py](BACKEND/routers/anuncios.py):
- `_build_ml_payload`: lê SKU em cascata (`form.sku` → `product.sku_cmig` → `product.sku`) e adiciona como `{"id": "SELLER_SKU", "value_name": str(sku_value)}` aos attributes, se ainda não estiver presente.
- Form do update_listing: passa `sku`, `model`, dimensões (`height_cm`/`width_cm`/`length_cm`/`weight_kg`) pro `_build_ml_payload`. Antes esses campos só funcionavam no fluxo de create.

**Verificação:** import backend OK.

---

## 2026-05-17 — Fix: ML rejeitando fotos com URL relativa (item.picture.invalid)

**Motivação:** Update de anúncio ML retornava erro `item.picture.invalid` em `item.variations.picture_ids` porque enviávamos URLs relativas (`/static/uploads/...`) como `pictures[].source`. ML precisa de URLs HTTPS públicas pra baixar a imagem.

**Causa raiz dupla:**
1. **Serializer de listing (anuncios.py)** retornava `cmig_product` e `catalog_product` sem `images` nem `cmig_id` — o frontend não tinha como mostrar nem refazer fotos. Resolvido na rodada anterior.
2. **`_build_ml_payload`** enviava `{"source": url}` direto, sem absolutizar. URLs relativas chegavam no ML como inválidas, e o estado de variações com `picture_ids` apontando pra essas URLs também não validava.

**Mudanças:**
- [BACKEND/config.py](BACKEND/config.py) — nova setting `PUBLIC_BASE_URL` (default `""`), documentada como "URL pública do backend pra absolutizar imagens em integrações externas (ex.: `https://ecommerce.madeingroup.com.br`)".
- [BACKEND/routers/anuncios.py](BACKEND/routers/anuncios.py):
  - Helper `_absolutize_image_url(url)`: se URL já tem `http(s)://`, retorna como está. Se relativa e `PUBLIC_BASE_URL` está setado, prefixa. Se sem base configurada, retorna original (dev).
  - `_build_ml_payload`: agora usa o helper em `pictures[].source`.
  - Fluxo de update no `update_listing`: quando há `pictures` no payload **e** o listing tem `variations_json`, adiciona `variations: [{id, picture_ids: []}]` pra limpar `picture_ids` inválidos das variations existentes no ML. As variations passam a herdar as fotos do top-level item.

**Pendente em produção:** setar `PUBLIC_BASE_URL=https://ecommerce.madeingroup.com.br` no `.env` do servidor. Sem isso, o helper não tem como absolutizar e ML continua rejeitando.

**Verificação:** import backend OK. Teste do helper: `/static/x.jpg` + base url → `https://...x.jpg`; URL absoluta passa direto; None não crasha.

---

## 2026-05-17 — Gerador EAN-13 + filtro/ordenação em listas + refresh de fotos no anúncio

**Motivação:** 3 features pedidas pelo usuário: (1) gerar EAN-13 automaticamente nos forms de Produto CMIG/PG, (2) filtrar e ordenar listas de produtos por categoria/nome/SKU, (3) na edição de anúncio, botão pra buscar fotos atualizadas do produto vinculado.

**Mudanças:**

### 1) Gerador EAN-13
- [FRONTEND/src/utils/ean.js](FRONTEND/src/utils/ean.js) — **NOVO** utilitário. Gera EAN-13 com prefixo **200** (faixa GS1 reservada pra uso interno do varejista — não conflita com produtos comerciais reais). Inclui `ean13Checksum`, `generateEan13` e `isValidEan13`.
- [FRONTEND/src/views/cmig-products/CmigProductFormView.vue](FRONTEND/src/views/cmig-products/CmigProductFormView.vue) e [PgProductFormView.vue](FRONTEND/src/views/supplier/PgProductFormView.vue) — botão `fa-magic` ao lado do input EAN, com tooltip "Gerar código EAN-13 interno (prefixo 200)".
- **Validação**: testes locais geraram 100/100 EANs válidos com prefixo correto.

### 2) Filtro + ordenação nas listas
- [CmigProductListView.vue](FRONTEND/src/views/cmig-products/CmigProductListView.vue) e [SupplierProductListView.vue](FRONTEND/src/views/supplier/SupplierProductListView.vue):
  - Nova barra de filtros (background cinza-claro, abaixo do header do card):
    - Campo de busca livre (matches `title` OR `sku`/`sku_cmig`).
    - Dropdown de categoria (carregado de `GET /catalog/categories` ao montar).
    - Dropdown de ordenação: Nome (A-Z, Z-A), SKU (A-Z, Z-A), Categoria (A-Z).
    - Contador de resultados à direita.
  - Reatividade: tudo via `computed`, sem chamadas extras à API ao mudar filtro.

### 3) Refresh de fotos do produto no anúncio
- [AnunciosView.vue](FRONTEND/src/views/anuncios/AnunciosView.vue):
  - Botão "Atualizar fotos" (`fa-sync-alt`) na Aba 4 (Fotos) do wizard, ao lado do título "Fotos do produto vinculado".
  - Re-fetch do produto via `GET /cmigs/{cmig_id}/products/{id}` (CMIG) ou `GET /pg/{id}` (PG) e atualiza `wf.selectedProduct.images` reativamente — `productImages` computed reflete imediatamente.
  - Toast indica quantas fotos novas apareceram (diff por URL contra o estado anterior).
  - Disabled durante fetch + spinner.

**Backend**: nenhuma mudança — endpoints já existiam.

**Verificação:** `npm run build` → `✓ built in 19.61s`. Teste de geração EAN: 100/100 válidos, prefixo `200`.

---

## 2026-05-16 — Ordenação descendente (mais recente primeiro)

**Motivação:** Tabela mostrava eventos em ordem cronológica ascendente (mais antigo no topo). Usuário prefere ordem descendente para ver primeiro o que aconteceu por último.

**Mudanças:**
- [BACKEND/routers/cmigs.py](BACKEND/routers/cmigs.py) e [BACKEND/routers/supplier_products.py](BACKEND/routers/supplier_products.py) — adicionado `visible_events.reverse()` antes do `return`. O replay continua rodando cronologicamente (necessário pra calcular split CMIG/PG e `running_available`); só a lista enviada pro frontend fica invertida.

**Verificação:** import backend OK.

---

## 2026-05-16 — Tabela do modal compactada em 1 linha por evento + ID Anúncio + Saldo Disponível

**Motivação:** Modal CMIG/PG estava verboso (cada pedido ocupava 2-3 linhas), coluna "Pessoa" mostrava nome do comprador (pouco útil pra reconciliação), e a coluna de saldo era "Saldo NFe" (não refletia o disponível considerando pedidos).

**Mudanças:**
- [BACKEND/services/stock_history.py](BACKEND/services/stock_history.py) — adicionado campo `item_ml_item_id` ao `StockEvent`, populado a partir de `OrderItem.ml_item_id` (ID do anúncio no marketplace, ex.: `MLB1234567890`).
- [BACKEND/routers/cmigs.py](BACKEND/routers/cmigs.py) — endpoint agora retorna `running_available` por evento (= NFe acumulado − pedidos pendentes acumulados sem NFe-out finalizada). Walk cronológico em um único pass.
- [BACKEND/routers/supplier_products.py](BACKEND/routers/supplier_products.py) — idem, com semântica de PG (acumulado de NFes dos CMIGs vinculados − overflow PG pendente).
- [FRONTEND/src/views/cmig-products/CmigProductListView.vue](FRONTEND/src/views/cmig-products/CmigProductListView.vue) & [SupplierProductListView.vue](FRONTEND/src/views/supplier/SupplierProductListView.vue):
  - Modal `max-width: 95vw` (mais largo lateralmente).
  - Tabela inteira: `white-space: nowrap; font-size: 13px` — cada linha numa só.
  - **Coluna Data**: data+hora numa só linha, font-size 12px. Formato `dd/MM/yy HH:mm`. Nova função `formatDateTimeOneLine`.
  - **Coluna Referência** (orders): removida palavra "Pedido", número + status na mesma linha com separador `·`, font-size 12px. Badge "reservado" inline.
  - **Coluna Pessoa / Anúncio**: pra orders mostra `<code>{{ ml_item_id }}</code>`; pra NFes continua mostrando `person_name`. Header renomeado.
  - **Coluna Item**: começa com `SKU: XXXX - <titulo>` em uma linha, com truncamento via `max-width + overflow:hidden + text-overflow:ellipsis`. Tooltip mostra título completo.
  - **Coluna Qtd**: overflow info (`+N PG` ou `N CMIG`) inline ao lado da quantidade, não mais em segunda linha.
  - **Coluna Saldo Disponível** (renomeada de "Saldo NFe"): mostra `running_available` calculado pelo backend. Aparece em TODAS as linhas (NFe + Pedidos), antes só NFes tinham valor.

**Verificação:** `python -c "from services.stock_history import StockEvent; ..."` → `item_ml_item_id` registrado. `npm run build` → `✓ built in 7.25s`. 205 módulos transformados.

---

## 2026-05-16 — Polimento UI: Saldo Físico, logo Mercado Livre, limpeza de labels

**Motivação:** Após refinar a semântica de statuses, a UI ficou com 8 cards (alguns redundantes), labels em inglês e texto puro no lugar do logo do marketplace. Polimento solicitado pelo usuário.

**Mudanças:**
- [FRONTEND/public/marketplaces/](FRONTEND/public/marketplaces/) — **NOVA** pasta com README documentando onde salvar os PNGs dos marketplaces. Arquivos esperados: `mercadolivre.png` (logo completo), `mercadolivre-icon.png` (só o handshake, usado em badges), `shopee.png` e `shopee-icon.png` (futuro). Usuário precisa salvar manualmente.
- [FRONTEND/src/views/cmig-products/CmigProductListView.vue](FRONTEND/src/views/cmig-products/CmigProductListView.vue):
  - Removidos cards "Saldo NFe Atual" (preto) e "Saldo Final" (azul-água).
  - Novo card "Saldo Físico" (azul-água) com fórmula `Saldo Inicial + Entradas NFe − Saídas NFe − Pedidos` (computed property `saldoFisico`).
  - Card "Movimentado s/ NFe (shipped/delivered)" renomeado pra "Pedidos".
  - "Reservado (handling/ready)" → "Reservado".
  - Linhas de pedido: removida etiqueta "mov. s/ NFe" (badge laranja). Etiqueta "reservado" mantida pra handling/ready_to_ship.
  - Coluna "Origem" pra ML: usa `<img :src="mlLogoUrl">` apontando pra `/marketplaces/mercadolivre-icon.png`. Fallback automático pro badge amarelo com texto "ML" se o arquivo não carregar (via `@error`).
- [FRONTEND/src/views/supplier/SupplierProductListView.vue](FRONTEND/src/views/supplier/SupplierProductListView.vue) — mesmos cleanups de labels em inglês, mesma substituição do badge ML por imagem, remoção da etiqueta "mov. s/ NFe" das linhas. Cards específicos do PG mantidos.

**Layout final do modal CMIG (2 linhas):**
- Linha 1 (4 cards): Saldo Inicial · Entradas NFe · Saídas NFe · **Saldo Físico** (NOVO, azul-água).
- Linha 2 (3 cards): Reservado · Pedidos · Disponível.

**Pendente do usuário:** salvar `mercadolivre-icon.png` em [FRONTEND/public/marketplaces/](FRONTEND/public/marketplaces/) (com a imagem só do handshake amarelo) e `mercadolivre.png` (logo completo) para uso futuro. Até salvar, o fallback de texto/cor cobre.

**Verificação:** `npm run build` → `✓ built in 7.14s` (após troca de `src` estático por `:src` dinâmico, que Vite não tenta resolver no bundle).

---

## 2026-05-16 — Refinamento: separar pedidos reservados (handling/ready) de movimentados (shipped/delivered)

**Motivação:** Na primeira versão da feature, "Reservado em Pedidos" incluía qualquer pedido shipped/delivered sem NFe — confuso porque esses já são saídas físicas definitivas. Correção: `handling` e `ready_to_ship` = reservado (estoque comprometido mas ainda no galpão); `shipped` e `delivered` = movimentado em definitivo (goods já saíram). Adicionar ícone de marketplace na coluna "Origem".

**Mudanças:**
- [BACKEND/services/stock_history.py](BACKEND/services/stock_history.py) — `SHIPPED_STATUSES` expandido pra `('handling', 'ready_to_ship', 'shipped', 'delivered')` (todos os 4 contam pra split CMIG↔PG). Novos: `RESERVED_STATUSES`, `DEFINITIVE_STATUSES`. `StockEvent` ganha flags `is_reserved` e `is_definitive` populadas a partir de `Order.shipment_status`.
- [BACKEND/routers/cmigs.py](BACKEND/routers/cmigs.py) — agregados refinados: `reserved_in_pending_orders` agora conta APENAS handling/ready_to_ship; novo `moved_in_orders_no_nfe` conta shipped/delivered sem NFe-out finalizada. `current_balance_available = NFe Atual − reservado − mov_sem_nfe`. Period split em `period_out_orders_reserved` e `period_out_orders_definitive`.
- [BACKEND/routers/supplier_products.py](BACKEND/routers/supplier_products.py) — mesma refatoração com sufixo `_pg`.
- [FRONTEND/src/views/cmig-products/CmigProductListView.vue](FRONTEND/src/views/cmig-products/CmigProductListView.vue) — segunda linha de cards reorganizada: Saldo NFe Atual · Reservado (handling/ready) · Movimentado s/ NFe (shipped/delivered) · Disponível. Coluna "Origem" agora mostra ícone de marketplace: badge amarelo `#FFE600` com "ML" pra Mercado Livre, badge laranja `#EE4D2D` com "Shopee", ambos com `fa-shopping-bag`. Badge "reservado" só pra pedidos handling/ready_to_ship; badge "mov. s/ NFe" pra shipped/delivered sem NFe-out.
- [FRONTEND/src/views/supplier/SupplierProductListView.vue](FRONTEND/src/views/supplier/SupplierProductListView.vue) — mesma estrutura de cards e ícones de marketplace.

**Verificação:** smoke test com 4 statuses + NFe sem PG → reserved=5 (handling 2 + ready 3), mov_no_nfe=4 (shipped sem NFe), disponível=1 (10−5−4). `npm run build` → `✓ built in 7.02s`. Imports backend OK.

---

## 2026-05-16 — Movimentação de estoque considera pedidos marketplace (split CMIG↔PG)

**Motivação:** Os endpoints de movimentação de estoque (CMIG e PG) consideravam apenas NFes — pedidos despachados/entregues mas sem NFe vinculada ficavam invisíveis. Estoque "reservado" não era refletido no relatório. Nova regra: pedidos com `shipment_status IN ('shipped','delivered')` contam como saída; se o CMIGProduct tem vínculo com PG, a saída debita CMIG enquanto há saldo projetado positivo; overflow vai para PG.

**Mudanças:**
- [BACKEND/services/stock_history.py](BACKEND/services/stock_history.py) — **NOVO**. Centraliza a lógica em `StockEvent` dataclass + `replay_stock_events_for_cmig_product` + `replay_stock_events_for_pg_product`. Matching em cascata OrderItem → CMIGProduct via (1) ProductListing.cmig_product_id, (2) OrderItem.sku, (3) OrderItem.catalog_product_id = pg_product_id. Replay cronológico aplica regra do split. Função PG itera CMIGs vinculados e concatena.
- [BACKEND/routers/cmigs.py](BACKEND/routers/cmigs.py) — endpoint `GET /cmigs/{id}/products/{pid}/stock-movements` agora delega ao helper. Retorna campos novos: `current_balance_nfe`, `reserved_in_pending_orders`, `current_balance_available`, `period_in_nfe`/`period_out_nfe`/`period_out_orders`, `has_pg_link`, `pg_product_id`. Movimentações incluem source ∈ {`nfe_in`, `nfe_out`, `order`}.
- [BACKEND/routers/supplier_products.py](BACKEND/routers/supplier_products.py) — endpoint `GET /pg/{id}/stock-movements` idem, com `current_balance_pg`, `reserved_in_pending_orders_pg`, `current_balance_available`. Pedidos só aparecem com `qty_to_pg > 0` (overflow real).
- [FRONTEND/src/views/cmig-products/CmigProductListView.vue](FRONTEND/src/views/cmig-products/CmigProductListView.vue) — modal reorganizado em 2 linhas de cards: (1) NFe-only [Inicial · Entradas NFe · Saídas NFe · Final] (2) Cenário com pedidos [NFe Atual · Reservado · Disponível · Saídas Pedidos]. Coluna "Origem" com 3 badges (NFe Entrada/Saída/Pedido). Linhas de pedido mostram plataforma, status de envio, comprador e overflow PG se houver. `Saldo NFe` em linhas de pedido aparece como `—` (pedidos não mudam stock_quantity).
- [FRONTEND/src/views/supplier/SupplierProductListView.vue](FRONTEND/src/views/supplier/SupplierProductListView.vue) — mesmo padrão, com "Saldo PG Atual" e "PG Disponível" no card. Pedidos exibidos com badge "{N} em CMIG" pra mostrar qual fração foi pra CMIG antes do overflow.

**Não muda `stock_quantity`** — camada puramente reporting. Sem migration SQL.

**Verificação executada:**
- `python -c "from services.stock_history import ..."` → imports OK.
- Testes lógicos do replay com 3 cenários (com PG / sem PG / misto NFe+order) — todos batem com o esperado.
- `npm run build` em FRONTEND/ → `✓ built in 7.46s`. Bundle CmigProductListView 17.7kB → 21.8kB.

**Limitações documentadas:** ajustes manuais de `stock_quantity` continuam fora do histórico. Pedidos sem `shipped_at` usam `created_at` como fallback. Edição direta de PG.stock_quantity também fora.

---

## 2026-05-15 — Histórico de movimentação de estoque no card de Produtos PG

**Motivação:** Replicar a feature do CMIG (botão fa-history + modal) na tela de Produtos Gerais (PG). Estoque PG é alterado manualmente — não há NFe que mova `CatalogProduct.stock_quantity` diretamente — então o histórico é reconstruído **agregando movimentações dos CMIGProducts vinculados** ao PG via `CMIGProduct.pg_product_id`.

**Mudanças:**
- [BACKEND/routers/supplier_products.py](BACKEND/routers/supplier_products.py) — novo endpoint `GET /pg/{product_id}/stock-movements?start_date=&end_date=`. Encontra todos os `CMIGProduct WHERE pg_product_id = X`, junta com `InvoiceItem ← Invoice ← Person ← CMIG`, filtra por status `authorized|finalized` + `stock_updated=True`. Match por `cmig_product_id IN linked_cmigs` OU por EAN do PG (itens legados). Retorna `initial_balance`, `final_balance`, `current_balance`, `period_in/out/net`, lista de movimentações com `cmig_name`, `cmig_product_sku`, `cmig_product_title` e saldo acumulado, e `linked_cmig_count` (para o frontend exibir mensagem específica se zero).
- [FRONTEND/src/views/supplier/SupplierProductListView.vue](FRONTEND/src/views/supplier/SupplierProductListView.vue) — botão `fa-history` em cada linha (entre "Duplicar" e "Desativar"). Modal `modal-xl` com filtros de data (presets 7d/30d/90d/1ano/Tudo), 5 cards de saldo e tabela com coluna "CMIG / Produto" mostrando qual CMIG originou a movimentação. Mensagem específica quando o PG não tem nenhum CMIG vinculado.

**Limitação documentada:** edições manuais via `PUT /pg/{id}/stock` não aparecem como linhas — ficam absorvidas no `initial_balance`. Limitação similar à do CMIG.

**Verificação:** `python -c "import routers.supplier_products as m"` → endpoint `GET /{product_id}/stock-movements` registrado. `npm run build` em FRONTEND/ → `✓ built in 7.00s`.

---

## 2026-05-15 — Fix: SKU não aparecia em itens antigos de NFe

**Motivação:** Após a migration 61, itens já existentes continuavam sem mostrar o SKU no card "Itens" do detalhe da NFe — a nova coluna estava NULL pra todo histórico anterior. Só itens cadastrados após a migration eram preenchidos pelo picker.

**Mudanças:**
- [Scripts SQL/62_backfill_invoice_items_sku.sql](Scripts SQL/62_backfill_invoice_items_sku.sql) — migration de backfill: para cada `invoice_items` com `cmig_product_id` setado e `sku` NULL/vazio, popula `sku` com o `cmig_products.sku_cmig` correspondente. Idempotente.
- [BACKEND/routers/invoices.py](BACKEND/routers/invoices.py) — `_serialize_item` ganha fallback defensivo: se `it.sku` é vazio mas `it.cmig_product_id` está setado, usa `it.cmig_product.sku_cmig`. Cobre o cenário "rodei a 61 mas não rodei a 62 ainda". `get_invoice` agora faz `selectinload(InvoiceItem.cmig_product)` pra evitar N+1 no fallback.

**Pendente para deploy:** rodar `Scripts SQL/62_backfill_invoice_items_sku.sql` no Oracle ATP. Após isso o fallback em runtime fica como rede de segurança apenas.

**Verificação:** `python -c "import routers.invoices as m"` → `imports OK`, `relationship cmig_product: True`.

---

## 2026-05-15 — Histórico de movimentação de estoque no card de Produtos CMIG

**Motivação:** Usuário pediu uma forma rápida de inspecionar o estoque de cada CMIGProduct — abrir um histórico de movimentações com filtro de período e saldo inicial/final calculados. Útil para conferência sem precisar abrir as NFes uma por uma.

**Mudanças:**
- [BACKEND/routers/cmigs.py](BACKEND/routers/cmigs.py) — novo endpoint `GET /cmigs/{cmig_id}/products/{product_id}/stock-movements?start_date=&end_date=`. Reconstrói o histórico a partir de `InvoiceItem` joined com `Invoice` (status `authorized|finalized` e `stock_updated=True`). Match por `cmig_product_id` OU por EAN (para itens legados). Retorna `initial_balance`, `final_balance`, `current_balance`, `period_in/out/net` e lista de movimentações com saldo acumulado.
- [FRONTEND/src/views/cmig-products/CmigProductListView.vue](FRONTEND/src/views/cmig-products/CmigProductListView.vue) — botão de ícone `fa-history` em cada linha (entre "Sync PG" e "Excluir"). Modal `modal-xl` com filtros de data (presets: 7d / 30d / 90d / 1ano / Tudo), 5 cards de saldo (Inicial, Entradas, Saídas, Final, Atual) e tabela com tipo, NF-e (link clicável), pessoa, item (descrição + SKU), qtd e saldo acumulado. Default: últimos 30 dias.

**Limitação documentada:** ajustes manuais de estoque (ex.: criação do produto com estoque inicial, edição direta via PATCH) não aparecem como linhas — ficam absorvidos no `initial_balance`. Para rastreamento completo seria necessária uma tabela `stock_movements` dedicada (futuro).

**Verificação:** `npm run build` em FRONTEND/ → `✓ built in 6.78s`. Backend → endpoint `GET /{cmig_id}/products/{product_id}/stock-movements` registrado no router.

---

## 2026-05-15 — Card de itens da NFe mostra SKU e origem (CMIG/PG/Manual)

**Motivação:** Usuário pediu que o card de itens (form e detalhe da NF-e) informe o SKU do produto e se o item veio do estoque CMIG ou do estoque PG. Antes, ambas as informações eram perdidas no momento da seleção — o item só guardava `cmig_product_id` (NULL quando vinha do PG) e o SKU não era capturado em nenhum cenário.

**Mudanças:**
- [Scripts SQL/61_invoice_items_sku_source.sql](Scripts SQL/61_invoice_items_sku_source.sql) — migration idempotente: adiciona `invoice_items.sku VARCHAR2(50)` e `invoice_items.source_type VARCHAR2(10)` (com CHECK `'cmig'|'pg'|'manual'` ou NULL). Backfill: itens existentes com `cmig_product_id` ganham `source_type='cmig'`.
- [BACKEND/models/fiscal.py:165](BACKEND/models/fiscal.py#L165) — campos `sku` e `source_type` adicionados ao `InvoiceItem`.
- [BACKEND/routers/invoices.py](BACKEND/routers/invoices.py) — `_serialize_item`, `create_item` (POST) e `update_item` (PATCH) aceitam/retornam os dois novos campos.
- [FRONTEND/src/views/fiscal/InvoiceFormView.vue](FRONTEND/src/views/fiscal/InvoiceFormView.vue) — `selectProduct(p, source)` agora captura `sku` (de `p.sku_cmig` se CMIG, `p.sku` se PG) e `source_type`. Card de itens ganha coluna "Origem" com badge (CMIG cinza, PG azul, Manual neutro) e SKU como small text abaixo da descrição.
- [FRONTEND/src/views/fiscal/InvoiceDetailView.vue](FRONTEND/src/views/fiscal/InvoiceDetailView.vue) — mesmo card replicado.

**Pendente para deploy:** rodar `Scripts SQL/61_invoice_items_sku_source.sql` no Oracle ATP antes de subir o backend.

**Verificação:** `npm run build` em FRONTEND/ → `✓ built in 7.05s`. Import do model em BACKEND/ → `sku: VARCHAR(50) source_type: VARCHAR(10)`.

---

## 2026-05-15 — Fix: NFe perde fornecedor selecionado ao finalizar/transmitir/calcular

**Motivação:** Usuário relatou erro "Selecione o fornecedor antes de finalizar" ao clicar em "Salvar sem SEFAZ" em uma Nota de Entrada, mesmo com o fornecedor visivelmente selecionado no formulário.

**Causa raiz:** A função `selectPerson` em [FRONTEND/src/views/fiscal/InvoiceFormView.vue:839](FRONTEND/src/views/fiscal/InvoiceFormView.vue#L839) só atualizava `form.person_id` localmente — não fazia PUT no backend. O backend [routers/invoices.py:1375](BACKEND/routers/invoices.py#L1375) lia `inv.person_id` direto do banco (ainda NULL) e disparava o erro. Bug latente afetava também "Calcular Impostos" e "Transmitir SEFAZ" para qualquer alteração de cabeçalho.

**Mudanças:** [InvoiceFormView.vue](FRONTEND/src/views/fiscal/InvoiceFormView.vue)
- `saveHeader()` agora aceita `{ silent: true }` — pula toast/reload, re-lança erros para o caller.
- `calculateTaxes()`, `transmit()`, `finalizeNoSefaz()` chamam `await saveHeader({ silent: true })` antes da ação. Garante que cabeçalho (fornecedor, natureza, datas, frete) está sincronizado com o backend.

**Verificação:** `npm run build` em FRONTEND/ → `✓ built in 8.48s`, sem erros.

---

## 2026-05-15 — Adoção cirúrgica do setup Fernando

**Motivação:** Avaliação do setup em `SetupFernando/` para reuso seletivo. Setup é alinhado em filosofia mas voltado para stack Next.js/Supabase/Firebase — adotado só o que se aplica a Vue/Oracle/OCI.

**Mudanças:**
- Copiado `migration-specialist.md` para [.claude/agents/](.claude/agents/) — útil pelo volume de SQL em [Scripts SQL/](Scripts%20SQL/) (60+ migrações).
- Adicionada **Regra de Verificação ("entregue exige prova")** em [CLAUDE.md](CLAUDE.md) — explicita os 5 critérios e os comandos `pytest`/`npm run build` que devem rodar antes de declarar conclusão.
- `migration-specialist` adicionado à tabela de agentes em [CLAUDE.md](CLAUDE.md).
- Bloco final padronizado: `State Current` → `Estado atual` com formato fixo de 7 campos (Objetivo final / Fase atual / Último ponto validado / Próximo passo / Bloqueios / Riscos ativos / Decisões pendentes).
- Anotado bloqueio ativo: `BACKEND/Wallet_MIGECOMMERCE/` ausente.

**Descartado intencionalmente:** `supabase-auditor`, `design-bridge`+Stitch, `discovery-guide`, `frontend/backend-specialist` (do setup Fernando — pressupõem Next.js/Supabase), stack global Firebase/Supabase, sobrescrita do `~/.claude/CLAUDE.md` global.

---

## 2026-05-15 15:00 — Maturidade do projeto: governança, testes, Docker, CI/CD

**Motivação:** Comparação com setup profissional de outro desenvolvedor revelou lacunas em processo de revisão, testes, containerização e CI/CD. Implementadas todas as melhorias mantendo Oracle como banco de dados.

### Agentes Claude (`.claude/agents/`)
- Criados 6 novos agentes customizados para o projeto:
  - `quality-guardian` — revisão de segurança, bugs, LGPD antes de cada entrega
  - `consistency-auditor` — CRUDs incompletos, padrões inconsistentes entre os 25 routers
  - `debug-specialist` — diagnóstico com contexto Oracle + AsyncSyncSession
  - `session-closer` — fecha sessões atualizando LOG.md, ADRs, lições, commit
  - `deploy-operator` — checklist obrigatório de deploy para Oracle Cloud
  - `adr-consistency-checker` — verifica se código respeita as ADRs

### Governança no CLAUDE.md
- Adicionada **Regra de Proporcionalidade** (Lightweight vs Full)
- Adicionada **Regra Inviolável de Conventional Commits**
- Adicionado **Procedimento de Auditoria** (quality-guardian + consistency-auditor + adr-checker em paralelo)
- Adicionada seção **State Current** (estado vivo do projeto)
- Atualizada regra de testes (agora há suite pytest)

### Documentação Estruturada
- `docs/decisions/ADR-0001-oracle-asyncsyncsession.md` — decisão e consequências do wrapper Oracle
- `docs/decisions/ADR-0002-vue3-adminlte-bootstrap.md` — stack frontend sem TypeScript
- `docs/decisions/ADR-0003-jwt-localstorage.md` — decisão de armazenamento de tokens
- `docs/lessons-learned.md` — 11 lições documentadas (bcrypt, CLOB, selectinload, etc.)
- `sandbox/.gitkeep` — pasta para experimentos

### Infraestrutura de Qualidade
- `BACKEND/pyproject.toml` — config de `ruff` (lint + format) e `mypy` (type check)
- `BACKEND/requirements.txt` — adicionados `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `httpx`
- `BACKEND/tests/conftest.py` — fixtures com MockDB (sem Oracle em testes unitários)
- `BACKEND/tests/test_health.py` — testes de health/docs endpoint
- `BACKEND/tests/test_auth.py` — testes de login, tokens, acesso negado
- `BACKEND/tests/test_orders.py` — testes de autenticação em endpoints de pedidos

### Docker
- `BACKEND/Dockerfile` — Python 3.11-slim, Oracle thin mode, sem Instant Client
- `FRONTEND/Dockerfile` — Node 20-alpine + nginx (build Vite em multi-stage)
- `FRONTEND/nginx.conf` — proxy para API, WebSocket e arquivos estáticos
- `docker-compose.yml` — orquestra backend + frontend com healthcheck
- `docker-compose.override.yml` — modo dev com hot-reload no backend

### CI/CD (GitHub Actions)
- `.github/workflows/ci.yml` — executa em todo push/PR:
  1. `ruff check` + `ruff format --check`
  2. `mypy` (continue-on-error na fase inicial)
  3. `pytest tests/ -m "not integration"` (sem Oracle — variáveis dummy)
  4. `npm run build` no frontend

### Conventional Commits + Husky
- `.commitlintrc.json` — regras commitlint (tipos, scope lowercase, subject 100 chars)
- `FRONTEND/package.json` — adicionados `@commitlint/cli` e `@commitlint/config-conventional`
- `.husky/commit-msg` — valida formato da mensagem de commit
- `.husky/pre-commit` — roda ruff nos arquivos Python staged
- `.claude/settings.json` — permissões pré-aprovadas commitadas no repositório

### Impacto
- Zero mudanças no código de negócio existente — todas as melhorias são infraestrutura/processo
- Oracle mantido como banco de dados
- Testes unitários funcionam sem conexão Oracle (mock do get_db)

---

## 2026-05-15 11:36 — Fiscal > Saídas: UI clean + criar destinatário + salvar sem SEFAZ

### Tela Fiscal > Saídas (`FRONTEND/src/views/fiscal/SaidasView.vue`)
- Coluna **Tipo**: removida a etiqueta colorida (badge). Agora exibe apenas o texto do tipo (Venda, Devolução, Retorno Simbólico, etc.) — visual mais limpo, sem destaque verde indevido em "Retorno Simbólico".
- Coluna **Nº / Série**: a chave de acesso agora fica na mesma linha do nº/série (`d-inline` + `ml-2`) entre parênteses, em vez de quebrar para a linha de baixo.

### Tela Nova / Editar NF-e (`FRONTEND/src/views/fiscal/InvoiceFormView.vue`)
- **Novo botão "Novo Cliente / Fornecedor"** no modal de seleção de Pessoa: abre um modal interno para cadastrar a pessoa (PF ou PJ), com lookup automático de CNPJ via BrasilAPI (`POST /people/lookup-cnpj`) que pré-preenche razão social, nome fantasia, e endereço. Ao salvar, a pessoa é selecionada automaticamente na NF-e.
- O modal pré-preenche o documento se o usuário já digitou na busca da listagem de pessoas.
- Marca `is_customer=true` para Saídas e `is_supplier=true` para Entradas automaticamente.
- **Novo botão "Salvar sem SEFAZ"** (`btn btn-primary`, ícone `fa-check-double`): finaliza a NF-e localmente sem transmissão à SEFAZ. Chama `POST /invoices/{id}/finalize-no-sefaz`.

### Backend — endpoint `POST /invoices/{id}/finalize-no-sefaz` (`BACKEND/routers/invoices.py`)
- Novo helper `_apply_stock_movement(inv, db)`: idempotente; para saídas (direction='out') decrementa `CMIGProduct.stock_quantity` por `cmig_product_id` ou EAN; para entradas incrementa. Marca `inv.stock_updated=True`.
- Novo endpoint que valida itens + person_id, aplica movimento de estoque, marca `inv.status = "finalized"` e grava um `InvoiceEvent(event_type="finalize_no_sefaz")`. Retorna o invoice serializado + `stock_movement: {matched, unmatched, already_updated}`.
- Validação: só funciona para NFes em status `draft` (reusa `_get_invoice_for_edit`).

### Frontend store + helpers
- `FRONTEND/src/stores/fiscal.js`: novo método `finalizeNoSefaz(invoiceId)`.
- `FRONTEND/src/views/fiscal/_helpers.js`: novo status `finalized` em `statusLabel` ("Finalizada (sem SEFAZ)") e `statusClass` (`badge-primary`).

### Resultado
- NFes "Finalizadas sem SEFAZ" aparecem normalmente na listagem `/fiscal/saidas` (a query `_collect_outbound_rows` não filtra por status), contribuindo para os totalizadores por CMIG (`by_cmig`) e ficando agrupáveis por Natureza da Operação (campo `natureza_operacao`).
- Estoque dos CMIGProducts é atualizado mesmo sem transmissão à SEFAZ — útil para devoluções manuais, ajustes e controles internos.

---

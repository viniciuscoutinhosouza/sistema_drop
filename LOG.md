# LOG de alterações — Sistema Drop

> Resumo cronológico das alterações feitas via Claude. Mais recente no topo.

---

## 2026-07-17 — feat(estoque): Sincronizar/Ler anúncio FULL cria inventário de conferência (ADR-0019 Fase 3)

Fecha o pedido original: "Sincronizar Estoque" e "Ler Anúncio" de anúncios **FULL** passam a **ler o
FULL do ML e criar/atualizar o inventário FULL de conferência** com essa contagem (reusa o
`_upsert_full_inventory_draft` da Fase 2). O usuário revisa em lote e finaliza como **Baseline** (o FULL
vira o número do ML) ou **Ajuste** — mantendo o FULL amarrado ao fiscal + âncora (decisão do dono; não
sobrescreve direto).

- **anuncios.py:** `sync_stock_to_marketplace` (só no sync MANUAL, com `listing_ids` — o scheduler
  automático NÃO gera rascunho) e `reimport_batch` coletam os anúncios FULL lidos e chamam o hook de
  conferência em transação própria (guard try/except: nunca derruba o sync). Ambos retornam
  `full_inventory_draft_id`/`full_items`.
- **Frontend (AnunciosView):** o modal de resultado da ação em lote mostra um callout com link
  "Revisar e finalizar →" para o inventário FULL criado.
- Reusa 100% do mecanismo auditado da Fase 2. ruff limpo; import 3.11 OK; `npm run build` OK. **Sem
  migration** (usa a 130). Padrão de guard idêntico ao hook de import (já em produção).

---

## 2026-07-17 — feat(estoque): inventário FULL como âncora do replay (ADR-0019 Fase 2)

Ao importar anúncio(s) FULL novo(s), o sistema cria um **inventário FULL em rascunho** (revisão em
lote) com a contagem do ML; o usuário finaliza como **Baseline** (a contagem vira a verdade na data)
ou **Ajuste** (soma a diferença), e a âncora entra no replay do FULL (Fase 1).

- **Migration 130** (`Scripts SQL/130_full_inventory.sql`, idempotente, padrão da 129): `inventories`/
  `inventory_items` aceitam `catalog_type/product_type='full'`; `inventories.account_id` (+FK). Model
  atualizado.
- **Replay data-aware ADITIVO** (`full_stock_service.py`): `_fetch_full_inventory_events` (baseline mais
  recente + ajustes) + `_apply_full_anchor` (PURA). `recompute_full_stock` agora carrega a data dos
  eventos e, por (CMIGProduct × conta) COM âncora, aplica baseline(piso `finalized_at`)/ajuste — **sem
  âncora → resultado byte-a-byte da Fase 1** (teste de regressão). Correção na revisão: produto com SÓ
  baseline (sem remessa/venda) é setado para `counted` (não zerado) via união de chaves.
- **inventories.py:** `PUT /{id}` troca o modo no rascunho; `finalize_inventory` branch FULL (recompute
  PRÉ → congela `system_qty`/`delta` → finaliza → recompute PÓS aplica a âncora); `_ser_header`+escopo
  aceitam FULL. **anuncios.py:** hook `_upsert_full_inventory_draft` no import (idempotente: reusa
  rascunho FULL aberto da conta; retorna `full_inventory_draft_id`).
- **Frontend:** tela de inventário revisa/finaliza FULL (badge FULL+conta, seletor Baseline/Ajuste no
  rascunho, nota); lista com badge FULL; resultado do import mostra link p/ revisar o rascunho.
- Auditado: consistency-auditor (prévio, 8 pontos incorporados: migration 129-pattern, replay aditivo
  sem regressão, modo via PUT, idempotência do hook, account no header, anchor próprio) + quality-guardian
  (2 HIGH: piso `finalized_at` = **paridade com o inventário local** [não é bug — confirmado linha 653];
  concorrência do finalize = mesma limitação Fase 1 — **documentados** no ADR) + adr-consistency-checker
  (aprovado na Fase 1). ruff limpo; import 3.11 OK; `test_full_inventory`+`test_full_recompute` 19 passed;
  `npm run build` OK. **Migration 130 pendente de aplicar no Oracle** (o dono aplica).

---

## 2026-07-17 — feat(estoque): FULL recomputável por replay (ADR-0019, Fase 1)

O estoque FULL (`FullStock.qty`) passou de **só incremental** para **recomputável por replay** — base
do subsistema pedido pelo dono (Fase 2: âncora de inventário na importação; Fase 3: sync/ler anúncio).

- **`recompute_full_stock`** (`services/full_stock_service.py`): reconstrói o FULL por (produto CMIG ×
  conta) — **acumular-e-fixar** (soma os deltas e grava `qty=max(0, soma)`, sem clampar a cada evento):
  `+ Σ remessa` (Invoice `direction='out'` p/ CNPJ FULL) `− Σ retorno` (`direction='in'` de CNPJ FULL,
  exclui `purpose='devolucao'`) `− Σ venda FULL` (Order `full` shipped/delivered, **exclui
  `return_status='returned'`** e cancelado). **Débito da venda dirigido pelo PEDIDO, uma vez, só o FULL**
  (nunca o galpão). Preserva `reserved_qty`; zera linhas stale do escopo. Reusa `is_full_cnpj`/
  `resolve_full_*` (sem duplicar lógica). Função pura `_accumulate_full_balances` isolada + testada.
- **Integrado ao botão "Recalcular Estoque (todos)"** (`POST /stock/recompute-all`): após o recompute
  local + reservas, roda `recompute_full_stock` em `db3`.
- **Cancelamento/devolução que reabastece o Full:** tratado — venda `returned`/cancelada não debita
  (re-crédito por omissão no replay do zero).
- **Limitações (Fase 1, documentadas no ADR-0019):** grava `qty` absoluto → evento incremental durante
  o replay em background pode ser sobrescrito (auto-cura no próximo recompute; rodar em baixo tráfego).
  `reserved_qty` fora do escopo desta fase.
- Auditado: quality-guardian (sem CRITICAL; 2 HIGH de decisão — filtro `devolucao` alinhado + janela de
  concorrência documentada) + adr-consistency-checker (**aprovado**, sem violação de 0004/0008/0009/0010/
  0013). ruff limpo; import 3.11 OK; `test_full_recompute` 8 passed (regra de acumulação); **sem migration**.
  Nota: `recompute_full_stock` (que toca o Oracle) não foi smoke-testado em DEV (sem Wallet) — validar em
  produção numa CMIG antes de rodar amplo.

---

## 2026-07-17 — feat(pedidos): filtro por período + filtro de Entrega + busca ampliada

Três melhorias nos filtros da tela de **Pedidos**:

- **Período (data inicial/final):** novos params `date_from`/`date_to` no `GET /orders`. O dia é do
  calendário BR (ADR-0013) convertido para UTC via `BR_TZ`; range **half-open** `[dia 00:00,
  dia_seguinte 00:00)` → cobre o dia BR inteiro (`created_at` é UTC-aware). Data inválida → **422**.
- **Filtro de Entrega** substitui o de **Tags** (que não tinha outro consumidor): usa o
  `shipping_mode` já classificado — Full, Flex, Agência, Correios (+Coletado/Combinado), com "Todos"
  como padrão. Os badges de tag na linha do pedido continuam (só o filtro saiu).
- **Busca ampliada:** o campo antes só batia em `buyer_name`; agora `or_(buyer_name, platform_order_id
  [nº da venda], items.any(sku/title))` — cliente, nº da venda, SKU e nome do produto. `any()` gera
  EXISTS correlacionado (não duplica linhas; coexiste com o count e o selectinload).
- Frontend (OrderListView): 2 inputs de data (De/Até, `filters.created_from/created_to` → enviados
  como `date_from/date_to`), select "Entrega" (`shipping_mode`), placeholder novo da busca.
- Auditado (consistency-auditor prévio: half-open, opção "Todos", 422, nomes de campo sem colisão com
  o `syncRange` — incorporados). Verificação: ruff limpo; import 3.11 OK; `npm run build` OK; conversão
  BR→UTC conferida. **Sem migration** (follow-up recomendado: índice em `orders.created_at`).

---

## 2026-07-15 — feat(estoque): botão "Recalcular Estoque (todos)" na tela de Controle de Estoque

A tela **Controle de Estoque** ganhou um botão que recalcula o estoque de **todos os produtos**
(loop do mesmo cálculo canônico do botão de 1 produto). Decisões do dono: **recálculo completo**
(físico + reservas + reativação de flags de NF-e) e acesso **só admin/UGO**.

- **Reuso, sem endpoint novo:** o botão chama o `POST /stock/recompute-all` que **já existia** —
  ele roda `recompute_all_stock` (que literalmente faz o loop de `recompute_pg/cmig_product_stock`,
  as MESMAS funções do botão de 1 produto) + `recompute_reservations_from_movements` + reativa
  `Invoice.stock_updated`, tudo **em background** (retorna na hora → sem risco de timeout).
- **Permissão:** o endpoint era `require_menu_permission("estoque")`; adicionei gate de papel
  **admin/UGO** (operação global afeta todas as CMIGs/galpões; não faz sentido para AC, escopado).
  O endpoint não tinha caller no frontend, então a restrição é segura.
- **Frontend (StockControlView):** botão visível só p/ admin/ugo, com `confirm()`, spinner e toast
  "recálculo iniciado em segundo plano — atualize a lista em instantes".
- Auditado (consistency-auditor prévio: escolha síncrono-vs-background e semântica levada ao dono →
  respondido "completo" + "admin/ugo") + quality-guardian. Verificação: ruff limpo; import 3.11 OK;
  `npm run build` OK. **Sem migration.**

---

## 2026-07-15 — feat(estoque): exportar Controle de Estoque em PDF e Excel

A tela **Controle de Estoque** ganhou um botão **"Exportar"** (Excel `.xlsx` / PDF) que baixa os
produtos listados **respeitando os filtros atuais** (escopo PG/CMIG, galpão, CMIG, busca, zerados,
ordenação).

- **Backend:** novo `services/stock_export.py` (`build_pdf` A4 paisagem + `build_xlsx`, colunas iguais
  às da tela: SKU, Produto, EAN, Tipo, Físico, Reservado, Disponível, Ag.Retorno, Ag.Validação,
  Inapto, FULL; guard anti formula-injection no Excel + escape `& <` no PDF). Em `routers/stock.py`
  extraí `_collect_stock_items` (fonte ÚNICA: acesso por role + escopo AC + **escopo FULL por conta**
  + sort, sem paginação) — `stock_summary` só pagina. Novo `GET /stock/summary/export?format=pdf|xlsx`
  reusa o helper (mesmo acesso), com **teto de 5000 linhas** (trunca + avisa no subtítulo) e nome de
  arquivo com data/hora BR (`datetime_br`, ADR-0013).
- **Frontend (StockControlView):** dropdown "Exportar" (Excel/PDF) → GET do export com os mesmos
  params do `load()` → `saveBlobResponse`.
- **Dívida técnica registrada:** `stock_export.py` é a 3ª cópia do esqueleto reportlab/openpyxl
  (com `eship/export.py` e `sales_report_export.py`) — vale extrair um `services/table_export.py`
  genérico num commit futuro.
- Auditado (consistency-auditor prévio: `format=pdf|xlsx`, FULL=`full_stock_total`, escopo FULL no
  helper, cap, filename BR — incorporados) + quality-guardian. Verificação: ruff limpo;
  `test_stock_export` 4 passed; import 3.11 OK; `npm run build` OK. **Sem migration.**

---

## 2026-07-13 — feat(etiqueta): botão baixa ZIP (PDF+ZPL) e ação em lote na tela Pedidos

Na tela **Pedidos**, o botão de etiqueta passou a **baixar um ZIP com o PDF e o ZPL** (sem abrir o
PDF), e o menu "Imprimir Selecionadas" ganhou **"Baixar etiquetas (ZIP)"** dos pedidos marcados.

- **Backend (orders.py):** extraí `_ml_label_fmt_bytes` do endpoint `/label` (validação + cache +
  fetch ML + conferência no zpl2); `_order_label_pair(order)` devolve `(pdf, zpl)` tratando ML
  (reusa `_ml_label_fmt_bytes`; `_emit_nfe_for_label` é idempotente → não reemite ao buscar os 2
  formatos) e **manual** (usa `_load_manual_label_data` — acesso CANÔNICO do manual, não o filtro
  genérico, evitando alargar acesso). Novos endpoints: `GET /{id}/label.zip` (1 pedido) e
  `POST /labels.zip` {order_ids} (lote, **cap 25**, falha por pedido vira linha em `_avisos.txt`).
- **Frontend (OrderListView + OrderDetailView):** botão → `downloadLabelZip` (GET `/label.zip`,
  baixa o zip, **não abre**); novo `bulkDownloadLabels` (POST `/labels.zip`). Removidos os handlers
  antigos (`printShippingLabel`/`downloadManualLabel`/`saveLabelBoth`) que abriam o PDF.
- **Segurança/LGPD:** o cache de etiquetas saiu de `BACKEND/static/labels/` (servido sem auth — o
  PDF do ML tem nome+endereço do comprador) para `BACKEND/private_labels/`, servido só pelos
  endpoints autenticados (mesmo padrão do ADR-0015 p/ XML). Deploy deve remover o `static/labels/`
  legado no servidor.
- Auditado (consistency-auditor prévio: CRITICAL de acesso manual [usar `_load_manual_label_data`] +
  HIGH de assinatura/duplo-fetch [`_emit` idempotente, cap 25] incorporados) + quality-guardian
  (HIGH pré-existente do cache em `static/` **corrigido**). Verificação: ruff limpo; `test_label_zpl`
  13 passed (inclui `_zip_label_files`); separação/eship OK (36 passed); import 3.11 OK;
  `npm run build` OK. **Sem migration.**

---

## 2026-07-13 — fix(etiqueta): ZPL de pedido ML passa a trazer o produto (SKU/nome/qtd)

O ZPL do pedido ML vinha nativo do Mercado Livre — só o rótulo de envio, **sem o SKU/nome/qtd**
do vendedor (o PDF do ML traz a declaração de conteúdo; o ZPL não). Como não dá para editar os
bytes do ML, o sistema agora **anexa uma etiqueta ZPL de CONFERÊNCIA** (SKU + nome + qtd + código
de barras) logo após o rótulo de envio, em todos os pontos que servem ZPL de ML.

- **Reuso (não duplicou):** a conferência usa o `render_shipping_labels_zpl` já existente com um
  **cabeçalho parametrizável** (`header_label`) — "CONFERENCIA DE PRODUTO (pedido ML)". O ZPL manual
  segue com o cabeçalho "VENDA DIRETA".
- **Novo `services/label_meta.py`:** `build_orders_label_meta` + `resolve_item_base` extraídos da
  separação (evita import circular orders↔separation) e reusados nos dois. Resolve EAN/nome via
  `resolve_order_item_link` — **essencial** p/ pedidos ML vinculados só pelo anúncio (sem isso o
  produto sairia vazio). A separação passou a importar esses helpers (sem reescrever a lógica).
- **orders.py `/{id}/label` (zpl2):** anexa a conferência **on-the-fly** (montada do banco) — o
  cache em disco continua guardando só o ZPL **puro do ML**, então a conferência nunca fica velha.
- **separation.py:** `cart_labels` (ramo ML, fmt=zpl2) e ZIP bundle (ramo ML) anexam a conferência
  dos MESMOS pedidos do rótulo. O ZPL segue **sem marcar impresso** (companheiro).
- **Limitação conhecida:** no ML saem **2 rótulos térmicos por pedido** (envio do ML + conferência);
  no manual o produto continua no mesmo rótulo. Inevitável (não editamos o rótulo do ML).
- Auditado (consistency-auditor prévio: reusar render_shipping_labels_zpl + reusar `_order_labels_meta`
  via módulo compartilhado + não cachear a conferência — todos incorporados). Verificação: ruff limpo;
  `test_label_zpl` 11 passed; separação/eship OK (35 passed; 2 falhas pré-existentes em test_orders,
  `MockResult`); import 3.11 OK. Sem migration. Sem mudança no frontend.

---

## 2026-07-11 — feat(etiqueta): baixar etiqueta em PDF **e** ZPL em todos os locais

Toda ação de etiqueta passa a baixar os **dois formatos de uma vez** (PDF + ZPL Zebra). Revisados
todos os pontos onde o sistema busca etiqueta: pedido único (ML), pedido manual/venda-direta,
separação em lote (gaiola) e ZIP de documentos.

- **Fix latente (crítico):** `ml_service.get_shipment_label(fmt="zpl2")` agora **desembrulha o ZIP**
  que o ML retorna (o conteúdo real é o `.txt` `^XA…`). Antes o endpoint de pedido único servia o
  ZIP cru como `.zpl` (lixo p/ impressora). Unwrap centralizado (`_unwrap_zpl_zip`) — orders,
  separação e eShip (idempotente) recebem ZPL limpo.
- **Gerador ZPL nativo** (`label_service.py`): `render_shipping_labels_zpl` / `render_manual_order_label_zpl`
  — etiqueta térmica 10x15 @203dpi (uma por volume; `^CI28` p/ acentos, Code128 `^BCN`, EAN13 `^BEN`
  com fallback p/ Code128, escape de `^ ~ \`). Reusa `_flatten_volumes` do PDF (conjuntos idênticos).
- **manual_orders**: novo `GET /{id}/label.zpl` espelhando `.pdf` (carga comum extraída).
- **separation `cart_labels`**: `fmt=pdf|zpl2`. O ZPL é o formato **companheiro** — mesma seleção do
  PDF, mas **não marca impresso** (o front pede zpl2 **antes** do pdf → conjuntos iguais, marcação
  única). ZPL é sempre 10x15 (ignora `layout` — A4/4-up é conceito de papel).
- **separation ZIP bundle**: inclui `.zpl` ao lado de cada `.pdf` (ML + manual).
- **Frontend**: `utils/download.js` ganhou `saveLabelBoth(pdfResp, zplResp)` (abre PDF p/ imprimir +
  baixa PDF + baixa ZPL). Aplicado em OrderList (ML + manual), OrderDetail (manual) e Separação
  (pedido + lote). O `bundle.zip` já baixa tudo.
- Auditado (consistency-auditor prévio: fix do ZIP-do-ML + "não marca no zpl2" incorporados).
  Verificação: ruff limpo; `test_label_zpl` 9 + separação/eship OK (31 passed); import 3.11 OK;
  `npm run build` OK. **Sem migration.** ZPL não pôde ser testado em impressora térmica real (validada
  a estrutura ^XA/^XZ/^CI28/barcodes).

---

## 2026-07-11 — feat(relatorio): Vendas por período + gráfico diário; fix das colunas % Lucro / % LL

**Fix (% Lucro e % LL).** As colunas calculavam **participação no total do período** (lucro do produto
÷ lucro total). O correto é a **margem do próprio produto**: `% Lucro = Lucro Bruto / Venda` e
`% LL = (Lucro Bruto − Taxa − Frete) / Venda`. A linha TOTAL mostrava `100%` fixo (fazia sentido na
semântica antiga) → agora mostra a **margem consolidada** (não soma 100%, como esperado p/ margem).

**Filtro por período.** O seletor de mês virou **De / Até** (datas locais BR, ambas inclusivas) com
atalhos *Este mês / Mês anterior / 30 dias*. `build_monthly_sales(year, month)` →
**`build_sales_report(date_from, date_to)`**, limites BR→UTC (ADR-0013). Os 3 endpoints (gerar /
Atualizar / exportar) e o nome do arquivo exportado passaram a usar o período. Validação: início ≤ fim
e teto de 366 dias.

**Gráfico de variação diária.** Área (ApexCharts) com **Vendas** e **LL Parcial** por dia, cobrindo
todos os dias do período (dias sem venda = 0, a linha não "pula"). O **LL diário** usa a taxa/frete
**dos pedidos do dia** (não o rateio por produto) — como `platform_fee`/`seller_shipping_cost` já são
por pedido, o dia é a atribuição exata: **Σ dias == total do período** (garantido por teste).

**Verificação:** teste cobre margens, período e série diária; `pytest -m "not integration"` 98 passed /
2 pré-existentes; `npm run build` OK.

---

## 2026-07-11 — feat(produtos): descrição por IA + ficha dos componentes do KIT (4 telas)

**#1 Descrição por IA** — botão "Gerar por IA" no campo Descrição das **4 telas** (CMIG simples/KIT,
PG simples/KIT). Abre modal com: **prompt** (10 linhas, largura total), **resposta da IA editável**
(10 linhas), **checkbox** que reenvia a resposta anterior como **contexto** do próximo prompt,
**Voltar** (não altera a descrição) e **Pronto** (substitui). Campo Descrição das 4 telas
padronizado em 10 linhas/largura total.
- Backend: **novo** `routers/ai_content.py` → `POST /api/v1/ai/product-description`.
  **Nada de LLM novo** — reusa `ai_service.complete()`, `AIConfig` (singleton ativo, chave base64) e
  `product_brief.build_product_brief()` (ficha técnica do produto, já sanitizada contra
  prompt-injection) como contexto automático quando o produto já existe (edição).
  Trata `httpx.TimeoutException` → **504** (o `ai_service` não tratava e vazava como 500).
  Sem `AIConfig` ativa → **400** com mensagem clara (nunca falha em silêncio).

**#2/#3 Componentes do KIT** — cada componente mostra **dimensões · peso · NCM · CEST** abaixo do
título e um **ícone que copia a descrição**; o modal de IA (nos KITs) lista os componentes com
ícone de copiar a descrição de cada um (p/ colar no prompt).
- **Gap fechado no backend:** os blocos `components[]` dos serializadores **descartavam**
  `description`/dimensões/peso/NCM/CEST — sem isso os campos sumiam ao reabrir o KIT em edição.
  Completados: `_serialize_cmig_product` + `/pg-products` (`cmigs.py`, via novo helper
  `_product_specs`) e `_serialize_product` (`supplier_products.py`, + `cost_price` que também faltava).
  Frontend: `addComponent()` e `onMounted()` das 2 telas de KIT agora propagam os campos.

**Novos (reutilizáveis):** `composables/useClipboard.js` (o padrão estava reimplementado inline em 8
telas), `components/products/AiDescriptionModal.vue`, `components/products/ProductDescriptionField.vue`
(um componente para as 4 telas, em vez de 4 cópias).

**Atenção:** `CMIGProduct.description` é `VARCHAR(4000)` (o PG é CLOB) → o modal mostra contador e
**bloqueia o "Pronto"** se exceder, evitando truncamento no save.

**Verificação:** chamada **real** à IA ponta a ponta (config → ficha técnica → prompt → LLM → texto):
descrição coerente gerada usando a ficha do produto. Rota `/api/v1/ai/product-description` registrada.
`pytest -m "not integration"` 98 passed / 2 pré-existentes; `npm run build` OK. Sem migrations, sem
novas dependências.

---

## 2026-07-11 — fix(kit): card "Componentes do Kit" não localizava produtos PG (403 silencioso)

No cadastro de KIT da CMIG (`CmigCompositeFormView`, rota `role:'ac'`), a aba **"Catálogo PG"**
não retornava nada. **Dois defeitos empilhados + um que os escondeu:**
1. **403:** a aba chamava `GET /api/v1/pg`, que exige a menu-key **`pg`** — e o perfil **`gc` (AC)**,
   único que cria KIT de CMIG, **não a possui** (seed 83). Todo AC tomava 403.
2. **A busca não existia:** `GET /pg` **não declarava `search`** (FastAPI descarta o param). Mesmo
   como admin, digitar um SKU devolvia o **catálogo inteiro** sem filtrar — a busca de PG nunca
   funcionou (idem no KIT de PG, `PgCompositeFormView`).
3. **Silêncio:** `doSearch()` tinha `try/finally` **sem `catch`** → o 403 era engolido, sem toast.

**Correções**
- `routers/cmigs.py`: **novo** `GET /cmigs/{cmig_id}/pg-products?search=&limit=` — lookup de PG no
  escopo da CMIG, autorizado por `_check_cmig_access` (o mesmo da aba CMIG, que já funcionava),
  **sem afrouxar o CRUD de PG**. Escopo: PG **ativo**, do **galpão da CMIG** e **não-composto**
  (evita kit-dentro-de-kit no servidor). Busca `ilike` em título+SKU. Fallback: CMIG sem galpão →
  não filtra por galpão (senão o picker viria vazio).
- `routers/supplier_products.py`: `GET /pg` ganha `search`/`simple_only`/`limit` (opcionais —
  comportamento antigo preservado). Conserta a busca do KIT de PG.
- `CmigCompositeFormView.vue` / `PgCompositeFormView.vue`: aba PG → novo endpoint; **`catch` com
  toast** (o silêncio foi o que escondeu o bug) e **estado vazio** ("Nenhum produto encontrado
  para X") em vez da tabela sumir.
- **Descartado de propósito:** conceder a menu-key `pg` ao perfil `gc` (abriria o CRUD de PG ao AC).

**Verificação:** query do novo endpoint exercitada contra o banco (CMIG 1/galpão 1): busca por
título "Anel" → 2; por SKU "5212" → 1; termo inexistente → 0. `pytest -m "not integration"`
98 passed / 2 pré-existentes; `npm run build` OK. Sem migrations, sem novas dependências.

---

## 2026-07-11 — feat(cmig): converter identidade fiscal CPF ⇆ CNPJ (ADR-0018)

Passou a ser possível **alterar o tipo fiscal** de uma CMIG existente (ex.: uma conta cadastrada como
CPF que virou empresa → CNPJ). Antes era impossível: o `update_cmig` usava `exclude_none=True` (não
dava para limpar o CPF) e o formulário só *adicionava* CNPJ mantendo o CPF (deixaria os dois).

- **Backend:** `CMIGUpdate` ganhou normalizador (`''`/espaços → `None`, mas mantém o campo em
  `fields_set`) + campos `ie`/`ibge_code`; `CMIGOut` expõe `ibge_code`. `update_cmig` trata o
  documento **fora** do `exclude_none`: valida estado final (exatamente um de CPF/CNPJ), unicidade,
  Razão Social p/ PJ, e **seta ambos explicitamente** (permite zerar o antigo). Alterar o **tipo**
  exige `ac`/`admin`. Converter **CPF→CNPJ** exige **IE** (upsert no `fiscal_config`) e **IBGE**.
- **Frontend (`CmigFormView`):** toggle PJ/PF também na edição; **aviso** de impacto (pedidos
  pendentes mudam de DC-e→NF-e, recadastro eShip, conta ML não muda); campos IE/IBGE na conversão
  (IE pré-preenchida do fiscal-config).
- **Política (escolha do dono):** efeitos colaterais são **avisados, não bloqueados**; documentos já
  emitidos ficam intactos (snapshot). **Sem migration** (colunas já nullable/unique — migration 49).
- Auditado (consistency-auditor prévio: C1 eShip / C2 regime live → tratados como aviso + IE/IBGE
  obrigatórios). Verificação: ruff limpo; `pytest test_cmig_conversion` 5 passed; normalizador testado.

---

## 2026-07-10 — feat(downloads): nome de arquivo padronizado Tipo_venda_cliente (etiqueta/NF-e/DANFE/DACE)

Todo arquivo de pedido baixado passa a sair nomeado com **tipo + número da venda + nome do cliente**
(ex.: `Etiqueta_2000017318796590_Elaine-C.pdf`, `NF-e_..._Elaine-C.xml`). Etiqueta/DANFE/DACE (que
abrem em nova aba para imprimir) agora **abrem E baixam** uma cópia já nomeada (escolha do usuário).

- **Backend:** novo `services/file_naming.py` — `slugify_name` (ASCII estrito via NFKD + ascii-ignore,
  protege o `Content-Disposition` contra header injection do nome do comprador) + `order_download_filename`
  (`Tipo_venda_cliente[_extra].ext`) + constantes `TIPO_ETIQUETA/NFE/DANFE/DACE`. Aplicado no
  `Content-Disposition` de `orders` (etiqueta, NF-e XML, DANFE, DACE), `manual_orders` (etiqueta),
  `separation` (DANFE + nomes internos do ZIP) e `invoices` (Saídas XML/DANFE — com
  `selectinload(Invoice.order)` + fallback p/ NF-e de entrada sem pedido).
- **Frontend:** novo `utils/download.js` — como o blob URL perde o header, o front lê o
  `Content-Disposition` e usa como `a.download` (backend = fonte única do nome). `saveBlobResponse` +
  `openAndSaveBlobResponse` aplicados em OrderList, Saídas, Detalhe NF-e, modal NF-e e Separação.
- Auditoria: consistency-auditor (prévia, CRITICAL de header-injection incorporado) + quality-guardian
  (sem CRITICAL/HIGH). Verificação: ruff limpo; `import main` OK; `pytest test_file_naming/test_separation`
  OK; `npm run build` OK. **Sem migration.** Deploy `c7ed84c` em produção (docs 200, cmigs 401, sem
  ImportError, PM2 estável).

---

## 2026-07-09 — chore(dce): remove o código dormente da auto-emissão SEFAZ (DC-e vem do emissor do ML)

Teste ao vivo provou que a auto-emissão nunca liberaria a etiqueta: mesmo com uma DC-e de produção
autorizada (emitida pelo ML), o `GET /shipments/{id}/invoice_data` fica **404** — o `invoice_data` do
ML **não aceita DC-e (modelo 99)**, só NF-e 55; a DC-e é interna ao emissor do ML (assinada com o
certificado do próprio ML). Confirmado que a opção B (auto-emitir + reportar) é inviável → removido o
código morto.

- **Removidos:** `services/fiscal/dce/{dce_service,xml_builder_dce,dce_signer,chave_dce,ibge}.py`,
  testes `test_dce_{xml,ibge,ml_report}.py`, `ml_service.report_dce_invoice`,
  `orders.{_report_dce_to_ml,_cpf_label_invoice_pending,_dce_feature_ready}`, `config.NFE_ENV_PROD`,
  `OrderDce.ml_reported_at` (atributo do model; coluna fica no banco).
- **Mantidos (ativos):** `dce_client`/`signer_cert`/`dace`/`exceptions` (teste de certificado central
  em `marketplace_settings` + DACE de legado via `get_order_dace`), `OrderDce` (usado por
  `order_docs`), `emit_order_dce` (neutralizado → devolve o link do emissor do ML) e o botão do
  frontend (opção A). Migrations 120/121/124 e a tabela `order_dce` permanecem.
- ADR-0017 atualizada. Verificação: ruff limpo; `import main` OK; `pytest -m "not integration"`
  **86 passed / 2 pré-existentes**; grep confirma **zero** referências remanescentes aos símbolos
  removidos (backend + frontend).

---

## 2026-07-09 — refactor(dce): DC-e passa a ser emitida pelo emissor do próprio ML (link) — supersede ADR-0017

Ao ligar a emissão própria de DC-e em **produção**, o handshake TLS com a SEFAZ-PR falhou
(`unable to get local issuer certificate` contra `dce.fazenda.pr.gov.br`): o Ubuntu não confia na
raiz **ICP-Brasil v10** e o `NFE_ICP_CABUNDLE` era config morta (nunca carregado no
`_build_ssl_context`). Em vez de resolver credenciamento + ICP-Brasil, adotou-se o **emissor de DC-e
do próprio Mercado Livre**.

- **Frontend** (`OrderListView.vue`): o botão "Emitir DC-e" vira um **link** (`dceEmitterUrl`) que
  abre `mercadolivre.com.br/emissor/omni/emitir/dce/sale/SALE_ML_DCE/{platform_order_id}?...` — rota
  real do ML, reconstruível por venda. O ML emite a DC-e e **libera a etiqueta**.
- **Backend** (`emit_order_dce`): **neutralizado** — devolve `{ml_emitter, emitter_url}` (helper
  `_ml_dce_emitter_url`), sem tocar na SEFAZ. Etiqueta CPF volta a instruir via `_DCE_PENDING_MSG`.
- **Dormente (não removido, reversível):** `services/fiscal/dce/*`, `report_dce_invoice`,
  `_report_dce_to_ml`, `_cpf_label_invoice_pending`, tabelas/migrations 120/121/124.
- **Produção revertida:** `NFE_ENV_PROD=false` + `production_released=0` (CMIG 101) — some o erro 500.
- ADR-0017 marcada **SUPERSEDED**. `report_dce_invoice`/`_report_dce_to_ml` seguem testados (dormentes).

---

## 2026-07-09 — fix(dce): reporta a DC-e ao Mercado Livre para liberar a etiqueta (conta CPF)

Bug (venda 2000017318796590): a DC-e era emitida na SVRS mas o sistema **nunca avisava o ML** →
shipment ficava `invoice_pending` → etiqueta bloqueada. Verificado ao vivo (shipment 47478739656:
`invoice_pending`, `GET /invoice_data`→404). O `ml_service.emit_dce` era um **stub 501**. Também: o
toggle `NFE_ENV_PROD` era lido em `dce_service.py` mas **não existia** no `Settings` → produção
inalcançável (a DC-e daquela venda saiu em homologação).

- **`report_dce_invoice`** (ml_service): `POST /shipments/{id}/invoice_data?siteId=MLB`,
  `application/xml`, XML `procDCe` **cru** (preserva a assinatura). Recusa do ML → HTTPException com o
  motivo.
- **`_report_dce_to_ml`** (orders): carrega a `OrderDce` autorizada; envia só se
  `environment='production'` (o ML recusa homolog); idempotente por `order_dce.ml_reported_at`
  (migration 124); token via `get_valid_token`.
- **Wiring:** best-effort no fim de `emit-dce` (`ml_notified`/`ml_warning`, sem desfazer a emissão) +
  `_cpf_label_invoice_pending` no fluxo da etiqueta (reporta a DC-e e orienta reclicar; recusa do ML
  propaga).
- **`config.py`:** declara `NFE_ENV_PROD: bool = False` (corrige o toggle morto; gate composto com
  `production_released` por CMIG).
- Migration 124 (`order_dce.ml_reported_at`). ADR-0017 atualizada (passo de report ao ML).
- Auditado (consistency-auditor prévia + quality-guardian + adr-consistency-checker): sem
  CRITICAL/HIGH. 7 testes novos (`test_dce_ml_report.py`); ruff limpo; app importa. **Pendente:** smoke
  em produção (confirmar aceite do modelo 99 no `invoice_data` na 1ª emissão real).

---

## 2026-07-07 — fix(estoque): reserva órfã de pedidos entregues zerava o disponível do anúncio

Anúncio MLB4794270619 (produto PG 156, "Halter 24kg") mostrava estoque=2 mas 0 disponível:
`reserved_quantity=3 > stock=2`. Causa: 3 pedidos JÁ ENTREGUES (1341/1343/1415) com movimento
`reserve` **sem `unreserve`** — a reserva nunca foi liberada. Pedido não-FULL reserva ao ser criado;
a liberação (`confirm_dispatch`) só dispara na TRANSIÇÃO de `shipment_status`→shipped/delivered num
sync. Pedidos importados/sincronizados **já entregues** (sem transição observada) reservavam e nunca
liberavam → reserva órfã → `disponível = estoque − reservado` subestimado (e anúncio auto-pausado).
**Sistêmico:** 119 pedidos / 32 produtos.

- **Reparo (produção):** `backfill_orphan_reservations(apply)` — liberou 119 pedidos / 32 produtos
  (produto 156 → reservado 0, disponível 2). Só mexe em `reserved_quantity` (estoque físico é
  event-sourced — a entrega já é a saída canônica); 0 produtos negativos.
- **Causa-raiz (código):** `webhook_service.process_ml_order` — ao criar pedido não-FULL já despachado/
  entregue (`_order_was_dispatched`), libera a reserva recém-criada (`release_reservation`, idempotente).
- **Safety-net:** job `release_orphan_reservations` a cada 6h (`tasks/release_orphan_reservations_job.py`)
  rodando o backfill idempotente — cobre casos de borda (relink pós-entrega etc.).
- **Verificação:** `pytest -m "not integration"` 94 passed / 2 pré-existentes; `py_compile` OK.

---

## 2026-07-07 — fix(orders): pedido duplicado (aparecia 3× na tela de Pedidos) — race na sincronização

A venda 2000017298867566 aparecia 3× porque havia **3 registros `Order` idênticos** (mesmo
`created_at` no mesmo segundo) — corrida: webhook + job `sync_orders` inserindo o mesmo pedido ao
mesmo tempo. `orders.platform_order_id` **não tinha restrição única** (só índice não-único); a dedup
existia só no app (`process_ml_order`/`process_shopee_order` com `scalar_one_or_none`), que não segura
inserções concorrentes.

- **Limpeza (produção):** removidas 3 linhas extras (2 pedidos afetados: ids 1689,1690,1385), seus
  `stock_movements`, e `recompute_reservations_from_movements` corrigiu o `reserved_quantity`
  (35 produtos PG — estavam super-reservados). Verificado: 1 linha/venda, 0 grupos duplicados.
- **Prevenção (schema):** migration **123** — índice ÚNICO `ux_orders_plat_poid_drop` em
  `orders(platform, platform_order_id, dropshipper_id)` (pedidos manuais com `platform_order_id` NULL
  não entram na unicidade). Inclui dedup defensivo idempotente.
- **Prevenção (código):** `webhook_service` (ML + Shopee) captura `IntegrityError` no `flush` do insert
  → rollback + re-busca o pedido criado concorrentemente → ignora graciosamente (sem 500, sem duplicar).
- **Verificação:** `pytest -m "not integration"` 94 passed / 2 pré-existentes; `py_compile` OK.

---

## 2026-07-04 — fix(dashboard): KPIs "hoje"/"mês" usavam meia-noite UTC em vez do fuso BR (ADR-0013)

`routers/dashboard.py` `get_kpis` (home Dashboard) montava os limites de dia/mês com
`datetime.now(UTC).replace(hour=0…/day=1)` → a virada caía às 00:00 UTC (= 21:00 BRT do dia
anterior). Pedidos da madrugada BR (00:00–03:00) caíam no dia/mês errado; ex.: um pedido de
30/06 22h BRT era contado em "hoje" (01/07). Corrigido: limites calculados em `datetime.now(BR_TZ)`
e convertidos para UTC (`.astimezone(UTC)`) só na comparação com `created_at` (TIMESTAMP WITH TIME
ZONE) — mesmo padrão já usado em `GET /dashboard/marketplace` e `sales_report_service`.
- O endpoint `/dashboard/marketplace` (tela "Dashboard de Marketplaces") **já estava correto**
  (janelas em BRT → UTC); nada alterado nele.
- Verificação: simulação de fuso (pedido 30/06 22h BRT deixa de contar em "hoje"; limites idênticos
  aos do `/marketplace`); `pytest -m "not integration"` 94 passed / 2 pré-existentes.

---

## 2026-07-05 — feat(eship): Console de API do eShip no Console de API (admin) + diagnóstico do envio

**Console de API do eShip.** A tela Administração > Console de API (antes só ML) ganhou um comutador
**Mercado Livre / eShip** no topo. O modo eShip: seleciona a CMIG (reusa `GET /integrations/eship/cmigs`,
apikey nunca exposta), digita a **função** RPC (templates: GetProduto/GetSaldoEstoque/GetOrdem/GetArmazem/
PostOrdem) + body JSON → `POST /admin/api-console/eship/execute`. O executor faz o POST **cru**
(`{base}/?api&funcao=...`, apikey no header), decodifica **latin-1** e devolve a resposta crua **incluindo
`erros`** (não passa pelo `client.call`, que os esconde). Guarda de UI: funções de escrita (Post/Put/Delete/
Cancela…) exigem confirmação. `funcao` validada por regex; `body_json` deve ser objeto. Admin-only.
- Backend: `routers/admin_api_console.py` (novo endpoint `/eship/execute`). Front: `ApiConsoleView.vue`
  (comutador + form eShip com estado separado; painel de Response compartilhado + destaque de `erros`).
- Auditado (consistency-auditor); HIGH incorporados (reuso do endpoint de CMIGs, `company_name`, guarda de
  escrita, validação de funcao/body, latin-1 no corpo). `npm run build` OK; smoke real contra a API (GetProduto
  → 200, apikey só no header).
- **Catálogo completo de funções (2ª iteração):** gerado do swagger oficial (`FRONTEND/.../eshipCatalog.json`,
  242 funções). A função virou **dropdown agrupado por módulo**; ao selecionar, um painel mostra os
  **parâmetros do body** (campo/tipo/obrigatório/descrição) e o body é **pré-preenchido com o template completo**
  (inclui aninhados como `cadastroDestinatario`/`produtos`). Adicionada a seção **Headers extras** (backend
  `/eship/execute` repassa headers do usuário, exceto `api`).

**Diagnóstico do envio (venda #2000017245325174).** O `webServicePostOrdem` falha com `MAR6076 Armazém não
encontrado` para qualquer valor. Causa: o armazém "Armazenaki_Aruja" (id 2) está com `codigo` **vazio** — a
API pública casa por código; o painel web funciona porque usa o **id** via endpoint interno (`mod=9&func=445&
idrs[]=2`). Mesmo usuário (86) nos dois. Pendente: Armazenaki cadastrar um `codigo` no armazém (ou vincular a
apikey). Nosso payload também precisa de `idTipo` (=104 p/ MIG) — a implementar por CMIG. Bug de endereço
(dict `{id,name}` do ML ia serializado ao WMS) **corrigido** no `_parse_address` (estado vira UF).

## 2026-07-04 — feat(eship): envio completo do pedido ao WMS (Ordem + NF-e + Etiqueta) — Fase 1 (manual)

**Objetivo:** o botão "Enviar ao eShip" passa a mandar a **Ordem + XML da NF-e + Etiqueta** (antes só
criava a Ordem). Correção também dos bugs conhecidos do módulo. Ordem correta confirmada com o ML:
NF-e autoriza → ML libera a etiqueta (`invoice_pending` bloqueia). Motor de NF-e = Faturador ML.

**Backend**
- `services/fiscal/order_docs.py` (novo) — fonte ÚNICA do XML fiscal **autorizado**: NF-e própria
  SEFAZ (`Invoice.xml_local_path`) → Faturador ML (download `/invoices/documents/xml/{iid}/authorized`,
  com validação de que o corpo é NF-e, não HTML de erro) → DC-e (`OrderDce`). `separation.py`
  (`_bundle_docs`/`_invoice_id_from_order`) passou a delegar a ele (de-dup).
- `integrations/eship/service.py` — `send_order_full` (Ordem→NF-e→etiqueta ZPL+PDF), idempotente por
  **claim atômico** dos selos (single-flight anti duplo-clique) + tolerante a parcial; `attach_file`
  sem `idTipoAnexo` (flags `inserirFiscal`/`atualizarTransporte` + strip do prolog `<?xml?>`);
  `extract_order_id` lê `ordem.id` aninhado; `extract_status` navega `corpo.body.dados[0].status.id`;
  `map_status` por **id** (1/2/3→handling, 6→ready_to_ship, 7/8→shipped, 10→cancelled); `cancel_order`
  reseta selos; `sync_order_status` envia `incluirInfo`; guard de **FULL** (não vai ao WMS);
  `FUNC_CANCELAR_ORDEM`=`webServiceCancelaOrdem`.
- `integrations/eship/router.py` — `POST /orders/{id}/send` (admin,ugo); **removido** o `/push` órfão.
- `models/order.py` + `Scripts SQL/122_eship_anexos.sql` — colunas `eship_nfe_attached`,
  `eship_label_attached`, `eship_dispatch_status`, `eship_dispatch_error`, `eship_dispatch_attempts`.
- `routers/orders.py` — serializer da lista expõe os campos eShip (selos na tela).

**Frontend**
- `OrderEShipActions.vue` — botão único **"Enviar ao eShip"** → `/send`; selos NF-e/Etiq; reenvio de
  pendências; toast granular em falha parcial.

**Auditoria:** consistency-auditor (plano) + quality-guardian/consistency-auditor/adr-consistency-checker
(fechamento) — HIGH corrigidos (validação de XML baixado, claim anti-duplo-anexo, remoção do `/push`,
guard de FULL no backend). Sem CRITICAL/BLOQUEADO. `pytest`: 33/33 eShip; suíte 94 passed / 2 falhas
pré-existentes; `npm run build` OK. **Pendente:** smoke em homologação + 1 envio real (dono) + migration
122. Fase 2 (rotina automática opt-in por CMIG + auto-emissão) virá em seguida (ADR-0018).

## 2026-07-04 — feat(admin): gestão de Galpões pelo Administrador Geral + fix menu "Minha Empresa"

**Galpões (admin):** o admin não tinha menu para cadastrar/gerir galpões (a única tela,
`settings/warehouse` role='go', estava órfã). O backend já suportava (GET /warehouse mostra todos;
POST/PUT/DELETE aceitam `go_id`; admin bypassa o gate `go_empresa`).
- `views/settings/WarehouseAdminView.vue` (novo) — CRUD: lista todos os galpões com o GO dono, form
  criar/editar com **dropdown de GO dono** (obrigatório, via `GET /goes`), CEP lookup, excluir
  (`DELETE /warehouse/{id}`; backend bloqueia 409 se houver usuário ativo).
- `router/index.js` rota `admin/galpoes` (role admin); `AppSidebar.vue` item "Galpões" (menu-key
  `config_galpoes`) + `_legacyMenus.admin`; `routers/profiles.py` `MENU_CATALOG` += `config_galpoes`.
  Sem mudança de lógica no backend.

**Fix menu "Minha Empresa" (go_id nulo):** o link montava `/goes/${go_id}/edit`; para usuário sem
empresa vinculada (backend só retorna `go_id` quando role=="go") virava `/goes/null/edit` → erro
`int_parsing` ao salvar. `AppSidebar.vue`: o link e o menu pai "Gestão" só aparecem quando existe
`authStore.user?.go_id`. `GoFormView.vue`: `goId` ignora `"null"/"undefined"`; navegação direta
redireciona com aviso; `updateGo` usa `goId.value`.

**Verificação:** `npm run build` OK; `py_compile` OK; `pytest -m "not integration"` 94 passed / 2
pré-existentes. Diffs aditivos sobre a base DC-e (nada revertido).

---

## 2026-07-04 — feat(dce): emissão de DC-e na SEFAZ AUTORIZADA (perfil Marketplace) + DACE (ADR-0017)

A MIG passa a emitir a DC-e das contas CPF **direto na SVRS** (perfil Marketplace, por conta e ordem),
substituindo o botão que abria o painel do ML. Validado ponta-a-ponta em homologação SEFAZ-PR
(status 107 → autorização cStat 100) com pedido real, iterando ao vivo com o certificado da MIG.

- **Descobertas da homologação:** soapAction obrigatório + `consStatServDCe`; chave inclui `tpEmit`
  (`...nDC(9) tpEmis tpEmit nSiteAutoriz cDC(6)...`); assinatura **sem prefixo ds:** (cStat 587);
  `infDec`/`infDCeSupl` obrigatórios; nome do destinatário fixo em homologação (cStat 598).
- **Remetente = endereço do Galpão** (IBGE resolvido por cidade+UF); **destinatário = idOutros**
  quando não há CPF do comprador (o ML não expõe).
- **DACE (PDF com QR)** — `dace.py` (reportlab) + `GET /orders/{id}/dace.pdf`.
- **Habilitação:** `CMIGFiscalConfig.dce_authorized` (fiscal-config) + cert central da MIG.
  Gate: sem autorização/cert → 501 (comportamento antigo). Deploy seguro (default bloqueado).
- **Frontend:** botão "Emitir DC-e" emite de verdade; "DACE (PDF)" baixa o documento.
- Módulos `services/fiscal/dce/*`; migrations 120/121; ADR-0017. Testes 8/8.

---

## 2026-07-04 — feat(admin): gestão de Galpões pelo Administrador Geral

O admin não tinha menu para cadastrar/gerir galpões (a única tela era `settings/warehouse`,
role='go', órfã). Backend já suportava (GET /warehouse mostra todos ao admin; POST/PUT/DELETE
aceitam `go_id`; admin faz bypass do gate `go_empresa`). Faltava a tela + menu.

- **`views/settings/WarehouseAdminView.vue`** (novo) — CRUD admin: lista todos os galpões (com
  o GO dono), form criar/editar com **dropdown de GO dono** (obrigatório, via `GET /goes`),
  CEP lookup, e excluir (`DELETE /warehouse/{id}`, backend bloqueia 409 se houver usuário ativo).
- **`router/index.js`** — rota `admin/galpoes` (role admin).
- **`AppSidebar.vue`** — item "Galpões" na seção Administração (menu-key `config_galpoes`) +
  `_legacyMenus.admin` (incl. `config_marketplaces` que faltava).
- **`routers/profiles.py`** — `MENU_CATALOG` += `config_galpoes` (aparece na Gestão de Perfis).
- Sem mudança de lógica no backend (endpoints `/warehouse` reusados). Tela órfã do GO
  (`settings/warehouse`) permanece como está (fora do escopo).
- **Verificação:** `npm run build` OK; `py_compile` OK; `pytest -m "not integration"` 94 passed /
  2 pré-existentes.

---

## 2026-07-04 — fix(go): "Minha Empresa" quebrava com go_id nulo (path /goes/null)

Ao salvar em Gestão > Minha Empresa, erro `int_parsing` em `go_id` (path recebia a string "null").
Causa: `AppSidebar.vue` montava `/goes/${authStore.user?.go_id}/edit`; para usuário sem empresa
vinculada (o backend só retorna `go_id` quando role=="go"), o link virava `/goes/null/edit` e o
PUT falhava.

- **`AppSidebar.vue`** — link "Minha Empresa" e o menu pai "Gestão" só aparecem quando existe
  `authStore.user?.go_id` (além da permissão `go_empresa`).
- **`GoFormView.vue`** — `goId` computed ignora `"null"/"undefined"`; navegação direta a
  `/goes/null/edit` mostra aviso e redireciona (não chama a API); `updateGo` usa `goId.value`.
- **Verificação:** `npm run build` OK.
- **Nota:** se algum usuário que É Gestor Operacional legítimo estiver sem `user.go_id` no banco,
  isso é um problema de vínculo de dados (separado) — o link some corretamente até o vínculo existir.

## 2026-07-04 — feat(dce): caminho de emissão SVRS (cliente + orquestração) com feature gate

Liga a emissão real da DC-e à SVRS (Ambiente Nacional / SEFAZ-PR), reaproveitando o transporte
mTLS/SOAP do NF-e. **Deploy seguro**: gated por `dce_authorized` + cert central — sem cert/autorização,
o botão mantém o comportamento atual (501 → painel).

- **dce_client.py**: SOAP mTLS com as URLs oficiais (autorização/consulta/status/evento, prod +
  homologação), envelope `dceDadosMsg` (ns `.../dce/wsdl/{servico}`), extração cStat/protocolo/chDCe.
- **dce_service.py**: mapeia pedido→DC-e (emit=CPF vendedor + endereço CMIG; marketplace=CNPJ MIG;
  dest=comprador+IBGE; itens), gera chave modelo 99, assina com A1 da MIG (reusa signer NF-e),
  transmite, persiste `order_dce`.
- **routers/orders.py**: `emit-dce` ligado ao serviço + `_dce_feature_ready` (gate faseado).
- **Smoke**: `POST .../platform-certificate/{profile}/status-check` + botão "Testar conexão SVRS"
  na telinha (valida cert+mTLS antes de emitir; espera cStat 107).
- **A confirmar em homologação**: wrapper `enviDCe`/indSinc e tags de retorno (padrão SEFAZ, best-effort).
- py_compile OK; testes DC-e 7 passed/1 skip; npm build OK.

---

## 2026-07-04 — feat(dce): fundação da emissão de DC-e perfil Marketplace (Fase 1, parcial)

Fundação para emitir a DC-e (Declaração de Conteúdo Eletrônica, modelo 68 / chave modelo 99) das
contas de vendedor CPF: a MIG assina com o A1 do CNPJ dela, por conta e ordem (perfil Marketplace,
tpEmit=1). Confirmado com o contador (aval + sem credenciamento) e contra fonte primária SVRS.

- **Migrations 120/121** (idempotentes): `platform_cert_configs` (A1 central do assinante),
  `order_dce` (DC-e por pedido — tabela própria, não reusa `invoices`), flags DC-e em
  `cmig_fiscal_config` (dce_authorized default 0/bloqueado + numeração), `ibge_municipios` (cache).
- **models/fiscal.py**: `PlatformCertConfig`, `OrderDce`, `IbgeMunicipio` + flags.
- **services/fiscal/dce/**: `chave_dce` (modelo 99 — **reconstrói a chave de um DACE real**),
  `xml_builder_dce` (infDCe tpEmit=1), `ibge` (cidade+UF→código, seed da API IBGE), `signer_cert`
  (resolvedor do A1 central), `exceptions`. Helper `services/fiscal/pfx_utils.validate_pfx`.
- **Cert central (telinha)**: `GET/POST /api/v1/marketplace-settings/platform-certificate/{profile}`
  (Super Admin) + view `MarketplaceCertificateView.vue` + rota + menu Administração → "Certificado
  do Marketplace". A MIG sobe o A1 (perfil `marketplace_dce`) por aqui.
- **Testes**: `test_dce_xml` (chave valida DACE real) + `test_dce_ibge` (normalização) — 7 passed,
  1 skip (XML precisa de lxml, roda no servidor). `npm run build` OK.
- **Ainda NÃO wired**: cliente SVRS (aguarda URLs WSDL), DACE (PDF), `dce_service` e a troca do stub
  `emit_dce`. O botão "Emitir DC-e" segue no comportamento atual até a homologação. Spike/plano em
  `sandbox/dce-spike/` (não versionado).

---

## 2026-07-03 — feat(eship): "Listar Produtos no eShip" escopado por empresa (CMIG) + Skill/Agente eShip

**Skill + Agente eShip** (estudo completo da API): criada a skill `eship-api` (`.claude/skills/eship-api/`
— SKILL.md + 6 references cobrindo os 12 módulos/289 funções, auth RPC, catálogo, produtos/estoque,
ordens/emissão/status, transporte/recebimento e gotchas) e o agente `eship-especialista`
(`.claude/agents/eship-especialista.md`). Base: OpenAPI oficial + sondagem read-only. Documentado o
backlog de correções (status por `id`, `webServiceCancelaOrdem`, `extract_order_id` aninhado,
`GetOrdem` exige `incluirInfo`, saldo por `codigoProduto`, cap de páginas etc.).

**Listar Produtos no eShip — escopo por empresa** (`integrations/eship/service.py`,
`EnvioProdutosView.vue`, `test_eship_products.py`): a tela trazia o catálogo inteiro do WMS
(multi-tenant, ~6.890 produtos de várias empresas). Agora traz **apenas os produtos da CMIG**, com
Full/físico/disponível/reservado. Como a API **ignora** os filtros de empresa do `webServiceGetProduto`
(comprovado ao vivo), o escopo é **client-side** casando `produto.cadastro.cnpj`/`cpf` (só dígitos) com
o documento da CMIG (helper `_produto_da_cmig`). `quantidadeRegistros=100` (teto honrado) reduz a
varredura de 304→~76 páginas. **Anti-vazamento LGPD:** CMIG sem CNPJ/CPF retorna vazio +
`escopo_indefinido` **sem** chamar o WMS (nas duas funções de listagem). `total` = itens da empresa;
`total_catalogo` = catálogo WMS. Frontend: removidos dropdown e coluna "Empresa" (redundantes) e aviso
quando falta documento. Auditado: consistency-auditor (prévia — C1/C2/H1/H2/H3 incorporados) +
quality-guardian (sem CRITICAL/HIGH; MEDIUM do `all=false` corrigido). 31 testes eShip passam; ruff
limpo; `npm run build` OK.

**Estoque real na listagem:** o `webServiceGetProduto` traz estoque **0** na lista (`saldoEstoque=[]`);
o estoque real vem do `webServiceGetSaldoEstoque` (já escopado ao depósito da conta). Enriquecimento
(`_fetch_saldo_indexes` + `_eship_produto_row(p, saldo)`) casando `GetProduto.id ==
GetSaldoEstoque.pro_produto_id` (fallback SKU), somando linhas (depósitos/lotes) e convertendo as
strings (`_num`). Verificado ao vivo: RS-WLQ=300, 438R=20, 320=2.

**Exportação PDF/Excel** (`integrations/eship/export.py`, endpoint `GET /cmigs/{id}/produtos/export?
format=pdf|xlsx`, botões no modal): reutiliza `list_all_eship_products` (escopado + estoque),
espelha o padrão de `services/sales_report_export.py` (reportlab/openpyxl). Guard anti
formula-injection no XLSX; escaping no PDF; `escopo_indefinido`→400. Auditado (quality-guardian: sem
CRITICAL/HIGH). 33 testes eShip; PDF/XLSX gerados e validados; `npm run build` OK.

---

## 2026-07-01 — style(sidebar): hierarquia pai × filho no menu lateral

Diferenciação visual dos menus no sidebar (AdminLTE dark), por hierarquia em vez de cor forte
(a 1ª tentativa em verde saturado no texto ficou pesada).

- **`AppSidebar.vue`** (`<style scoped>`): menu PAI (1º nível) branco + semibold; FILHOS cinza,
  menores, recuados e ligados por uma linha-guia vertical **verde** (`#20c997`); menu pai ABERTO
  com realce sutil (fundo levíssimo + barra de acento verde à esquerda via box-shadow inset, sem
  deslocar o texto). Submenu SELECIONADO com fundo verde água de bom contraste
  (`rgba(32,201,151,.28)`) + barra de acento + texto branco. "Sair" segue vermelho; item ativo
  preserva o realce do AdminLTE (especificidade maior). `npm run build` OK.

---

## 2026-07-01 — feat(separacao): botão "Baixar tudo (ZIP)" da gaiola (NF-e PDF + XML + etiquetas)

No workspace da gaiola (Separação > Separar Pedido), um único botão baixa um ZIP com todas as
etiquetas + DANFE (PDF) + XML das NF-e dos pedidos.

- **`routers/separation.py`** — novo `GET /carts/{cart_id}/bundle.zip` (`cart_bundle`): tenta emitir
  a NF-e faltante (`_bundle_ensure_nfe`, reusa claim atômico + `_sync_nfe`), coleta DANFE+XML
  (`_bundle_docs`: ML via `_ml.fetch_invoice_file`; própria via `Invoice.xml_local_path`+`gerar_danfe`),
  gera etiquetas (ML `get_shipment_label` por conta + `render_shipping_labels` manual), monta o ZIP
  (`_assemble_bundle_zip`, função pura) e **carimba** `nfe_printed_at`/`label_printed_at` nos incluídos
  (libera "Concluir"). Regra: **pedido só entra se a NF-e estiver autorizada**; quem falhar sai em
  `_avisos.txt`. Guard de gaiola `cancelled`/`delivered` (409). Escopo por galpão igual aos vizinhos.
- **`SeparationView.vue`** — botão "Baixar tudo (ZIP)" (spinner `downloadingBundle`, download blob,
  erro-blob, `refreshCart` no sucesso).
- **Verificação:** `tests/test_separation_bundle.py` (2) do empacotador; `pytest -m "not integration"`
  **80 passed / 2 pré-existentes**; `npm run build` OK. Auditado (quality-guardian + consistency-auditor)
  — sem CRITICAL/HIGH; MÉDIO (guard de status) corrigido.
- **Nota operacional:** gaiola grande faz muitas chamadas ML sequenciais — teto `_BUNDLE_MAX_ORDERS=200`;
  atenção ao `proxy_read_timeout` do nginx em gaiolas volumosas.

---

## 2026-07-01 — feat(cmig): colaboradores por seleção de AC ou convite por e-mail + aprovação do admin

Corrige o bug "conta nova não adiciona colaboradores" na tela **Contas MIG** e adiciona o fluxo de
convite. Commit `fbbc8da`, deploy validado em produção (migration 119 aplicada).

- **Causa do bug:** o `CollaboratorsModal` carregava `/users?role=ac`, que exige a permissão de menu
  `config_usuarios` → AC novo tomava 403 e o `catch` esvaziava o dropdown silenciosamente. Além disso
  uma conta nova pode ser o único AC (lista vazia) — sem caminho de convite.
- **Parte 1 (selecionar AC):** novo `GET /cmigs/{id}/collaborators/candidates` (acessível ao DONO,
  não exige `config_usuarios`) lista ACs ativos elegíveis; o modal usa isso e mostra erro em vez de
  esvaziar. `POST /cmigs/{id}/admins` valida usuário existe / é `ac` / está ativo (erro claro, não FK).
  Removido o campo legado "ID do AC" do `CmigDetailView`.
- **Parte 2 (convite + aprovação):** migration 119 (`user_invites`); `POST /cmigs/{id}/invites` (dono)
  cria convite + envia e-mail (se SMTP off, devolve o link); `GET/POST /invites/{token}` PÚBLICOS para
  o cadastro do convidado (`User` inativo, `pending_approval`); `GET /users/approvals` +
  approve/reject (admin geral) liberam o login (`is_active=True`). Nova view "Aprovações de Cadastro"
  (Administração, menu key `config_aprovacoes`) e página pública `/cadastro-convite/:token`.
- **Fluxo:** dono convida → pessoa se cadastra → admin geral libera → dono vincula pela lista.
- Auditado (consistency + quality): sem bloqueantes; lacunas de reject/órfão corrigidas (reject remove
  o usuário órfão p/ não bloquear o e-mail; approve resolve convite órfão). Pendências não-bloqueantes:
  expiração de convite (`expired` é dead code), cancel/resend, helper `assert_eligible_ac` duplicado.

### fix(db): isola executor do banco + pool/timeouts — reconciliação de drift (commit `bb93bd9`)

Durante o deploy acima, o backend crashou no startup (`AttributeError: ... ASYNCIO_DEFAULT_EXECUTOR_WORKERS`).
Causa: `main.py` (commitado) já referenciava o setting, mas `config.py` e `database.py` — que carregam a
correção de um incidente de executor esgotado (executor DEDICADO ao banco, isolado do default de
SEFAZ/DANFE/email; `tcp_connect_timeout` + `call_timeout`; `pool_size/max_overflow` parametrizados <20
sessões do ATP) — estavam como mudanças **locais não commitadas**. O deploy-operator corrigiu à mão no
servidor; em seguida commitei a correção de verdade (`bb93bd9`) e redeployei para eliminar o drift e
ativar a isolação do executor do banco (que ainda não estava viva em produção). Validado: `/docs` 200,
`/api/v1/cmigs` 401, endpoint que toca o banco ~49ms, PM2 estável. Ver ADR-0001.

---

## 2026-06-29 — feat(nfe): emissão própria SEFAZ — Fechamento (auditoria + ADRs)

Auditoria Full em paralelo (quality-guardian + consistency-auditor + adr-consistency-checker).
Achados CRITICAL/HIGH corrigidos antes de fechar:

- **CRITICAL (LGPD/IDOR):** XML autorizado era gravado em `static/uploads/nfe/...` (servido por
  HTTP sem auth → qualquer um com a chave baixava NF-e de terceiros). Movido para `NFE_XML_DIR`
  (`data/nfe_xml`, fora de `static/`, no `.gitignore`); download só pelo endpoint autenticado.
- **HIGH (DoS):** `distribuicao` agora usa parser lxml endurecido (`resolve_entities=False,
  no_network=True, huge_tree=False` — anti billion-laughs/XXE) e descompressão do `docZip` com
  **teto de 8 MB** em stream (anti zip-bomb). Conteúdo do DFe é de terceiros.
- **HIGH (ADR-0013):** `build_nota_emissao` usava `issue_date.astimezone(BR_TZ)` (errado p/ datetime
  naive → `dhEmi` deslocada ~3h). Trocado por `to_br(issue_date)`.
- **HIGH (paridade):** download de XML/DANFE da NF-e própria na tela **Saídas** (individual + export
  ZIP) usava `xml_url`/`danfe_url` do Focus (NULL na emissão própria). Corrigido: `xml_available`/
  `danfe_available` derivam de `status=authorized`+`xml_local_path`; `SaidasView` baixa pelos
  endpoints `/invoices/{id}/xml|danfe`; export lê o XML local e gera DANFE.
- **MEDIUM:** TLS sempre verificado em produção (`_verify_ssl(environment)` força `True` quando
  `producao`, anti-MITM no mTLS).
- **ADRs criadas:** [ADR-0015](DOCs/decisions/ADR-0015-emissao-propria-nfe-sefaz.md) (emissão própria
  SEFAZ + cofre do certificado + transmissão síncrona) e
  [ADR-0016](DOCs/decisions/ADR-0016-distribuicao-dfe-propria.md) (Distribuição DFe própria + NSU).
  Registradas no CLAUDE.md.
- **Verificação pós-fix:** `pytest -m "not integration"` → **78 passed / 2 pré-existentes**; smoke do
  parser DFe + teto zip-bomb (50 MB → cortado); `npm run build` OK; `py_compile` OK.
- **Pendências não-bloqueantes (registradas):** `emission_provider` default ainda `'focus'` (não dirige
  lógica); inutilização sem UI (fase futura); strings/docstrings "Focus" cosméticas; `inbound_source=
  'dfe_focus'` mantido como legado.

---

## 2026-06-29 — feat(nfe): emissão própria SEFAZ — Fase 4 (DANFE + inutilização + e-mail próprio)

- **`services/fiscal/sefaz/danfe.py`** (novo) — `gerar_danfe` (BrazilFiscalReport) a partir do XML
  autorizado; `empacotar_nfeproc` (NFe assinada + protNFe) e `extrair_protNFe`. **`sefaz_service.emitir`**
  passa a gravar o **procNFe** completo (não só a NFe assinada) p/ DANFE/XML.
- **`routers/invoices.py`** — `GET /{id}/xml` (procNFe) e `GET /{id}/danfe` (PDF on-the-fly);
  `POST /{id}/email` reativado via **SMTP próprio** com XML+DANFE em anexo; `POST /inutilize`
  reativado via SEFAZ.
- **`services/fiscal/sefaz/inutilizacao.py`** (novo) — `inutilizar_nfe` (NfeInutilizacao4, cStat 102) +
  endpoints `inutilizacao` no catálogo RJ/SVRS e SP. Adaptador `sefaz_service.inutilizar`.
- **`services/email_service.py`** — `send_email` ganha `attachments` (XML/PDF).
- **Frontend** — `InvoiceDetailView.vue`: botões "Baixar XML/DANFE" agora baixam por blob dos novos
  endpoints (em vez das URLs do Focus). `npm run build` OK.
- **requirements.txt** — `brazilfiscalreport>=1.0`.
- **Verificação:** DANFE PDF gerado de um XML 4.00 montado (4.8 KB, `%PDF`); `pytest -m "not
  integration"` → **78 passed / 2 pré-existentes**; `py_compile` OK; `npm run build` OK.

---

## 2026-06-29 — feat(nfe): emissão própria SEFAZ — Fase 3 (Distribuição DFe própria + remoção do Focus)

Entrada (NF-e recebidas) deixa de depender do Focus: passa pela **Distribuição de DFe** própria
(NFeDistribuicaoDFe, Ambiente Nacional). Focus removido por completo do backend.

- **`services/fiscal/sefaz/distribuicao.py`** (novo) — `consultar_dfe` monta `distDFeInt` v1.01
  (envelope `nfeDistDFeInteresse>nfeDadosMsg`), consulta por `distNSU/ultNSU`, decodifica `docZip`
  (base64+gzip), classifica schema (NFe completa/resumo/evento). Trata cStat 138/137/656 e
  `ultNSU==maxNSU` (sem mais). Estrutura/versão confirmadas na NT 2014.002 (Portal NF-e/MOC).
- **`services/fiscal/sefaz/cancelamento.py`** — `manifestar` (Ciência 210210 / Confirmação 210200 /
  Desconhecimento 210220 / Operação não realizada 210240) ao **Ambiente Nacional** (cOrgao=91,
  endpoint `SEFAZ_EVENTO_AN`).
- **`services/fiscal/dfe_service.py`** — reescrito: `sync_received_for_cmig` faz o loop
  ultNSU→maxNSU (bounded), upsert em `dfe_recebidos`, cria Invoice de entrada das NF-e completas
  novas e persiste `cfg.ultimo_nsu`. `_create_invoice_from_xml` (sem download Focus). Filtro de
  CMIGs passa a `cert_path` (não mais `focus_company_token`). `process_received_nfe` removido.
- **`services/fiscal/sefaz_service.py`** — `manifestar(db, inv, cmig, cfg, tipo, justificativa)`.
- **`routers/invoices.py`** — `manifest` via SEFAZ; `inutilize` retorna 501 (fase futura). `email`
  já era 501. `sync-received` reusa o novo `sync_received_for_cmig`.
- **`routers/webhooks.py`** — `/focus-nfe` e `/focus-nfe-recebida` **removidos**.
  **`tasks/fiscal_alerts.py`** — `_refresh_stale_invoices` agora é a consulta N-6 SEFAZ pela chave.
- **`config.py`** — settings `FOCUS_*` removidas. **`services/fiscal/focus_service.py` DELETADO**
  (sem referências remanescentes). ORM `DFeRecebido` (models/fiscal.py).
- **Verificação:** `pytest -m "not integration"` → **78 passed / 2 falhas pré-existentes**;
  `py_compile` OK em todo o conjunto.
- **A confirmar em homologação** (não testável sem cert + AN): endpoints AN da Distribuição/Recepção
  de Evento e o `versao=1.01` do `distDFeInt` — validar antes do go-live; ajustáveis no catálogo
  `SEFAZ_DFE_AN`/`SEFAZ_EVENTO_AN`. **Pendente:** DANFE (Fase 4) + inutilização + email SMTP próprio.

---

## 2026-06-29 — feat(nfe): emissão própria SEFAZ — Fase 1 (núcleo + emissão manual)

Camada fiscal própria portada do projeto NFE_VendasProduto (validado cStat=100) e adaptada ao
Sistema Drop; o botão "Transmitir SEFAZ" da emissão manual deixa de usar o Focus.

- **Camada pura** `services/fiscal/sefaz/`: `exceptions`, `models` (dataclasses Decimal),
  `chave` (DV mód 11 + cNF), `xml_builder` (NFe 4.00; **CSOSN 102 e 500**, **PIS/COFINS CST 99**,
  **sem IPI**, **sem ICMSUFDest** — correções fiscais do Consultor-Fiscal-NFE; `idDest` calculado;
  devolução finalidade 4 com refNFe), `signer` (XMLDSig SHA-1 via signxml), `sefaz_client`
  (SOAP 1.2 + mTLS urllib3 + SECLEVEL=1/OP_LEGACY; catálogo RJ/SVRS + SP; PEM temporário em dir
  restrito), `emitter` (pipeline indSinc=1), `consulta` (N-6), `cancelamento` (110111 + CC-e 110110
  com xCondUso e limites). Testes `tests/test_sefaz_fiscal.py` (7) — DV com vetor real, CSOSN
  102/500, CST 99, sem IPI/ICMSUFDest, idDest intra/inter. Assinatura SHA-1 verificada com cert
  self-signed (rsa-sha1 + X509 único).
- **Adaptador** `services/fiscal/sefaz_service.py` — `build_nota_emissao` (Invoice/CMIG/Person/
  CMIGProduct → NotaEmissao), `reservar_numero` (PL/SQL `NFE_NEXTVAL_MANUAL`, congela chave/cNF
  antes da SEFAZ), `resolve_cert` (decifra senha), `emitir`/`cancelar`/`carta_correcao`/`consultar`
  (bloqueantes via `asyncio.to_thread`; log em `invoice_sefaz_logs`; XML salvo em
  `static/uploads/nfe/{cmig}/{chave}.xml`). Pré-valida cadastros (IBGE/IE/NCM) antes de consumir
  numeração. Gating de produção (`production_released`).
- **`routers/invoices.py`** — `transmit`/`cancel`/`correction-letter`/`refresh-status` desviados
  para `sefaz_service` (refresh agora é a consulta N-6 pela chave). `email` desabilitado no MVP
  (501). `_validate_ready_to_transmit` passa a exigir `cert_path`+`manual_nfe_serie`. `_apply_authorized`
  (Focus) removido.
- **`models/cmig.py` + migration `118_cmig_ibge.sql`** — `cmigs.ibge_code` (cMunFG/enderEmit).
  **`models/fiscal.py`** — ORM `InvoiceSefazLog`. **requirements.txt** — `lxml`/`signxml`/`urllib3`.
- **Frontend** — textos "Focus" → "SEFAZ" em InvoiceForm/InvoiceDetail/Entradas/Saídas/CmigDetail/
  _helpers. `npm run build` OK.
- **Verificação:** `pytest -m "not integration"` → **78 passed / 2 falhas pré-existentes**
  (`test_orders.py` MockResult.scalar, não relacionadas). `npm run build` OK. `py_compile` OK.
- **Pendente (próximas fases):** Distribuição DFe própria (entrada), DANFE (BrazilFiscalReport),
  e o **smoke real em homologação RJ/SP** (exige cert A1 + `NFE_CERT_MASTER_KEY` + migrations
  115-118 no Oracle + cadastro completo da CMIG: IBGE, IE, série manual). Limpeza final do
  `focus_service` só após a Distribuição DFe (entrada ainda o usa).

---

## 2026-06-28 — feat(nfe): emissão própria SEFAZ — Fase 0 (fundação), substituindo Focus

Início da troca do provedor Focus NFe por emissão própria direta à SEFAZ (mTLS + XMLDSig + SOAP),
reaproveitando os models existentes (CMIG=emitente, Person=cliente, CMIGProduct=produto,
Invoice/InvoiceItem=nota). Mantém intacta a NF-e dos pedidos de marketplace (Faturador ML). Plano
e correções fiscais validadas pelo Consultor-Fiscal-NFE (DIFAL não se aplica ao Simples — Tema 1093;
PIS/COFINS CST 99; ST de revenda = CSOSN 500). **Fase 0 entregue e verificada:**

- **Migrations** `Scripts SQL/115_nfe_sefaz_config.sql` (cmig_fiscal_config: `cert_path`,
  `cert_pass_encrypted`, `production_released`, `manual_nfe_serie`/`manual_nfe_next_number`(`_homolog`),
  `aliquota_fecp`, `ultimo_nsu`), `116_invoice_sefaz.sql` (invoices: `auth_protocol`/`sefaz_cstat`/
  `sefaz_xmotivo`/`environment`/`emission_provider` + tabelas `invoice_sefaz_logs` append-only com
  trigger imutável e `dfe_recebidos` p/ Distribuição DFe própria), `117_nfe_nextval.sql` (função
  PL/SQL `NFE_NEXTVAL_MANUAL` — numeração atômica por ambiente). Idempotentes (DECLARE/EXCEPTION).
- **`services/fiscal/cert_crypto.py`** — cifra a senha do certificado A1 (Fernet, master key
  `NFE_CERT_MASTER_KEY`) para repouso no banco. Teste `tests/test_cert_crypto.py` (4 passed).
- **`routers/fiscal_config.py`** — `register-focus` removido; `POST /certificate` reescrito: grava o
  `.pfx` em diretório restrito (`NFE_CERTS_DIR`, fora de static/) + senha cifrada no banco; série
  manual SEFAZ/produção/FECP editáveis com validação anticolisão com a série do marketplace.
- **`config.py`** — settings `NFE_CERT_MASTER_KEY`, `NFE_CERTS_DIR`, `NFE_ICP_CABUNDLE`,
  `NFE_VERIFY_SSL`, `NFE_DFE_AN_HOMOLOG/PROD`, `NFE_SEFAZ_TIMEOUT`. **`.gitignore`** ignora
  `.secrets/`/`*.pfx`. **models/fiscal.py** — novas colunas no ORM (CMIGFiscalConfig + Invoice).
- **Frontend** — `CmigFiscalConfigCard.vue` (removido bloco/modal Focus; novo certificado A1 SEFAZ
  sem token mestre, série manual + nº por ambiente + FECP + toggle "Produção liberada") e
  `FiscalConfigView.vue` (textos Focus → SEFAZ). `npm run build` OK.
- **Variáveis de ambiente novas (provisionar no `.env`, nunca commitar):** `NFE_CERT_MASTER_KEY`
  (string aleatória longa — perder a key inutiliza as senhas cifradas), `NFE_CERTS_DIR`,
  `NFE_VERIFY_SSL` (True só em produção, com cabundle ICP-Brasil), `NFE_ICP_CABUNDLE`.
- **Próximo:** Fase 1 — camada pura `services/fiscal/sefaz/` (chave/xml_builder/signer/sefaz_client/
  emitter/consulta) + `sefaz_service` + desvio do `transmit`. **Bloqueio:** idealmente portar o
  `fiscal/` do projeto-fonte (NFE_VendasProduto, cStat=100) — confirmar disponibilidade.

---

## 2026-06-28 — docs(fiscal): agente Consultor-Fiscal-NFE + skill fiscal-tributario-nfe

- **Novo agente** `.claude/agents/Consultor-Fiscal-NFE.md` — especialista fiscal-tributário e de
  documentos fiscais eletrônicos (NF-e/NFC-e/CT-e/MDF-e). Mesmo padrão do
  `mercado-livre-especialista`: regra de ouro anti-erro (nunca cravar alíquota/regra sem ancorar na
  legislação vigente — LC 123, RICMS da UF, NT da SEFAZ — e/ou testar em homologação), mapa de
  referências da skill, contexto do módulo fiscal do Drop (CRT, snapshot imutável, ADR-0008/0009).
- **Nova skill** `.claude/skills/fiscal-tributario-nfe/` (progressive disclosure, padrão da
  `mercado-livre-api`): `SKILL.md` + 6 referências:
  - `regimes-tributarios.md` — Simples (anexos, Fator R, alíquota efetiva, DAS, segregação),
    Lucro Presumido (presunção IRPJ/CSLL, PIS/COFINS cumulativo) e Lucro Real (lucro ajustado,
    PIS/COFINS não-cumulativo) + apuração e Reforma Tributária.
  - `credito-debito-impostos.md` — não-cumulatividade, ICMS próprio, ICMS-ST (MVA/IVA ajustada),
    DIFAL EC 87/2015, FECP, IPI, PIS/COFINS, ISS, apuração débito−crédito.
  - `emissao-nfe.md` — modelos 55/65, config do emitente, anatomia da NF-e 4.00, campos que
    rejeitam, ambientes/status, finalidades, contingência, DANFE, NT 2025.002.
  - `eventos-fiscais.md` — árvore de decisão "errei a nota e agora?", CC-e, cancelamento,
    inutilização, complementar/ajuste/devolução, manifestação do destinatário, denegação.
  - `documentos-transporte.md` — CT-e, MDF-e, `modFrete` (CIF/FOB), grupo de transporte da NF-e.
  - `tabelas-fiscais.md` — origem, CST ICMS, CSOSN, CST IPI/PIS/COFINS, CFOP, NCM/CEST, indicadores.
- SKILL.md e agente apontam para `DOCs/guia-implementacao-nfe-oracle.md` como fonte do **código**
  (DDL/SOAP/mTLS/A1), reservando a skill para a **regra fiscal**.

---

## 2026-06-28 — feat(relatorios): menu pai "Relatórios" + tela "Vendas do Mês" (grid + PDF/Excel)

- **Menu pai "Relatórios"** (nav-treeview) com 2 submenus: "Relatórios em PDF" (= o atual
  `/cmig-reports`, movido de "Minhas Contas", sem mudar rota) e "Vendas do Mês" (novo
  `/relatorios/vendas-mes`, menu_key `relatorio_vendas`). MENU_CATALOG e _legacyMenus
  (admin/ac/go) atualizados; cmig_reports realocado p/ seção RELATÓRIOS.
- **Vendas do Mês** (por conta de marketplace + mês): grid agregado por produto com
  qtd vendida (BRUTA), cancelada, **entregue** (= entregues + despachados/a caminho:
  `shipment_status` ∈ shipped/delivered/in_transit/out_for_delivery/first_visit), custo,
  venda, lucro bruto, % do lucro, Taxa/Frete **rateados** proporcionalmente à venda,
  **LL Parcial** (= Lucro Bruto − Taxa − Frete) e **% do LL Parcial**. Líquido =
  vendida−cancelada alimenta venda/custo. Custo = `OrderItem.unit_cost` (fallback
  `cost_price` do produto; flag `custo_incompleto`). Mês via `COALESCE(paid_at, created_at)`
  com bounds BR→UTC. Totais de Taxa/Frete somados **por ORDER** (sem double-count).
- Backend: `services/sales_report_service.py` (build + resync), `services/sales_report_export.py`
  (PDF reportlab + Excel **openpyxl** — nova dep em requirements.txt), `routers/sales_report.py`
  (`GET /reports/monthly-sales`, `POST .../refresh`, `GET .../export?format=pdf|xlsx`;
  `require_role("admin","ac","go")` + `_get_account_or_403`). Registrado em main.py.
- "Atualizar" re-sincroniza os pedidos da conta no período (reusa `sync_ml_integration`);
  token expirado retorna aviso específico; demais falhas degradam mostrando os dados salvos.
- Frontend: `views/reports/MonthlySalesView.vue`. Testes: tests/test_sales_report.py. Suite 67/2.
- Auditorias quality/consistency: 2 HIGH corrigidos (removido `ugo` do guard; token expirado
  tratado à parte). **DEPLOY: `pip install -r requirements.txt` no servidor (nova dep openpyxl).**

---

## 2026-06-28 — feat(estoque/anúncios): teto do fixo, pausa/reativação automática e sync horário de metadados ML (ADR-0014)

Revisão do ciclo de estoque dos anúncios + sincronização com o ML. 5 pontos pedidos pelo dono:

1. **Estoque fixo vira TETO** — `sync_stock` e publish/edit enviam `min(fixed_quantity,
   disponível)`; nunca anuncia mais do que existe. Fixo sem vínculo de produto mantém o valor
   puro (anúncio isca). (`tasks/sync_stock.py`, `routers/anuncios.py`)
2. **Pausa/reativação automática** — nova coluna `product_listings.auto_paused` (migration 114).
   Não-FULL com disponível (LOCAL+FULL via `available_to_push` puro) = 0 → `paused`; quando volta
   → `active`. Só reativa o que o SISTEMA pausou; nunca um anúncio pausado manualmente. Query do
   job reinclui `auto_paused=True` para poder reativar. Respeita ADR-0008.
3. **PG→FULL já vira CMIG** (ADR-0010) — confirmado, sem mudança.
4. **FULL identificado no anúncio (derivado na leitura)** — `_serialize_listing` expõe
   `has_full_stock`, `full_cmig_product_id` e saldos Local (PG/CMIG) + FULL (sempre CMIG), via
   `load_full_per_account_map` (batch, sem N+1). Sem coluna redundante: o gatilho é o crédito da
   NF-e em `full_stock`.
5. **Job horário `sync_listings_from_ml`** — traz do ML título/preço/promoções (Seller Promotions
   v2 — `deal_ids`/`original_price` não são confiáveis)/descrição/status/`logistic_type`-FULL/
   atributos/fotos/categoria/visitas. **NÃO traz estoque** (`skip_stock=True`). Padrão
   `tracked_job`+`task_db`, sequencial por conta, rollback por conta. Registrado no scheduler
   (`IntervalTrigger(hours=1)`). Nova `ml_service.get_item_promotions`.

Helper `_apply_ml_item_to_listing` estendido (skip_stock/category/visits/promo + limpa
`auto_paused` quando o ML mostra ativo); import inline ganhou a mesma limpeza (paridade — 1 HIGH
da auditoria). Auditado por quality-guardian + consistency-auditor + adr-consistency-checker
(sem CRITICAL/HIGH em aberto). `py_compile` OK; `pytest -m "not integration"` 65 passed (2 falhas
pré-existentes em `test_orders.py`, não relacionadas). **Pendente:** rodar migration 114 no Oracle.

## 2026-06-28 — fix(anuncios): troca de categoria do anúncio agora é enviada ao ML

Bug: ao editar e trocar a categoria, o backend salvava `listing.category_id` mas fazia
`ml_payload.pop("category_id")` → o ML ficava com a categoria antiga (divergência
silenciosa, sem aviso). O ML PERMITE trocar categoria via PUT; a regra é compatibilidade
(item com venda só vai p/ categoria compatível, senão recusa com `item.category_id.invalid`).

- `_try_apply_category_change(token, listing, new_attributes, old_category_id, old_attributes_json)`:
  PUT isolado de categoria (+ atributos da nova categoria). Sucesso → aplica; recusa
  (exceção OU `category_id` em `_skipped_fields`/eco divergente) → REVERTE
  `category_id`/`attributes_json` locais (sem divergência DB↔ML) e retorna aviso.
- `update_anuncio`: detecta troca (old vs body), roda o passo isolado ANTES do PUT principal;
  o principal segue sem `category_id` e, quando a categoria mudou, sem `attributes`
  (já tratados). Expõe `result["ml_category_warning"]`.
- Frontend (`saveWizard`): `toast.warning` do `ml_category_warning` (e do `ml_pictures_warning`,
  que era retornado mas não exibido). **Não** persiste a categoria no produto quando o ML
  recusou (senão re-tentaria a categoria rejeitada na próxima edição) — fix de 1 HIGH da auditoria.
- Decisão do dono: avisar e manter a categoria antiga quando o ML recusar (não recriar).
- DESCARTADO: guiar por `/items/{id}/available_upgrades` — teste real mostrou que esse
  endpoint retorna UPGRADES DE TIPO DE ANÚNCIO (Premium/Diamante), NÃO categorias compatíveis.
  Não há endpoint ML confiável p/ "categorias compatíveis"; o próprio PUT já valida (atende).
- Testes: tests/test_anuncios_category.py (sucesso/skipped/exceção). Suite 65/2 (baseline).
- Auditorias quality/consistency sem CRITICAL; 1 HIGH (persist da categoria rejeitada) corrigido.

---

## 2026-06-28 — feat(eship): catálogo inteiro no modal — ordenar, filtrar por empresa, paginar na tela

Modal "Listar produtos no eShip" passou a carregar o CATÁLOGO INTEIRO de uma vez
(decisão do dono) para ordenação/filtro globais:
- Backend `list_all_eship_products(db, cmig_id, force)`: busca a 1ª página (revela
  total), demais páginas com `asyncio.Semaphore(12)` + `asyncio.wait_for` (deadline
  agregado 45s), teto 300 páginas. Cache em memória por CMIG (TTL 300s; `refresh=true`
  recarrega). Endpoint `?all=true&refresh=bool`.
- Frontend: ordenação por coluna (Código, Cód. barras, Descrição, Empresa, Status),
  **dropdown de empresas** (montado dos dados), busca textual, paginação client-side
  (50/pág) e botão recarregar.
- Robustez (auditoria, 2 HIGH corrigidos): páginas que falham viram buraco SINALIZADO
  (`parcial`/`paginas_falhas` + banner "Catálogo parcial…"), e carga parcial NÃO é
  cacheada (não fixa catálogo furado por 5min); deadline agregado evita estourar o
  proxy. Guard no parse de `quantidadePaginas`.
- Testes: +1 (página falha → parcial + sem cache); cache limpo entre testes. Suite 62/2.
- DEPLOY: confirmar `proxy_read_timeout` do nginx ≥ 60s (1ª carga pode levar ~20-40s).

---

## 2026-06-27 — feat(eship): listar produtos do WMS (Integração → Produtos)

- Submenu/H1/meta.title "Envio de Produtos" → **"Produtos"** (path /integracao/envio-produtos
  inalterado). Mantidas as funções existentes (enviar ao WMS, saldo).
- Botão "Listar produtos no eShip" por CMIG → modal (Bootstrap modal-xl) com tabela paginada
  (Anterior/Próxima) + filtro client-side na página carregada. Colunas: código, cód. barras,
  descrição, empresa, status, Full, e estoque (físico/disponível/reservado).
- Backend: `service.list_eship_products(db, cmig_id, page)` chama `webServiceGetProduto`
  (`{"pagina": N}`, 25/pág) e mapeia via `_eship_produto_row` (info + estoque já vêm no
  GetProduto: totalFisico/totalDisponivel/totalReservado/itsFull). Endpoint
  GET /integrations/eship/cmigs/{id}/produtos (admin/ugo/ac + _assert_cmig_access).
- Fix de segurança (auditoria HIGH): `_assert_cmig_access`/`_accessible_cmig_ids` — ugo com
  `warehouse_id` nulo deixava de barrar CMIG órfã (None != None). Corrigido (afeta também
  /saldo e /push-products).
- Testes: +3 em tests/test_eship_products.py. Suite 60/2 (baseline MockResult).
- LIMITAÇÃO conhecida: o `webServiceGetProduto` retorna o catálogo do ARMAZÉM INTEIRO (todas
  as empresas do 3PL, ~6850 itens), não só da CMIG — não há filtro server-side que funcione.
  A coluna "Empresa" identifica o dono de cada SKU; filtro client-side ajuda. Escopo por
  empresa fica como follow-up (depende de parâmetro de filtro do eShip).

---

## 2026-06-25 — fix(eship): client detecta erro de negócio em HTTP 200 (`erros`)

Diagnóstico: "33 produtos enviados" era FALSO — nada foi cadastrado no WMS. Causas:
1. O eShip responde HTTP **200 mesmo em erro**, sinalizando no corpo `erros`
   (ex.: `{"erros":[{"erro":{"mensagem":"Função ... não existe.","codigo":"MAP0014"}}]}`).
   O `client.call` só checava o status HTTP → contava o erro como sucesso.
2. Teste direto na API (apikey do dono): `webServicePostProduto`, `webServicePostOrdem`,
   `webServiceGetOrdem`, `webServicePostVariacao`, `webServicePostEntrada`,
   `webServiceGetCadastro` → TODAS retornam `MAP0014 "função não existe"`. Só
   `webServiceGetProduto` e `webServiceGetSaldoEstoque` estão habilitadas para essa
   apikey/conta Armazenaki. Ou seja, as funções de ESCRITA (cadastro de produto, envio
   de ordem) não estão habilitadas para a chave — é config do lado do eShip, não do código.

Correção (código): `client.call` agora inspeciona `data["erros"]` e levanta `EShipError`
com a mensagem/código reais (`_extract_eship_error`, tolerante a formatos). Resultado: o
sistema deixa de reportar falso "enviado" — passa a mostrar o erro real (ex.: MAP0014).
Aplica-se a TODAS as funções eShip (produto, ordem, saldo).
- Testes: tests/test_eship_client.py (5 casos: erro em 200, sucesso erros=null/[], !=200,
  texto puro). Suite 57/2 (baseline MockResult).
- AÇÃO DO DONO (fora do código): pedir ao eShip/Armazenaki para habilitar as funções de
  escrita (webServicePostProduto, webServicePostOrdem…) na apikey de integração. Também:
  `webServiceGetProduto` ignora o filtro por SKU (retorna catálogo inteiro) — confirmar o
  parâmetro correto na spec.

---

## 2026-06-25 — feat(eship): cadastro em lote do catálogo da CMIG no WMS

Nova ação "Enviar produtos ao WMS" na tela Integração → Envio de Produtos: pré-cadastra
todo o catálogo de uma CMIG no eShip (independente de pedido). Antes, produtos só iam ao
WMS como efeito colateral do envio de um pedido.

- `service.push_cmig_products(db, cmig_id)`: resolve creds por CMIG (`creds_from_cmig`),
  lê CMIGProduct + `selectinload(variants)`, monta SKUs (produto c/ variações = 1 por
  variante usando `CMIGProductVariant.sku` + EAN do pai; sem variações = `sku_cmig`/title/
  ean; ignora sem SKU; dedup por SKU truncado em 15) e faz upsert (`webServicePostProduto`,
  idempotente). Best-effort: retorna `{total, sent, failed, errors}`.
- Concorrência limitada (Semaphore=5) — corta o tempo total p/ não estourar o timeout do
  proxy num catálogo grande, sem inundar o WMS (correção do HIGH da auditoria).
- Resposta inclui `sent_skus` (lista ordenada dos SKUs enviados) além de `errors`; a tela
  mostra "Ver SKUs enviados" (lista recolhível) e "SKUs com erro" — antes só a contagem.
- `_produto_payload(sku, descricao, gtin, creds)`: builder genérico reusado pelo caminho de
  pedido (`build_produto_payload`) e pelo lote.
- Router: `POST /integrations/eship/cmigs/{cmig_id}/push-products` (admin/ugo/ac +
  `_assert_cmig_access`, EShipError→502) — mesmo padrão de `get_saldo`.
- Frontend (EnvioProdutosView.vue): botão por CMIG (só se ativo+configurado), confirm,
  spinner, resumo enviados/falhas + SKUs com erro. Texto "Como funciona" atualizado.
- GTIN/EAN: o caminho de **pedido** (`upsert_produto`) também passou a enviar o EAN — antes
  ia vazio porque o `OrderItem` não tem coluna `ean`. Novo `_resolve_item_ean(db, item)`
  busca o EAN do produto vinculado (`CMIGProduct.ean` ou `CatalogProduct.ean`). O caminho de
  lote já enviava o EAN do produto.
- Testes: tests/test_eship_products.py (12 casos). Também consertado teste stale
  test_eship.py::test_build_ordem_payload (assinatura/payload desatualizados, veio nos
  commits puxados). Suite 49/2 (baseline MockResult).
- Auditorias quality/consistency/adr sem CRITICAL; HIGH (request bloqueante) corrigido.
- Obs.: garantir `proxy_read_timeout` adequado no nginx p/ catálogos grandes (deploy).

---

## 2026-06-24 — fix(anuncios): reloginho de custos reflete o recálculo + consulta silenciosa

Dois ajustes na Gestão de Anúncios:
- **Reloginho (costs_cached_at)** não virava "agora" após o recálculo em segundo plano.
  Causa: `GET /anuncios/{id}/costs` regravava `costs_cached_at` no banco mas NÃO devolvia
  o campo, e o `fetchCost` não atualizava `listing.costs_cached_at` (o reloginho lê esse
  campo). Correção: endpoint passa a devolver `costs_cached_at` (ISO) e o `fetchCost`
  grava em `listing.costs_cached_at` após sucesso → o card vira "agora" assim que o lote
  termina, sem recarregar a lista.
- **"Consultando..."** removido: o spinner durante o recálculo dos custos saiu; a tela
  mantém os valores cacheados enquanto consulta em segundo plano (silencioso). O ref
  `loadingCosts` segue como guarda de concorrência (sem indicador visual).
- Verificado: py_compile, npm run build.

---

## 2026-06-24 — feat(anuncios): preserva foto específica por variação no envio ao ML (opção 2)

O dono testou no servidor: o anúncio com variações foi atualizado, mas as variações
perderam a foto específica (passaram a herdar as do topo). Trocado para PRESERVAR a
foto de cada variação, replicando o fluxo de 2 etapas da publicação com variações.

- ETAPA 1 (já existia): `_clear_stale_variation_picture_ids` zera picture_ids no 1º
  PUT (senão o ML rejeita as antigas inválidas).
- ETAPA 2 (nova): `_resync_variation_pictures` — do `pictures` que o ML devolve monta
  url→picture_id, resolve a foto de cada variação (via `_pictures_urls`) e faz 2º PUT
  (`update_item_variations`) com a lista COMPLETA de variações (regra de ouro do ML).
  Persiste os picture_ids no `variations_json`. Best-effort: nunca derruba o sync
  (captura inclusive timeout/connect do httpx) — degrada com aviso `ml_pictures_warning`.
- `_consolidate_with_variation_pics`: inclui as fotos de cada variação no array do topo
  (cap 12) p/ o ML lhes atribuir picture_id. Avisa se alguma variação ficou sem foto
  (estouro do limite de 12).
- Aplicado nos DOIS caminhos (sync_listing_to_ml e update_anuncio) — paridade. Reusa
  os helpers da publicação (`_consolidate_unique_pictures`, `_build_url_to_pic_id_map`,
  `_resolve_picture_ids_for_variation`, `ml_service.update_item_variations`).
  `publish_anuncio_with_variations` não foi tocado (já fazia as 2 etapas).
- Testes: +6 casos em tests/test_anuncios_helpers.py (consolidação, urls_by_id, persist,
  resync resolve por variação com lista completa, no-op). Suite 40 passed / 2 baseline.
- Auditorias: consistency (plano) + quality (impl). 1 HIGH corrigido (etapa 2 captura
  erros de transporte, não só HTTPException — evita 500 após o 1º PUT já aplicado).
- Verificado: py_compile, 15 testes do módulo verdes, npm run build, pytest 40/2.

---

## 2026-06-24 — fix(anuncios): zera picture_ids de variação ao enviar fotos (paridade sync ↔ wizard)

Bug: "Enviar Anúncio ao Marketplace" (`sync_listing_to_ml`) dava
`item.picture.invalid` em `item.variations.picture_ids` para anúncios COM
variações — o ML rejeitava picture_ids antigas com caminhos locais
(`/static/uploads/media/...`). O caminho gêmeo `update_anuncio` (wizard
"Salvar e Enviar") já tratava isso; o sync não — disparidade entre os dois.

- `_clear_stale_variation_picture_ids(ml_payload, listing)` (novo helper): quando
  envia `pictures` e o listing tem `variations_json`, seta
  `variations=[{id, picture_ids: []}]` (variações herdam as fotos do topo).
  Decisão do dono: herdar do topo (mesmo comportamento do wizard).
- `sync_listing_to_ml`: passa a chamar o helper (o fix). `update_anuncio`: bloco
  inline substituído pela chamada ao helper (DRY, sem mudança de comportamento).
- Top-level `pictures` continua absolutizado por `_absolutize_image_url`
  (PUBLIC_BASE_URL) — o erro só citava variations, não pictures.
- Teste novo `tests/test_anuncios_helpers.py` (9 casos) cobrindo
  `_clear_stale_variation_picture_ids` e `_strip_unwritable_stock` (blinda os dois
  fixes recentes). Suite: 34 passed / 2 (baseline MockResult).
- Verificado: py_compile, 9 testes novos verdes, npm run build, pytest 34/2.
  Auditorias quality/consistency sem CRITICAL/HIGH (paridade confirmada;
  nenhum outro PUT /items com fotos+variações ficou sem o guard).

---

## 2026-06-24 — fix(ml): auto-cura de `available_quantity.not_modifiable` no update_item

Follow-up do fix anterior: o erro continuou no anúncio #2923
(`item.available_quantity.not_modifiable`) porque o flag `is_full`/`logistic_type`
local estava desatualizado — o guard proativo não identificou como FULL.

- `ml_service.update_item`: a auto-recuperação (que já tratava `field_not_updatable`)
  passou a tratar também o código `item.available_quantity.not_modifiable` — remove
  `available_quantity` do payload e retenta. Os demais campos (título, preço, atributos,
  fotos) são salvos. **Robusto independente do flag local** (cobre FULL, catálogo e
  variações). Testado com a resposta exata do #2923: 1º PUT 400 → remove estoque →
  2º PUT 200, `_skipped_fields=['available_quantity']`.
- `sync_to_ml_batch`: detecção de skip passou de `"FULL" in s` para
  `"available_quantity" in s` — cobre tanto o strip proativo quanto a auto-cura.
- Frontend: toast ajustado para "estoque gerido pelo ML (FULL/catálogo)".
- Obs.: o `#2927 ConnectTimeout` é erro de rede transitório ao conectar no ML — o
  batch isola o item e segue; basta reexecutar a ação para esse anúncio.
- Verificado: py_compile, mock-test do update_item, npm run build, pytest 25/2.

---

## 2026-06-24 — fix(anuncios): não enviar estoque ao ML em anúncios FULL

Bug: a ação "Enviar Anúncio ao Marketplace" (Gestão de Anúncios) enviava
`available_quantity` para anúncios FULL; o ML rejeita com
`item.available_quantity.not_modifiable` e o PUT inteiro falhava (título/preço/
atributos não eram salvos). Anúncios FULL têm estoque gerido pelo galpão ML —
só o estoque LOCAL muda (coerente com ADR-0010).

- `_listing_is_full(listing)` (novo): FULL = `logistic_type=='fulfillment'` OU
  `is_full` (forma OR, alinhada ao ramo FULL de /sync-stock).
- `_strip_unwritable_stock(ml_payload, listing)` (novo): remove `available_quantity`
  do payload de update p/ FULL e p/ catálogo ML; retorna o motivo do skip. Cobre
  variações (os forms de update não emitem `variations` com estoque).
- `sync_listing_to_ml` e `update_anuncio`: passaram a usar o helper (antes só
  removiam estoque p/ catálogo). Demais campos seguem normalmente.
- `sync-to-ml-batch`: retorna `full_stock_skipped`; o frontend
  (AnunciosView.runBatchAction) mostra `toast.info` avisando que o estoque do FULL
  não foi enviado.
- NÃO tocados (intencional): publish/create (item novo nasce não-FULL e o ML exige
  estoque no POST), reactivate (tratado no ml_service), switch-to-cross-docking
  (envio de estoque intencional após sair do FULL), /sync-stock (já lê do ML p/ FULL).
- Verificado: py_compile ok, unit do helper (FULL via logistic/is_full e catálogo
  removem estoque; cross_docking/vazio mantêm), npm run build ok, pytest
  -m "not integration" 25/2 (baseline). Auditorias quality/consistency/adr sem
  CRITICAL/HIGH; adendo no ADR-0010 (fronteira de escrita do anúncio).

---

## 2026-06-21 — feat(datetime): fonte única de data/hora p/ horário do Brasil (front + back)

Padronização transversal de data/hora (ADR-0013). Problema: telas (Dashboard Marketplace,
Análise de Concorrência) exibiam horário errado — cada componente formatava com
`toLocaleString('pt-BR')` **sem `timeZone`** (renderizava no fuso do navegador) e strings
*naive* eram mal interpretadas; "hoje"/intervalos via `toISOString()` davam off-by-one.

- **Frontend — fonte única** `utils/formatters.js`: reescrita a seção de data/hora com
  `Intl.DateTimeFormat` em `timeZone: 'America/Sao_Paulo'` fixo — `parseDate`, `formatDate`,
  `formatDateTime`, `formatTime`, `brToday`, `brDaysAgo`, `brInputToUtcIso`. Só-data
  (`YYYY-MM-DD`) = dia literal (sem off-by-one); naive = UTC.
- **Backend — fonte única** `services/datetime_br.py` (novo): `now_utc/now_br/ensure_aware/
  to_br/to_utc/iso_utc/parse_marketplace_dt`, `BR_TZ`. `dashboard.py` `generated_at` → UTC.
- **Consolidação** (delegam ao util, removidas duplicatas): `_helpers.js`, InventoryList/Form,
  StockMovementsModal, CmigFiscalConfigCard, ShipmentModal, OrderStatusStepper, UsersView,
  Separation (View/InfoModal/CartsList), Integrations, InvoicesModal, EmailConfig, SaidasView.
- **Bugs de fuso corrigidos** (achados na auditoria): `orders.py` `date_from/date_to` agora
  = dia local BRASIL→UTC (não corta as últimas 3h); `useCampaignAds.isoDate` e `SaidasView`
  mês corrente via fuso do Brasil (não `toISOString`). Dedup de `ZoneInfo` em dashboard/
  sync_marketplace_metrics/ml_fiscal_sync/stock → importam `BR_TZ`.
- **Dívida registrada** (ADR-0013): `datetime.utcnow()` naive em módulos fiscais e reuso de
  `parse_marketplace_dt` — follow-up sem bloqueio (o front já exibe naive como UTC).
- Verificado: `npm run build` ✓, py_compile dos arquivos backend ✓, smoke do `datetime_br` ✓,
  `pytest -m "not integration"` 25/2 (baseline — as 2 falhas são limitação do MockResult em
  orders.py:480, sem relação com a mudança). Auditorias quality/consistency/adr sem CRITICAL/HIGH.

---

## 2026-06-21 — fix(análise): preço promocional + permalink de Ads + card preço cruzado + link vendedor

Ajustes pedidos pelo dono após teste:
- **Preço (#4)**: o coletor pegava o preço RISCADO; agora pega o PRINCIPAL/promocional (`.andes-money-amount:not(--previous)`), no grid e na PDP.
- **Permalink/Ads (#3)**: anúncios patrocinados vinham com tracker `click1.mercadolivre.com.br/mclics/...` → quebrava a visita da página (sem categoria/vendas/reputação/avaliação) e o link. Agora sanitiza p/ a URL canônica do item (`_item_url`) no coletor e na visita; top20 reordenado por vendas REAIS da PDP (deep primeiro).
- **Card preço (#1)**: virou cruzamento **Unidade(KIT/Unitário) × FULL/Outros × Frete(Grátis/Comprador)** com Mín/Médio/Máx/Qtd por combinação (`price_combinations`).
- **Concentração (#2)**: link "ir para a página/loja do vendedor" por vendedor (`top_sellers[].url`).
- Verificado: compile/import, price_combinations/seller/top20 OK, pytest 25/2, build ✓.

---

## 2026-06-21 — feat(análise): deep por VENDAS + KIT/FULL + simulador Clássico×Premium + análise geral

Refatoração do estudo (planejada em plan mode, auditada quality/consistency/adr):
- **Coletor** ([ml_search.py](tools/collector/ml_search.py)): remove "Voltar" do breadcrumb; deep-visit dos **20 MAIS VENDIDOS** (`_approx_sold`, fallback relevância) em vez dos mais relevantes; `page_sold`/`deep_rank_by_sales`. deep_count 30→20.
- **Backend** ([competitor_analysis_service.py](BACKEND/services/competitor_analysis_service.py)): `_clean_category_path` (funde categorias), `_is_kit`, `_price_quartiles`; `_build_search_study` ganha KIT/FULL (contagem + `price_stats.full/kit/non_kit`), `distribution` (quartis), `sweet_spot`, `seller_concentration`, `rating_avg`, `price_vs_sales`, `top20_by_sales`; `_simulate_owner_listing_types` (Clássico×Premium do produto do dono via `ml.get_listing_costs`, no preço que atinge a margem desejada — solver auto-consistente, sem dupla contagem); prompt novo (1 `expert_analysis` GERAL + `listing_type_recommendation`, sem comentário por anúncio); payload com `simulador_dono`.
- **Front** ([CompetitorAnalysisView.vue](FRONTEND/src/views/analysis/CompetitorAnalysisView.vue)): card frete com KIT/rating + linhas FULL/KIT/Sem-KIT; cards Distribuição de preço (quartis+sweet_spot) e Concentração de vendedores; Top 20 c/ link do vendedor; removida coluna comentário; card "Análise do especialista"; tabela Clássico×Premium destacando o recomendado.
- Auditorias: quality-guardian (HIGH dupla-contagem do solver → corrigido), consistency (M1 cards vazios em estudo legado + M2 rótulo "por vendas" → corrigidos), adr (APROVADO + adendo). pytest 25/2, builds ✓. ADR-0012 com adendo.

---

## 2026-06-21 — feat(análise): visita a página de cada anúncio (top 30) + progresso ao vivo

Upgrade do estudo: além do grid, o coletor abre a PÁGINA dos 30 mais relevantes (configurável) p/ dados ricos que a API bloqueada dava. Planejado (plan mode) + auditado (consistency-auditor); decisões do dono: deep=30, seguir sem visitas (impossíveis na página pública).

- **Coletor** ([ml_search.py](tools/collector/ml_search.py)): `_parse_item_page` (breadcrumb→categoria, ficha técnica→marca/modelo/specs, vendas, preço, reputação textual, reviews, frete/FULL), `_read_embedded_state` (date_created/category_id/seller_id do `__PRELOADED_STATE__`/`__NEXT_DATA__`/ld+json), `_visit_item_pages` (loop humanizado, jitter 2.5-6s, para no 1º captcha, resiliente por item), `_write_progress` (atômico). Query Título+Modelo. CLI `--deep-count`/`--progress-file`.
- **API** ([collector_api.py](tools/collector/collector_api.py)): `POST /collect` aceita `deep_count`; job grava `progress_path`; `GET /collect/{job_id}` expõe `progress` ao vivo.
- **Backend** ([competitor_analysis_service.py](BACKEND/services/competitor_analysis_service.py)): `_fetch_scraped_items(deep_count,on_progress)` + `_collect_via_job` repassa progresso a `_set_progress` (status granular); `_build_listings_from_scraped` mapeia categoria/ficha/reputação/`date_created`→velocidade (`_apply_velocity` extraído); `_build_search_study` com categorias REAIS por item + `brand_coverage`/`model_coverage`/`reputation_mix`/`velocity_stats`/`deep_visited_count`. Prompt atualizado (visitas indisponíveis; velocidade quando há data).
- **Front** ([CompetitorAnalysisView.vue](FRONTEND/src/views/analysis/CompetitorAnalysisView.vue)): coluna Categoria + marca/modelo + reputação (quando raspada); progresso granular.
- **Config**: `COLLECTOR_DEEP_COUNT=30`; timeouts 900/960s (cobre ~30 páginas; túnel async evita 524). ADR-0012 adendo.
- Verificação: compile/import ✓, deep mapping testado ✓, pytest 25/2, build ✓. Deploy: backend + coletor local (reiniciado) + dist. **Validação E2E da página real fica pro teste do dono pelo frontend** (seletores PDP podem variar por categoria → degrada p/ None).

---

## 2026-06-21 — feat(análise): categorias reais (barra lateral) + vendedor com link

- **Coletor** ([ml_search.py](tools/collector/ml_search.py)): `_parse_categories` raspa o filtro "Categorias" da barra lateral da busca (categoria/subcategoria + qtd reais — o card de resultado não expõe categoria por item); `seller_url` por anúncio (loja oficial / `_CustId_`). Best-effort: se o ML mudar o layout, cai na categoria sugerida.
- **Backend** ([competitor_analysis_service.py](BACKEND/services/competitor_analysis_service.py)): `_fetch_scraped_items` retorna `(items, categories, err)`; `_build_search_study` usa as categorias raspadas no `top_categories`; `seller_url` no listing/top_by_relevance/all_results_raw.
- **Frontend**: card Top Categorias mostra categorias reais com link + qtd; coluna **Vendedor** (com link) no Top 10.
- Limitações honestas: Visitas/Reputação seguem impossíveis (API /items bloqueada); Vendas só quando o ML mostra "X vendidos" no card; categoria por-anúncio não vem da busca (só o agregado da barra lateral).
- Deploy: backend pull+restart, frontend dist (coluna Vendedor confirmada), coletor via subprocesso. Verificado: import/compile + caminho de categorias.

---

## 2026-06-21 — fix(coletor): coleta assíncrona (job + polling) p/ evitar HTTP 524 do túnel

O túnel Cloudflare (grátis) corta requisições HTTP que passam de ~100s → a coleta de 120 itens (minutos) dava **524** e o estudo falhava. Tornei a coleta **assíncrona**:
- `POST /collect` agora DISPARA o job e responde na hora `{job_id, status:"running"}` (testado: 551ms via túnel). `GET /collect/{job_id}` devolve o status/resultado. TTL de jobs 1h, mantém lock/rate-limit.
- Backend `_collect_via_job`: dispara e faz **polling** (5s) até `COLLECTOR_TIMEOUT` (330s). Retrocompatível com coletor síncrono. Failover multi-máquina preservado.
- Verificação: fluxo async testado 7/7 (POST→job_id→poll→done, auth, 404); deploy backend + restart do coletor local; POST via túnel coletor1.madeingroup.api.br retornou job_id em 551ms (sem 524).
- **Operacional:** atualizar o coletor exige reiniciar a janela "Coletor ML API" (fechar + rodar `iniciar_coletor_completo.bat`); o `ml_search.py` (subprocesso) atualiza sozinho, mas o `collector_api.py` é processo de longa duração.

---

## 2026-06-21 — fix(análise): ML bloqueou /items (403 PolicyAgent) → coletor vira fonte primária

O ML estendeu o bloqueio para `GET /items/{id}` e `/items?ids=` (403 PolicyAgent) em anúncios de terceiros → `fetch_item_details` morria e o estudo dava "falha ao carregar detalhes". Pivot: a busca raspada vira a FONTE PRIMÁRIA; enriquecimento via API desligado por flag. Auditado (consistency-auditor: C1 permalink, C2 top_categories, H1 relabel front, H2 dict padronizado, L2 prompt).

- **config.py**: `ML_COMPETITOR_ENRICHMENT=False` (flag; religar se o ML reabrir).
- **Coletor** ([ml_search.py](tools/collector/ml_search.py)): raspa o MÁXIMO por item — título, preço, preço original, desconto, vendedor, "X vendidos", avaliação/reviews, frete grátis, FULL, thumbnail, permalink real, sponsored.
- **Backend** ([competitor_analysis_service.py](BACKEND/services/competitor_analysis_service.py)): `_fetch_scraped_items` (itens completos), `_build_listings_from_scraped` (dict padronizado, nulls explícitos), `_build_search_study` (agregados compartilhados), `_parse_sold` ("X vendidos"/"mil"→int), `_enrich_via_api` (overlay dormente atrás do flag). `_gather_ml` reescrito: raspado→listings→(enrich opcional)→estudo. Catálogo/highlights removidos (só davam IDs p/ a API morta). `enrichment_off` no `ml_data`.
- **_SYSTEM_PROMPT**: dados da página de busca; sem visitas/data/reputação; previsão baixa confiança; não inventar métricas.
- **Frontend** ([CompetitorAnalysisView.vue](FRONTEND/src/views/analysis/CompetitorAnalysisView.vue)): rótulo "por vendas"→"por relevância" quando `enrichment_off`; oculta colunas Visitas/Reputação; mostra vendedor, preço original, avaliação; aviso explicativo.
- Verificação: import backend ✓ (_parse_sold 50/2500/1000; build helpers OK), py_compile coletor ✓, npm build ✓. ADR-0012 com adendo.

---

## 2026-06-21 — chore: túnel fixo do coletor + frontend (scraped_count) deployado + runbook 2ª máquina

- **Túnel fixo Cloudflare**: domínio `madeingroup.api.br` (Registro.br → NS Cloudflare). Named tunnel `coletor-ml-1` → `https://coletor1.madeingroup.api.br` → localhost:8777. `.env` do servidor Oracle atualizado para a URL fixa; backend reiniciado (PM2). Launcher `iniciar_coletor_completo.bat` + atalho no Inicializar do Windows. cloudflared.exe gitignored.
- **Frontend deployado**: build local com a mudança cosmética (`scraped_count` no header da Análise de Concorrência) → `dist` enviado por scp para `/home/ubuntu/app/FRONTEND/dist` (backup do antigo no servidor). Confirmado: texto "relevância" no bundle, site 200. Resolve a pendência cosmética.
- **Runbook 2ª máquina (failover)**: `tools/collector/SETUP_MAQUINA2.md` — passo a passo para configurar `coletor-ml-2`/`coletor2.madeingroup.api.br` e ligar `COLLECTOR_API_URL=https://coletor1...,https://coletor2...` no servidor.
- Pendente: dono configurar a 2ª máquina; reiniciar o PC 1 p/ validar auto-start.

---

## 2026-06-20 — feat(full): Análise de Concorrência busca 120 por relevância (coletor pagina) — commit c448016, backend deployado no Oracle (2026-06-20)

Fatoração da 3ª fonte (coletor Camoufox) p/ trazer os **120 primeiros por relevância** (antes ~50). Auditado por consistency-auditor (incorporados C1/C2, H1, H3, M1, M2, M3, L2).

- **Coletor** ([ml_search.py](tools/collector/ml_search.py)): troquei "scroll 3x de 1 página" por **paginação** (clica "Seguinte" → fallback URL `_Desde_N`), ordem de relevância (default ML, sem `_OrderId_`), `search_rank` (1..N) por item, dedup entre páginas, **captcha checado por página** (para no 1º).
- **Limites** ([config.py](tools/collector/config.py) + [BACKEND/config.py](BACKEND/config.py)): coletor DEFAULT_LIMIT 50→120, MAX_LIMIT 100→150, SUBPROCESS_TIMEOUT 180→300; backend COLLECTOR_LIMIT 50→120, COLLECTOR_TIMEOUT 120→330 (cadeia 330>300>navegação). Espelhado no `.env.example`.
- **Backend** ([competitor_analysis_service.py](BACKEND/services/competitor_analysis_service.py)): `_fetch_scraped_ids` retorna `(ids, rank_map, err)` — rank propagado por **mapa item_id→rank** (multiget não preserva ordem); `_gather_ml` aplica `it["search_rank"]` e monta `search_study.top_by_relevance`; novo `_study_for_ai` enxuga o payload da IA (top_by_relevance[:25] + agregados + top10; os 120 crus só no result_json). Corrigido comentário "180".
- **Memorando** ([_SYSTEM_PROMPT]): descreve **3 fontes** (catálogo / busca relevância 120 / highlights); IA usa os por relevância como amostra de mercado (keywords/preço/intensidade), comenta individualmente só o top10. Adendo na [ADR-0012](DOCs/decisions/ADR-0012-coletor-ml-local-camoufox.md).
- **Front** ([CompetitorAnalysisView.vue](FRONTEND/src/views/analysis/CompetitorAnalysisView.vue)): header mostra `scraped_count` (relevância) além de catálogo/categoria.
- Verificação: py_compile coletor ✓, import backend ✓, pytest 25/2 (baseline) ✓, npm build ✓.
- **Nota (auditor H1)**: `fetch_item_details` (ml_service) mantém fallback individual `Semaphore(8)`/`missing[:80]` — não alterado; monitorar 429 com 120 itens (erro é gracioso). Falta validar a coleta real de 120 no IP do operador.

---

## 2026-06-20 — feat(full): coletor ML local (Camoufox) + 3ª fonte da Análise de Concorrência (ADR-0012) — commit c448016, backend deployado no Oracle (2026-06-20)

A busca livre por texto do ML virou 403 (descontinuada) → a Análise de Concorrência só via catálogo + highlights. Instalado o kit Camoufox (anti-detect Firefox via Playwright) e criado um coletor que raspa a busca pública do ML **localmente** (máquina do operador, IP residencial) — **nunca no servidor Oracle** (VM Micro 1GB não roda Firefox; IP de datacenter é flagrado pelo Akamai; decisão do dono).

- **Kit Camoufox**: 11 módulos em `plugins_src/_shared/` + `scripts/fingerprint_check.py` + `requirements-camoufox.txt`. venv dedicada `.venv-camoufox` (Python 3.11), camoufox 0.4.11 / browser v135.0.1. 11/11 módulos importam.
- **Módulo local `tools/collector/`** (roda na venv-camoufox): `collector_api.py` (FastAPI: `POST /collect` auth Bearer via hmac.compare_digest + rate limit + 429 se ocupado; `GET /health`), `ml_search.py` (núcleo de scraping anônimo, sem login), `config.py` (lê `tools/collector/.env`), `.env.example`, README. Smoke test de API: 9/9 OK.
- **Backend (Oracle) consome via HTTP** como 3ª fonte: `config.py` ganhou COLLECTOR_API_URL/TOKEN/ENABLED(default False)/TIMEOUT/LIMIT. `competitor_analysis_service.py`: `_fetch_scraped_ids` (httpx, revalida item_id `^MLB\d{6,}$`, degradação graciosa), `_gather_ml` funde os ids e marca `source="search_scraped"`.
- **Reachability**: máquina local atrás de NAT → expor a API por túnel (Cloudflare/ngrok); URL pública vai em COLLECTOR_API_URL do backend. Túnel carrega só controle; Camoufox sai pelo IP residencial.
- Auditorias: quality-guardian (corrigidos 2 CRITICAL + 2 HIGH: host 127.0.0.1, hmac compare, rate limit, revalidação de id), consistency-auditor (plano), adr-consistency-checker (APROVADO). pytest baseline 25/2 (2 falhas pré-existentes). ADR-0012 criada.
- **Pendente**: produção 24/7 (provável worker x86 + proxy residencial) — em aberto. Rodar `fingerprint_check.py` headful e testar coleta real no IP do operador.

---

## 2026-06-18 — feat(full): espelho CMIG protegido + lista mostra zerados e identifica a CMIG (commit 48579c7) — deployado

Os CMIGProdutos espelho (auto-criados só p/ segurar o FULL) podiam ser "excluídos" — na prática `delete_cmig_product` os DESATIVAVA (is_active=False) quando o PG tinha vendas — sumindo das listas e deixando o FULL órfão ("parecem excluídos e não podem ser excluídos"). E produtos zerados sumiam da lista.

- `cmig_products.is_full_mirror` (migration 101): marca os espelhos (assinatura pg_product_id + source_listing_id NULL + sku_cmig=pg.sku). `resolve_full_cmig_product` seta na auto-criação. **37 espelhos marcados** em prod.
- `delete_cmig_product`: bloqueia exclusão/desativação de espelho (HTTP 400 — segura o FULL; gerenciar pelo PG).
- `/stock/summary`: param `show_zeroed` + `cmig_name`/`is_full_mirror` nas linhas. PG e CMIG seguem em linhas separadas (vários CMIGs podem ter o mesmo produto no FULL).
- `StockControlView`: botão "Mostrar zerados" + identifica a CMIG em cada linha CMIG (badge "FULL" no espelho).

Decisões do dono: manter PG (local, mesmo zerado) e CMIG (full); linhas separadas; toggle p/ zerados; identificar a CMIG. Verificação: pytest 25/2 (pré-existentes), build OK, deploy OK (backend lê is_full_mirror sem ORA-00904), 0 espelhos desativados a reparar.

## 2026-06-18 — fix(full): vendas FULL não baixavam o estoque (commit f98bf20) — deployado

Bug: vendas FULL reservavam (`full_reserve`) mas nunca baixavam o `qty` (`full_out`). O `shipment_status` virava shipped/delivered via `_refresh_shipments` (sync de pedidos), que NÃO chamava `confirm_dispatch` — só o webhook chamava, no seu próprio caminho. Detectado no SKU 5276 (CMIG#3): qty 146 / reserved 124, zero `full_out`.

- `full_stock_service.reconcile_full_dispatched()`: pedidos FULL shipped/delivered sem `full_out` → `apply_full_order_shipped` (idempotente). Backfill + rede de segurança.
- `tasks/sync_orders` chama `reconcile_full_dispatched` após `_refresh_shipments`.
- `_refresh_shipments` dispara `confirm_dispatch` quando pedido FULL fica shipped/delivered (cobre o botão manual de refresh também).

**Backfill aplicado em produção:** 94 pedidos processados, 88 `full_out` criados, 207 un. SKU 5276 corrigido (qty 146→24, reserved 124→2). **6 pedidos pendentes** por terem item **SKU 5253 ("Faixa Elástica Azul-claro") não cadastrado** no catálogo (PG/CMIG) — após cadastrar o produto, a reconciliação do sync baixa automaticamente.

## 2026-06-18 — feat(full): estoque FULL sempre por produto CMIG (ADR-0010) — local, não enviado

Reformulação do controle de estoque FULL. Antes a remessa creditava o FULL na chave do produto **PG** e a venda reservava na chave **CMIG** → "Reserva FULL sem entrada" e FULL não isolável por CMIG (27 linhas pg / 3 cmig em produção; 18 produtos sem CMIGProduct).

Regra (dono): FULL é sempre do CMIG; não existe FULL para PG. `qty` = remessas REAIS − vendas enviadas − retornos REAIS; venda reserva/baixa no envio (atual); simbólicas não movem (ADR-0009). Sync do ML = conferência.

- `services/full_stock_service.py`: novo `resolve_full_cmig_product()` (cmig_product_id → listing → pg_product_id → EAN/SKU → **auto-cria** CMIGProduct espelho do PG, idempotente) + `_cmig_id_for_account()`. `apply_nfe_saida_to_full`/`apply_nfe_entrada_from_full`/`resolve_full_product` passam a resolver SEMPRE CMIG (nunca grava 'pg'). `available_to_push` resolve o espelho p/ anúncio só-PG.
- `services/stock_view.py`: `load_full_per_account_map` segue `pg_product_id` → card do PG mostra o FULL do CMIG espelho.
- `routers/stock.py`: `/cmig/{id}/sync-full` virou **conferência** (compara sistema × ML, reporta `drift`, dispara re-sync de NF-e em background; não sobrescreve). Novo `POST /stock/migrate-full-pg-to-cmig?dry_run=` (migração idempotente das linhas pg→cmig, auto-cria espelhos, agrega por (cmig,conta) preservando reserved, movimento `full_migrate`).
- `routers/invoices.py`: detecção de furos de sequência de NF-e agora **cross-mês** (une lote + persistidos por série/CMIG).
- Frontend `StockControlView.vue`: botão "Atualizar Estoque FULL" mostra conferência/drift.
- `DOCs/decisions/ADR-0010-full-sempre-cmig.md` + `Scripts SQL/100_full_cmig.sql` (âncora).

**Ajuste pós-deploy (commit 4430e1b):** o FULL estava aparecendo na linha PG E na CMIG do mesmo produto (duplicação visual). `load_full_per_account_map` ganhou `follow_pg_link`; a lista de Controle de Estoque usa `follow_pg_link=False` (FULL só na linha CMIG); o card de anúncio segue o link. Deployado.

Verificação: import OK; pytest 25 passed / 2 falhas pré-existentes (test_orders); `npm run build` OK. Auditoria de fechamento (quality+consistency+adr): 3 HIGH corrigidos (uq_cmigprod_sku no re-SELECT; índice único `uix_cmigprod_cmig_pg` p/ concorrência; `stock_summary` reusa `load_full_per_account_map` p/ paridade). **Deployado** (commit 6c1bc96). **Migração aplicada em produção:** 27 linhas pg→cmig (18 espelhos auto-criados, 25 convertidas, 2 mescladas), reservas (125) preservadas; full_stock final = 28 linhas cmig / 1099 un, zero linhas pg. Índice único criado.

---

## 2026-06-17 — fix(fiscal): NF-e "Retorno Simbólico" não movimenta estoque (LOCAL nem FULL) + reparo de dados

Bug: o sync fiscal movimentava estoque com base em NF-e de **Retorno Simbólico de Depósito** (CFOP 1949). Após a remessa 706 (inv #185) creditar o FULL corretamente (+569 em 12 produtos PG, conta 2/EBAZAR), 37 notas "Retorno Simbólico" debitaram o FULL de volta a ~0 (e inflaram o LOCAL via `nfe_in`). Regra confirmada pelo dono: **só remessa e retorno REAL movimentam estoque; simbólico é fiscal puro**.

Diagnóstico (read-only em produção, autorizado): a 706 estava correta; o estorno veio das simbólicas. CFOP não discrimina (1949 aparece em simbólico E em retorno real), então a fonte é a `natureza_operacao`.

Correção de código (guard centralizado):
- Novo `services/fiscal/fiscal_rules.py::is_simbolica(natureza)` (NFKD + lower + substring "simbolic").
- Guard nas funções de baixo nível (cobre todos os call-sites): `_apply_stock_movement` (invoices.py), `apply_nfe_saida_to_full`/`apply_nfe_entrada_from_full` (full_stock_service.py), `update_stock_from_invoice` (dfe_service.py); import-xml entrada com `not _is_simbolica`.
- `POST /stock/recompute-all` (stock.py): o UPDATE em massa de `stock_updated=True` passou a **excluir** notas `purpose='devolucao'` (Fase B) e simbólicas — senão as ressuscitaria (dupla contagem).

Reparo de dados (produção, autorizado, idempotente — `sandbox/repair_simbolicas.py`): re-creditado FULL +569 nos 12 produtos (conta 2), removidos os 110 movimentos `full_return_out` errôneos, 37 notas simbólicas → `stock_updated=False` + recompute LOCAL. O #177 (retorno REAL) foi corretamente preservado. FULL da remessa 706 restaurado (169/171=100, 170=90, 172=60, 173=61, etc.).

Auditoria: quality-guardian (2 CRITICAL iniciais — finalize movia LOCAL, import-xml entrada sem guard — corrigidos) + consistency-auditor (achou e corrigimos o HIGH do recompute-all). Veredito final: LIBERADO. pytest 25/2 (pré-existentes).

---

## 2026-06-17 — feat(returns): Devolução NF-e-driven (Fase B) — import XML + inspeção apto/não-apto + descarte (local, não enviado)

Devolução agora pode ser dirigida por NF-e. Fluxo: operador importa o XML da NF-e de devolução → casa o pedido original pela NF-e referenciada (`refNFe → Order.nfe_key`, fallback SKU/EAN) → devolução entra em inspeção (`pending_validation_quantity` pela QTD da NF-e, suporta parcial) → operador marca apto (volta a `stock_quantity`) ou não-apto (`unfit_quantity` + nota de descarte sem SEFAFZ).

Backend:
- `models/return_.py`: colunas `devolution_invoice_id`, `discard_invoice_id`, `referenced_access_key` (migration `110_returns_nfe.sql`, idempotente — **ainda não aplicada ao ATP**).
- `services/fiscal/nfe_xml_parser.py`: parse de `referenced_keys` (refNFe, 44 díg.) e `sku` (cProd).
- `services/stock_reservation_service.py`: `receive_return_items` (pending+, idempotente) e `validate_return_items` (apto: pending−/stock+; não-apto: pending−/unfit+; não commita — router orquestra).
- `routers/returns.py`: `POST /returns/import-xml` (Form cmig_id + File, `_check_cmig_access`, valida CNPJ↔CMIG, limite 5 MB/MIME); `_ingest_devolution`; `_create_discard_note`; `validate_return_endpoint` ramifica em `devolution_invoice_id` (escopo via `_check_cmig_access`); `_serialize` expandido.

Frontend: `components/returns/DevolutionXmlImportModal.vue` (novo), `ReturnListView.vue` (botão importar + badge NF-e), `ReturnValidationView.vue` (card da NF-e com itens/chave referenciada).

Decisão-chave (ADR-0009): NF-e de devolução e nota de descarte são **fiscal-only** (`stock_updated=False`) → inertes ao recompute event-sourced; os contadores UPDATE-direto (pending/apto/unfit) são a fonte canônica. Evita dupla contagem e preserva o portão de inspeção.

Auditoria de fechamento (quality-guardian + consistency-auditor + adr-consistency-checker):
- **CRÍTICO (ADR) corrigido**: premissa invertida — `stock_updated=True` é condição de INCLUSÃO no recompute. Devolução apta seria contada em dobro (nfe_in + UPDATE direto). Fix: `stock_updated=False` na NF-e de devolução e na nota de descarte.
- **HIGH (consistency) corrigido**: faltava validar CNPJ↔CMIG no import (paridade com import-xml-saida). Fix: validação + `_check_cmig_access`.
- **HIGH (quality) — caminho NF-e corrigido**: escopo por galpão na validação NF-e (`_check_cmig_access(inv.cmig_id)`). Gap **pré-existente** nos endpoints legados (`/pending-validation`, `GET /{id}`, `PUT /{id}/status`) permanece — registrado na ADR-0009 como pendência.
- MEDIUM/LOW: try/except+rollback+log no ingest; removido commit redundante no caminho legado; docstring "não commita".
- Gap conhecido (sem bloqueio): falta sync ML só-devoluções (entrada hoje é só upload de XML).

Verificação: AST+import OK; `npm run build` OK; pytest 25 passed / 2 falhas pré-existentes (test_orders, mock `.scalar`). **Falta aplicar a migration 110 ao Oracle ATP** (afeta dev+prod) e validar o fluxo ponta-a-ponta pela UI — ambos pendentes de autorização do usuário.

## 2026-06-17 — ops: reativação de anúncios pausados por falta de LOCAL com estoque no FULL

Operação one-off (conta 2): identificados 11 anúncios não-FULL com último push 0 (pausados por falta de LOCAL) e FULL>0. Confirmado status no ML e reativados via `reactivate_item` com a qtd do FULL. Resultado: 7 reativados, 3 já ativos, 1 erro transitório do ML (MLB4702333349 — kvsclient; será reativado no próximo sync_stock). Não houve mudança de código.

## 2026-06-17 — Auditoria de fechamento do lote fiscal/estoque + correções

Rodada quality-guardian + consistency-auditor + adr-consistency-checker. Achados HIGH corrigidos antes do deploy:
- Overselling: `available_to_push` (full_stock_service) — fallback p/ FULL quando LOCAL=0 só ocorre se NÃO houver anúncio `is_full` ativo do mesmo produto+conta (evita anunciar o saldo FULL 2x).
- Unificação: `_compute_product_stock` (sync_stock) e `_read_stock` (stock_sync_service) agora delegam a `available_to_push` (LOCAL = stock − reserved nos dois; elimina a divergência de reserved_quantity).
- Gating: `import_xml` (entrada) passou a exigir `require_menu_permission("fiscal_entradas")` (paridade com saída).
- `sync_ml_fiscal` retém referência do task de background (`_BG_TASKS`) — evita coleta pelo GC.
- ADR-0008 criado: documenta o batch mensal de NF-e e a exceção ao ADR-0004 (anúncio não-FULL anuncia FULL quando LOCAL=0).
Veredito final: LIBERADO (sem CRITICAL/HIGH). pytest 25/2 (pré-existentes).

## 2026-06-17 — fix(stock): não pausar anúncio com LOCAL=0 mas FULL>0 (local, não enviado)

Após remessa LOCAL→FULL, anúncios não-FULL ficavam com LOCAL=0; o push de estoque enviava 0 ao ML e o ML pausava — ignorando o FULL. Regra correta: só pausar quando LOCAL E FULL estão ambos zerados.
- `services/full_stock_service.available_for_product(db, account_id, cmig_product_id, catalog_product_id)`: disponível no FULL (qty-reserved) do produto na conta (soma cmig+pg).
- `tasks/sync_stock._compute_product_stock` e `services/stock_sync_service._read_stock`: quando o disponível LOCAL é 0, retornam o disponível do FULL em vez de 0 — assim o anúncio NÃO é pausado; só vai a 0 (pausa) quando LOCAL e FULL = 0. Anúncios já pausados reativam no próximo sync_stock (qty>0).
- Caveat: o anúncio não-FULL passa a anunciar a qtd do FULL quando o LOCAL zera (atende ao pedido do usuário). Se houver um anúncio FULL separado p/ o mesmo produto+conta, há risco de anunciar a mesma unidade 2x — avaliar com dados reais.
- Verificação: edições revisadas (ProductListing.account_id confirmado); import/pytest PENDENTE (classificador de Bash indisponível no momento).

## 2026-06-17 — feat(fiscal): sincronizar todas as NF-e do mês (remessa FULL) — Fase A (local, não enviado)

A "Sincronizar NF-e do ML" da tela Saídas era dirigida por pedido → notas de REMESSA para o FULL (sem pedido) não vinham → furo na sequência. Avaliação prévia do consistency-auditor aplicada (mapa tipo→estoque corrigido p/ não dar dupla contagem). Faseado: Fase A = Saídas (remessa/retorno FULL); Fase B (futura) = módulo de Devoluções NF-e-driven.

- `ml_service.download_invoices_batch(token, seller_id, start, end)`: baixa o lote do Faturador (`batch_request/period/stream`, sale/return/full/others=all) e devolve os XMLs do mês. (Testado ao vivo: pegou 97 XMLs de maio/conta 2.)
- `routers/invoices.py`: novo `POST /outbound/sync-ml-fiscal?period=AAAAMM&cmig_id` — dispara, em background e SEQUENCIAL por conta (batch é sensível a 429), `_sync_ml_fiscal_account`. HTTP do zip FORA da sessão de BD; 1 tx curta por nota. Classifica nota como FULL via `is_full_cnpj` (dest/emit) e direção pela CFOP (1/2/3=retorno → LOCAL↑+FULL↓; 5/6/7=remessa → LOCAL↓+FULL↑). Não-FULL é PULADO (venda já vem do cache de pedido; devolução = Fase B). Dedup da lista `/outbound` por chave de acesso.
- Frontend: `SaidasView` com seletor de mês + botão "Sincronizar todas (mês)" (store `syncMlFiscal`).
- Verificação: backend importa OK; `npm run build` OK; `pytest` 25/2 (pré-existentes).
- ⚠️ Achados ao vivo (PENDENTE validar via UI): o batch do ML é instável sob carga (retornou 500 em junho e 429 após chamadas repetidas) — o código trata (retorna vazio/retry); ~32 docs/mês são CT-e/eventos (não-NFe) e são pulados; a classificação remessa/retorno por CFOP precisa ser confirmada com notas reais (validação end-to-end bloqueada pelo 429 nos testes).
- Rotina diária: `tasks/ml_fiscal_sync.sync_ml_fiscal_current_month` (scheduler `sync_ml_fiscal`, CronTrigger 06:00 UTC ≈ 03:00 BRT) — sincroniza o MÊS ATUAL (BRT) de todas as contas ML ativas, sequencial por conta; idempotente (dedup por chave) → se errar um dia, corrige no outro.
- Detecção de FUROS de sequência: `_sync_ml_fiscal_account` coleta os números de NF-e por série do lote e calcula os faltantes em [min,max]; loga os furos (WARNING) e devolve `gaps` no resultado — para serem buscados numa próxima sincronização. Classificação de direção por CFOP (1/2/3=entrada→retorno; 5/6/7=saída→remessa).

## 2026-06-17 — feat(fiscal): ordenação das listas de Saídas e Entradas (local, não enviado)

Cabeçalhos clicáveis (asc/desc) por CMIG, Nº/Série, Tipo e Emissão.
- `routers/invoices.py`: `list_invoices` (Entradas) ganhou `sort_by`/`sort_dir` (cmig→cmig_id, numero→nfe_number, tipo→inbound_source, emissao→issue_date; order_by com nullslast + created_at desc de desempate). `list_outbound_invoices` (Saídas) ordena a lista mesclada (fiscal+ML) em memória antes de paginar (cmig→cmig_name, numero→nfe_number, tipo→nfe_type_label, emissao→issue_date).
- Frontend: `SaidasView.vue` (CMIG, Nº/Série, Tipo, Emissão) e `EntradasView.vue` (Nº/Número, Emissão, Origem=Tipo) com `setSort`/`sortIcon` e ícones fa-sort. Em Entradas não há coluna CMIG (é filtro), então a ordenação por CMIG fica só em Saídas.
- Verificação: backend importa OK; `npm run build` OK.

## 2026-06-17 — feat(fiscal): importar XML de Saída + remessa para o FULL (local, não enviado)

FISCAL > Saídas ganhou "Importar XML de Saída". Quando o destinatário é um CNPJ FULL cadastrado, é remessa: baixa LOCAL + crédito FULL. Avaliação prévia do consistency-auditor aplicada (3 HIGH incorporados). Sem migration — reusa toda a máquina FULL existente.

- `services/fiscal/nfe_xml_parser.py`: passa a extrair `sku` (cProd) do item.
- `routers/invoices.py`: novo `POST /invoices/import-xml-saida` (gating fiscal_saidas): valida EMITENTE==CMIG, dedupe access_key (409), upsert destinatário (`_upsert_recipient`, is_customer), cria Invoice direction=out status=authorized (inbound_source='xml_upload' — valor aceito pelo CHECK chk_inv_inbound_source; a saída distingue-se por direction='out'); itens criados via `_invoice_item_from_parsed` e CASADOS via `_resolve_item_match` (seta source_type+FK — necessário p/ baixa LOCAL e crédito FULL). Baixa LOCAL via `_apply_stock_movement` (event-sourced nfe_out); se `is_full_cnpj(destinatário)`, credita FULL via `apply_nfe_saida_to_full`. Retorna casados/não-casados + is_full_remessa. (+logger no módulo).
- Frontend: `XmlImportModal.vue` parametrizado por `direction` (in/out); `SaidasView.vue` com botão "Importar XML de Saída" + resultado (remessa FULL, casados/sem-match).
- Já existente (verificado, sem código): venda FULL→baixa FULL; FLEX/AGÊNCIA→baixa LOCAL (`reserve_stock` por shipping_mode, ADR-0004).
- Decisões do usuário: match só por SKU/EAN (sem variantes); nenhum XML de envio ao FULL é emitido pelo sistema (todos vêm do marketplace e são importados).
- Verificação: backend importa OK (rota registrada); `npm run build` OK; `pytest -m "not integration"` 25/2 (pré-existentes). Teste end-to-end requer um XML real de remessa.
- Fixes pós-teste com XML real: (a) `inbound_source='xml_upload'` (CHECK chk_inv_inbound_source não aceitava 'xml_upload_out'); (b) `full_stock_service._adjust_full_stock` faz `flush` após criar linha — XML com o mesmo produto em vários itens não gera 2 INSERT (ORA-00001 UIX_FULL_STOCK_PRODUCT); (c) `_already_has_full_movement` usa `.first()` (NF-e multi-item tem vários `full_in` → `scalar_one_or_none` quebrava); (d) `import_xml_saida` agora é atômico (um commit após LOCAL+FULL, rollback em falha — antes commitava LOCAL antes do FULL, deixando NF-e meio-aplicada). Recuperação: creditado FULL nas 3 saídas já importadas (#182/#183 ok, #184 com 13 itens).

## 2026-06-16 — fix(atendimento): timezone no sync de claims (offset-naive vs aware)

O sync de reclamações falhava a cada 15 min em claims cujo `last_message_at` (lido do Oracle, naive) era comparado com a data da mensagem do ML (aware) — `can't compare offset-naive and offset-aware datetimes` (ex.: claim 5527113570). Correção em `tasks/claims_sync.py`: `_parse_dt` retorna sempre tz-aware (assume UTC se sem offset) e novo helper `_aware()` normaliza o valor vindo do banco antes da comparação. Verificado: sync conta 2 sem erro (28 claims), claim 5527113570 atualizado.

## 2026-06-16 — feat(atendimento): anúncio (foto + link) e comprador na lista de Mensagens (local, não enviado)

A lista de conversas (aba Mensagens) não mostrava o anúncio nem o comprador. Avaliação prévia do consistency-auditor aplicada (sem HTTP na sessão de BD; helper compartilhado; placeholder + link condicional).

- `services/ml_items.py` (novo, neutro): `get_item_meta` (foto/permalink/título) e `get_user_nickname`. `claims_service.get_item_thumbnail` agora delega a ele (sem duplicação).
- `conversation_threads`: colunas `item_thumbnail`, `item_permalink` (migration `109`). `item_id`/`item_title` já existiam.
- `messages_sync._upsert_post_sale_thread`: enriquece via Order/OrderItem (título/foto/`item_id`) e usa `order.buyer_name` como fallback do comprador — tudo do BD, sem HTTP.
- `messages_sync._backfill_thread_items`: preenche foto/permalink/título (item ML) e nickname do comprador — HTTP FORA da sessão de BD, 1 tx curta por thread; cobre pós-venda E perguntas.
- `routers/messages.py _serialize_thread`: + `item_thumbnail`, `item_permalink`.
- `MessagesView.vue`: item da lista com foto (placeholder se ausente) + comprador + título do anúncio com link (`target=_blank`, só quando há permalink).
- Verificação ao vivo: sync conta 2 → thread com comprador (MARIANIUDACOSTA), título (Step Ajustável…), foto e permalink preenchidos. `pytest -m "not integration"` 25/2 (pré-existentes); `npm run build` OK. Migration 109 aplicada na ATP compartilhada.

## 2026-06-14 — feat(atendimento): apresentação da lista de reclamações + Histórico de Ações em PT-BR (local, não enviado)

Igualando à referência (Mercado Turbo):
- Lista de reclamações: **foto de capa do anúncio** (coluna `thumbnail` na tabela claims — migration `108_claims_thumbnail.sql`), **Tipo** ("Reclamação Comprador/Vendedor"), **Estágio**, **Status** (Aberto/Fechado, colorido) e **Última Interação**. Placeholder quando sem foto.
- Foto buscada do `OrderItem` interno e, quando ausente, **do item no ML** (`get_item_thumbnail`; e `get_order_item_id` quando não há pedido casado). 3/4 abertas resolveram; resto cai no placeholder.
- **Histórico de Ações 100% em PT-BR**: `ACTION_NAME_PT` cobre todos os action_names vistos (send_message_to_*, generate_return*, refund, allow_partial_refund, return_review*, create_new_resolution, disallow_return, set_culpability, change_typification, open_none, etc.); papéis traduzidos (`ROLE_PT`: Vendedor/Comprador/Mediador) e status (Aberto/Fechado). Rótulo recalculado no serializer (corrige registros antigos sem re-sync). Card do histórico mostra Ação/Quem/Estágio/Status/Data.
- Verificação ao vivo: re-sync das contas OK; "não mapeados: nenhum"; opened com thumbnail 3/4; `npm run build` OK.

## 2026-06-14 — fix(atendimento): sync de reclamações não cobria todas as contas (DPY-4011) (local, não enviado)

Sintoma: reclamações "não eram encontradas" — só a conta sincronizada manualmente tinha dados (parciais).
Causa raiz: `claims_sync` mantinha UMA sessão Oracle aberta durante dezenas de chamadas HTTP ao ML (lentas) → o ATP derrubava a conexão ociosa (`DPY-4011 / WinError 10054`) → rollback do lote inteiro. Além disso, enriquecia TODAS as reclamações (incl. fechadas), ~4 chamadas cada, tornando o job lento demais p/ cobrir as contas.
Correção: HTTP feito FORA do banco; **uma transação curta por claim**; enriquecimento (detalhe/reputação/mensagens/histórico) só para **abertas** (fechadas = resumo); `asyncio.gather` nas 4 leituras da aberta; dedupe de mensagens por hash com 1 query. Frontend: "Sincronizar" sem conta selecionada agora cobre **todas as contas acessíveis**.
Verificação ao vivo: sync de 5 contas sem erro (7–30s cada), 113 claims gravados; ML MIG com 3 abertas (= o esperado), LPS com 1. Conta CA FITNESS precisa reconectar (invalid_grant).

## 2026-06-14 — feat(atendimento): Reclamações sub-fase 3 — Mensagens Prontas + modais dedicados (local, não enviado)

- Templates "Mensagens Prontas" (§2.8): tabela `message_templates` (já na migration 107), `routers/message_templates.py` (CRUD escopado por usuário/CMIG, com `get_accessible_cmig_ids` novo em atendimento_access), `composables/useMessageTemplates.js`, `components/atendimento/TemplatesModal.vue` (gerenciar + usar). Botão de Mensagens Prontas no compositor das DUAS abas (Mensagens e Reclamações).
- Modais dedicados das ações de reclamação (§3.5), substituindo prompt/confirm/alert: Reembolso Parcial (valor), Revisar Devolução (Tudo Certo / Há um Problema + nota), Código de Rastreio, confirmação genérica (reembolso total/mediação/etiqueta), Detalhes da Devolução, Resolução Esperada — em ClaimsTab.
- Verificação: backend importa OK (4 rotas templates); `npm run build` OK; `pytest -m "not integration"` = 25 passed, 2 failed (pré-existentes).
- NÃO incluído (precisa de integração externa / definição): Cálculo de Frete dos Correios (API/credenciais Correios), Carrinho do Comprador e Informações da Entrega standalone na aba Mensagens, e Código de Rastreio standalone do pós-venda. Reportado ao usuário.

> **Local apenas.** Não enviado a GitHub/servidor.

## 2026-06-14 — feat(atendimento): Reclamações (claims ML) por conta CMIG — sub-fases 1+2 (local, não enviado)

Atendimento agora atende mensagens E reclamações pós-venda do ML, persistindo tudo no BD. Avaliação prévia do consistency-auditor aplicada (auth via get_accessible_account_ids — não require_menu_permission; checagem por-recurso; auditoria triggered_by_user_id; idempotência de refund; webhook em background). Ver ADR-0007.

- DB: migration `107_claims.sql` (idempotente) + `models/claim.py`: `claims`, `claim_messages` (2 canais comprador/mediador), `claim_actions` (histórico + auditoria local), `message_templates`.
- `services/claims_service.py`: leituras tolerantes (search/detail/actions-history/affects-reputation/messages/returns) + escritas (send_message, execute_claim_action) + mapas PT (stage/reason/action/reputation).
- `services/atendimento_access.py`: helper de escopo extraído e compartilhado entre messages e claims (refatorado messages.py p/ usá-lo).
- `tasks/claims_sync.py`: `sync_all_claims` (scheduler 15min) + `sync_account_claims` (on-demand/webhook); upsert claims/mensagens(hash)/ações; enriquecimento best-effort via Order. Webhook tópico `claims` em webhooks.py.
- `routers/claims.py` (prefix /api/v1/claims): stats, list, detail (2 canais + histórico), sync, returns, POST messages (responder), POST actions/{action} (dispatcher: refund/partial-refund/open-dispute/return-review/allow-return/send-tracking — valida available_actions, bloqueia refund duplicado, audita user_id). Registrado em main.py.
- Frontend: `MessagesView` vira abas (Mensagens | Reclamações c/ badge). `components/atendimento/ClaimsTab.vue` (3 colunas: lista+filtro / detalhe c/ header+IDs copiáveis+badge reputação+ações+2 canais+resposta 350ch / histórico). `composables/useClaims.js`.
- ADR-0007 (claim ML vs Return físico).
- Verificação: backend importa OK (7 rotas claims, models registrados); messages/webhooks refatorados OK; `pytest -m "not integration"` = 25 passed, 2 failed (pré-existentes); `npm run build` OK.
- PENDENTE: sub-fase 3 (auxiliares de mensagem: templates "Mensagens Prontas" CRUD, código de rastreio, cálculo de frete, carrinho, info de entrega) + modais dedicados (hoje refund/partial/return-review usam confirm/prompt). Rodar migration 107 no Oracle. Confirmar ao vivo paths dos POSTs de ação e tópico de webhook `claims`.

> **Local apenas.** Não enviado a GitHub/servidor.

## 2026-06-14 — chore(media): desabilitar geração de clips por IA (kill switch)

A geração de clips por IA (Veo) foi desligada a pedido. Visualização/exclusão dos clips já gerados continua ativa.

- `routers/media.py`: `POST /generate-clip` levanta 403 imediatamente (kill switch authoritative — impede custo mesmo via API direta). Implementação preservada abaixo do bloqueio para reabilitar facilmente.
- `composables/useMediaAi.js`: `export const CLIP_GENERATION_ENABLED = false`; `startClip` vira no-op (toast de aviso) quando desabilitado.
- `ProductPhotosCard.vue` e `AnunciosView.vue`: botões "Criar clip (IA)" ocultos via `v-if="CLIP_GENERATION_ENABLED"`.
- Reabilitar: trocar a flag para `true` + remover o `raise` no endpoint.
- Verificação: media.py sintaxe OK; `npm run build` OK.

## 2026-06-14 — feat(campaign-ads): Raio-X do anúncio + detalhe de campanha (fase 2) (local, não enviado)

Os 2 recursos deixados fora de escopo na fase 1 do módulo Campanha ADS. Avaliação prévia do consistency-auditor aplicada — pegou 1 CRITICAL: a URL de detalhe de campanha da §9.2 do levantamento (sem advertiser) está na lista de descontinuados; usei a forma COM `advertiser_id` no path + `api-version: 2`.

- `services/ml_service.py`: `CAMPAIGN_DETAIL_METRICS` (= base + impression_share/top_impression_share/lost_*_budget/lost_*_ad_rank/acos_benchmark, que só existem no detalhe). `get_campaign_detail(token, site_id, advertiser_id, campaign_id, …)` com advertiser no path. `search_product_ads` ganhou `aggregation_type` (None|item|DAILY) para a série temporal do Raio-X.
- `routers/campaign_ads.py`: `GET /product/campaign-detail` e `GET /product/ad-detail` (Raio-X). O ad-detail dispara as 2 visões obrigatórias (item + DAILY) em paralelo via `asyncio.gather` (a API só aceita 1 aggregation_type por chamada). Mesmo gating/validação da fase 1.
- Frontend: `useCampaignAds.js` (+loadCampaignDetail/loadAdDetail); `components/campanha-ads/CampaignDetailModal.vue` (estratégia traduzida PT, orçamento, metas, share de impressões em barras + acos_benchmark — share/benchmark tratados como null⇒"—", não 0); `components/campanha-ads/AdRaioXModal.vue` (cards + funil + gráfico de linha diário ApexCharts, série DAILY normalizada defensivamente: date||day||aggregation_date, esconde o gráfico se ausente). `CampaignAdsView.vue`: coluna Raio-X (👁) na tabela de anúncios + botão "Detalhe completo" na campanha expandida; modais recebem os dados da linha p/ exibição imediata.
- Verificação: backend importa OK (6 rotas no router, incluindo as 2 novas); `npm run build` OK; `pytest -m "not integration"` = 25 passed, 2 failed (pré-existentes, test_orders.py).
- Incerteza registrada p/ validação ao vivo: nome do campo de data da agregação DAILY (tratado defensivamente no front).

> **Local apenas.** Não enviado a GitHub/servidor.

## 2026-06-14 — feat(campaign-ads): submenu "Campanha ADS" (OPERAÇÕES) + acompanhamento de campanhas por CMIG (local, não enviado)

Página read-only de acompanhamento de Product Ads e Catálogo/UP do Mercado Livre por CMIG. Dados AO VIVO da API de Mercado Ads (sem job, sem tabela nova). Seletor CMIG → anunciante (o par `account_id`+`advertiser_id` é a chave, pois o advertiser pertence ao token de uma conta). Avaliação prévia do consistency-auditor aplicada (4 ajustes incorporados antes de codar).

- `services/ml_service.py`: `PRODUCT_ADS_METRICS` + `search_product_ads_campaigns`/`search_product_ads`/`search_ad_groups` (endpoints `/search`, api-version 2). `get_advertisers` agora parametriza `product_id` e usa `Api-Version: 1` (correção do levantamento). `get_ads_cost` migrado para o `/search` (o endpoint antigo foi descontinuado pelo ML em fev/2026).
- `routers/campaign_ads.py` (novo, prefix `/api/v1/campaign-ads`): `GET /advertisers?cmig_id`, `/product/campaigns`, `/product/ads`, `/catalog/ad-groups`. Gating `require_menu_permission("campanha_ads")` + acesso à conta via `_get_account_or_403` (reuso de anuncios.py). Validação de janela ≤90 dias; tolerância a erro por conta. Registrado em `main.py`.
- `routers/profiles.py`: `MENU_CATALOG` ganha `campanha_ads` (seção OPERAÇÕES).
- Frontend: `composables/useCampaignAds.js` (chamadas + derivadas), `views/campanha-ads/CampaignAdsView.vue` (abas PRODUCT[Campanhas/Anúncios] + CATÁLOGO/UP, cards globais, insights, lista expansível com metas, tabela de anúncios paginada). Rota `/campanha-ads`; item na sidebar (OPERAÇÕES, `fas fa-bullhorn`); `campanha_ads` nos `_legacyMenus` (admin, ac).
- Fora de escopo desta fase (registrado): abas DISPLAY/BRAND, "Raio-X do anúncio" e detalhe de campanha (métricas impression_share etc.).
- Verificação: backend importa OK (4 rotas); `npm run build` OK (chunk CampaignAdsView gerado); `pytest -m "not integration"` = 25 passed, 2 failed (pré-existentes em test_orders.py, sem relação).

> **Local apenas.** Não enviado a GitHub/servidor.

## 2026-06-12 — feat(ai-config): Fase B.1 — provider de IA de mídia (Gemini/Nano Banana) (local, não enviado)

Subdividida a Fase B em B.1/B.2/B.3 por recomendação do consistency-auditor (risco do outpaint + conflito 1024px vs mínimo do marketplace). Esta é a B.1 — base para gerar/editar imagem por IA.

- Migration `Scripts SQL/103_ai_config_media.sql` (idempotente, ORA-1430): adiciona `media_provider`/`media_api_key`/`media_image_model` em `ai_configs`.
- Modelo `AIConfig` (models/messages.py): 3 colunas de mídia (chave em base64, independente da IA de chat).
- `routers/ai_config.py`: GET retorna campos de mídia (chave mascarada) + `media_available_models`; PUT salva (admin). `MEDIA_MODELS` = {google: gemini-2.5-flash-image, openai: gpt-image-1}.
- `AIConfigView.vue`: nova seção "IA de Mídia (imagens)" — provider/chave/modelo + aviso de custo.
- Verificação: backend importa OK; `npm run build` OK. Pendente: migration 103 no Oracle.

> **Local apenas.** (B.2 implementada na sequência; B.3 pendente.)

## 2026-06-12 — feat(media): Fase B.2 — gerar foto por IA (Gemini) no wizard de anúncios (local, não enviado)

- `services/media_ai_service.py`: `generate_image` (Gemini 2.5 Flash Image, trata timeout/safety/sem-imagem) + `upscale_to` (Pillow, amplia ao px recomendado do marketplace — decisão "upscale", resolve o limite ~1024px do Gemini vs mínimo do ML).
- `services/product_brief.py`: `build_product_brief` (PG/CMIG) reutilizável, sanitizado (anti prompt-injection).
- `routers/media.py`: `POST /api/v1/media/generate-image` (prompt + ficha técnica opcional + fotos de referência → imagem salva em static/uploads/media). Registrado no main.py.
- `AIConfigView`: já tinha a seção de mídia (B.1). `AnunciosView`: botão **"Criar foto (IA)"** com painel (prompt, incluir ficha técnica, usar fotos como referência, aviso de custo) → adiciona a imagem gerada às fotos do wizard.

### Auditoria de fechamento
- quality-guardian pegou **1 CRITICAL** (path traversal em `_fetch_image`: `/static/../.env`/Wallet exfiltrados ao Gemini) + **2 HIGH** (SSRF via URL http externa; custo sem rate limit). **Corrigidos**: `_safe_static_path` (containment em static/ + só extensão de imagem), `_is_public_https` (bloqueia http e IPs privados/metadata/loopback), `follow_redirects=False` + check content-type, cap de prompt (4000), `_save_image` detecta formato real + trata I/O. Proteções testadas (traversal/SSRF/metadata rejeitados).
- consistency-auditor: NÃO BLOQUEADO — tudo no padrão.
- **Follow-up (HIGH residual):** rate limit/cota por usuário no endpoint pago — Gemini tem quota própria; documentado como pendência.
- Verificação: `npm run build` OK; `pytest -m "not integration"` 25 passed. Pendente: migrations 102/103 no Oracle.

## 2026-06-14 — feat(media): clip — preview, exclusão e associação ao produto (local, não enviado)

- **#1 Preview:** `ClipPreviewModal.vue` (overlay com `<video controls autoplay muted playsinline>` + baixar/fechar), reutilizável. Clicar no clip abre o modal (ProductPhotosCard e AnunciosView).
- **#2 Excluir:** `DELETE /media/clips/{job_id}` (ownership por user_id; apaga o mp4 via `_safe_static_path(..., exts=('.mp4',))` — agora parametrizado; best-effort). `useMediaAi.deleteClip`. Botão de lixeira em cada clip + confirm.
- **#3 Associar ao produto:** migration `106` (colunas `product_type`/`product_id` em `media_clip_jobs`); `generate-clip` grava o produto; `GET /media/clips` aceita filtro opcional por produto (sempre escopado ao user_id); `ProductPhotosCard` lista só os clips daquele produto. O clip fica **persistido/associado ao produto** (pronto).
- **Investigação ML (envio do clip):** skill + busca + doc oficial (403) — a API pública de itens do ML aceita vídeo só via `video_id` (YouTube); **upload de MP4 ("Clips") não tem endpoint público confirmado**. Por isso o envio automático do MP4 ao ML na publicação **não foi construído** (evitar dead code). O clip fica pronto/associado; o envio depende de confirmar o endpoint de upload do ML (ou marketplaces que aceitam MP4, ex.: Shopee/TikTok, quando integrados).
- Auditoria: avaliação prévia + fechamento (quality-guardian) — NÃO BLOQUEADO, sem CRITICAL/HIGH. Follow-up: cancelar a operação Veo ao excluir clip em geração (custo); STATIC_DIR absoluto. Verificação: build OK; pytest 25 passed. Pendente: migration 106 no Oracle.

## 2026-06-12 — fix(media): ORA-12899 no prompt do clip — truncar por bytes, não chars (local)

`media_clip_jobs.prompt` é VARCHAR2(1100) (conta bytes). Com instruções+prompt+brief e acentos UTF-8, 1100 chars = 1133 bytes → ORA-12899. Trocado o corte `[:1100]` (chars) por `_truncate_bytes(final_prompt, 1000)` (bytes, sem quebrar caractere). Testado.

## 2026-06-12 — fix(media): formato de imagem do Veo (bytesBase64Encoded) — clip dava 400 (local)

`start_video` enviava a imagem como `inlineData` (formato do generateContent), mas o Veo (predictLongRunning) exige `image: { bytesBase64Encoded, mimeType }`. Erro: "`inlineData` isn't supported by this model" (400). Corrigido em `services/media_ai_service.py`. Testado ao vivo: operação criada com sucesso (sem 400/429).

## 2026-06-12 — feat(ai-config): instruções/perfil de mídia aplicadas a todos os prompts de IA (local)

Campo de "Instruções / Perfil de Mídia" no card de IA de Mídia, prefixado a TODO prompt de foto e clip (análogo ao global_instructions do chat).
- Migration `Scripts SQL/105_ai_media_instructions.sql`: coluna CLOB `media_instructions` em `ai_configs`. Modelo `AIConfig.media_instructions` (Text).
- `ai_config` GET (2 ramos) + PUT (limitado a 500 chars — evita estourar o cap de 1024 do prompt do Veo).
- `media.py`: `_load_media_ai` agora retorna também as instruções (sem query extra); helper `_with_instructions` prefixa o perfil nos 3 endpoints (generate-image, ai-edit, generate-clip).
- `AIConfigView`: textarea (máx 500, contador) no card de IA de Mídia.
- Avaliação prévia (consistency-auditor): 3 ajustes incorporados — cap de tamanho (WARN-1), helper único reusando `_load_media_ai` (WARN-2), campo nos 2 ramos do GET + load fora do `if configured` (WARN-3). Verificação: build OK; pytest 25 passed. Pendente: migration 105 no Oracle.

## 2026-06-12 — fix(media): endpoint Gemini v1beta + recursos de mídia nos forms de produto (local)

### #2 — Erro 400 na geração de imagem
- **Causa:** o service usava o endpoint **`v1`** do Gemini, que rejeita `generationConfig.responseModalities` → 400. Corrigido para **`v1beta`** (`GEMINI_URL`). Mensagens de erro agora mostram o motivo real (ex.: quota/billing) via `_api_error_detail`.
- **Diagnóstico:** com `v1beta` o request passa, mas a chave free-tier do usuário retorna **429 (quota 0)** — geração de imagem/vídeo do Gemini/Veo **exige billing habilitado** (não funciona no nível gratuito). Comunicado ao usuário.

### #1 — Recursos de mídia nos forms de produto (PG e CMIG)
Os 3 recursos (gerar foto IA, gerar clip IA, drag-drop) que só existiam no wizard de anúncios foram levados para os forms de produto, via o componente compartilhado `ProductPhotosCard.vue` (usado por Pg/Cmig Product e Composite forms).
- **Composable novo `useMediaAi.js`** (B3 do auditor): centraliza generatePhoto/startClip/pollClip/loadClips/clearTimers (cleanup no unmount). `AnunciosView` **refatorado** para usá-lo (removida a duplicação).
- **`ProductPhotosCard.vue` reescrito**: drag-drop (vuedraggable, item-key=url) no lugar dos chevrons; botões "Criar foto (IA)" e "Criar clip (IA)" (via composable, com product_type/product_id); correção no upload (abre `ImageCorrectionModal` com spec genérico 1:1/1200 em vez de só rejeitar); lista de clips gerados. Contrato `modelValue=[{url,...}]` preservado.
- **Forms** PG/CMIG (simples e composto) passam `product-type`/`product-id` (null na criação).
- **Backend (B1):** `/media/generate-image` usa `rec_px = ... or 1200` (upscale mínimo quando não há marketplace) — sem `target_px`.

### Auditoria
- Avaliação prévia: 3 BLOQUEADORES (B1/B2/B3) — todos incorporados antes de codar.
- Fechamento (quality-guardian + consistency-auditor): **APROVADO, sem CRITICAL/HIGH**. Ajustes LOW aplicados: reset de `aiPhoto` no openWizard; props nos forms compostos.
- Follow-up: role guard/rate-limit nos endpoints pagos; expurgo de mídia antiga; dedupe de URLs.
- Verificação: `npm run build` OK; `pytest -m "not integration"` 25 passed.

## 2026-06-12 — feat(media): Fase C — gerar clip/vídeo por IA (Veo) no wizard (local, não enviado)

#4 (clip): botão "Criar clip (IA)" no wizard, geração assíncrona via Veo (Google), com prompt padrão configurável por marketplace.

- Migration `Scripts SQL/104_media_clip_jobs.sql`: coluna `media_video_model` em `ai_configs` + tabela `media_clip_jobs` (persiste a operação long-running para sobreviver a reload e listar clips). Modelos: `AIConfig.media_video_model`, `MediaClipJob`.
- `ai_config`: provider de vídeo (`MEDIA_VIDEO_MODELS`, Veo) + GET/PUT; renomeado `MEDIA_MODELS`→`MEDIA_IMAGE_MODELS`. `AIConfigView`: select de modelo de vídeo.
- `media_ai_service`: `start_video`/`video_status`/`download_video` (Veo v1beta long-running; download com limite de 100 MB).
- `routers/media.py`: `POST /media/generate-clip` (inicia, persiste job, cota de 3 simultâneos/usuário), `GET /media/clip-status/{job_id}` (poll; ao concluir baixa e salva o mp4), `GET /media/clips` (lista/recupera). Aspecto do clip vem do spec do marketplace.
- `DEFAULT_MEDIA_SPECS.clip.ai_prompt` (prompt padrão) editável na `MarketplaceSettingsView`; usado como sugestão no `AnunciosView`.
- `AnunciosView`: painel "Criar clip (IA)" + polling (teto ~10min, timers cancelados ao reabrir) + lista "Clips gerados" (preview + download). ML aceita vídeo só por YouTube → o clip é asset para download/uso manual.

### Auditoria de fechamento
- quality-guardian pegou **1 CRITICAL** (vazamento da `x-goog-api-key` em redirect do `download_video`) + HIGH (timers de polling órfãos; endpoint pago sem cota). **Corrigidos**: `download_video` segue redirects manualmente validando o host (allowlist Google + IP público) a cada salto; timers de polling rastreados/cancelados; cota de 3 clips simultâneos por usuário; guard de `user_id` reforçado (anti-IDOR); re-checagem do job antes do download (anti-corrida). Verificado: hosts externos/http rejeitados.
- consistency-auditor: NÃO BLOQUEADO — todas as 8 recomendações da avaliação prévia atendidas.
- **Follow-up:** rate limit em `generate-image`/`ai-edit` (imagens, mais baratas); expurgo periódico de mp4 antigos (retenção).
- Verificação: `npm run build` OK; `pytest -m "not integration"` 25 passed. Pendente: migrations 102/103/104 no Oracle.

## 2026-06-12 — feat(media): Fase B.3 — correção de imagem ao padrão do marketplace (local, não enviado)

#3 das melhorias: ao subir foto no wizard de anúncios, mostra o padrão do marketplace e, se a imagem estiver fora do padrão, oferece correção.

- Backend `POST /api/v1/media/ai-edit` (routers/media.py): outpaint por IA — recebe a imagem já no formato alvo (cliente adiciona borda branca), a IA preenche; limite de upload (15 MB, `file.read(MAX+1)`→413), valida extensão (`_IMG_EXTS`), upscale ao px do marketplace, salva via `_save_image`. Reusa helpers da B.2.
- `composables/useImageStandard.js`: `validateImage` (compara dimensões/proporção/MB/formato com o spec), `cropToAspect` e `padToAspect` (canvas, sem custo).
- `components/common/ImageCorrectionModal.vue`: modal **reutilizável** (props imageSpec/uploadUrl, sem acoplamento a anúncio) — opções Ajustar (crop) / Adicionar borda / Estender com IA (com confirmação de custo) / Usar como está; em erro de IA mantém aberto.
- `AnunciosView`: input "Enviar foto do computador" + texto do padrão (do marketplace da conta) → valida; fora do padrão abre o modal; dentro do padrão sobe direto.

### Auditoria de fechamento
- quality-guardian + consistency-auditor: **NÃO BLOQUEADO**, sem CRITICAL/HIGH; as 6 recomendações da avaliação prévia foram atendidas (limite de tamanho, confirmação de custo, spec de selectedAccount.platform, modal reutilizável, reuso de _IMG_EXTS, não fechar em erro). UploadFile não passa por _fetch_image (sem vetor de traversal/SSRF).
- Aplicado fix LOW: revoke de object URL no erro do loadImage.
- Follow-up LOW: extrair helper de upload (duplicado view/modal) e constante do texto de custo ao plugar o modal em PG/CMIG forms.
- Verificação: `npm run build` OK; `pytest -m "not integration"` 25 passed.

---

## 2026-06-12 — feat(marketplace-settings): Fase A — Config de Marketplaces + drag-drop de fotos (local, não enviado)

Primeira fase da feature de configuração de marketplaces (das 5 melhorias solicitadas). Fases B/C (IA imagem/vídeo) ficam para depois.

### #1 Página de Config de Marketplaces (Super Admin)
- Migration `Scripts SQL/102_marketplace_settings.sql` (idempotente): tabela `marketplace_settings` (1 linha/marketplace, `settings_json` CLOB flexível, unique em marketplace).
- Modelo `MarketplaceSetting` em `models/integration.py`.
- Router `routers/marketplace_settings.py` (`/api/v1/marketplace-settings`): GET autenticado, PUT só `require_role("admin")`. Padrão do `ai_config` (singleton + JSON, sem prefixo extra no main). Registrado em `main.py`.
- Menu key `config_marketplaces` em `routers/profiles.py` (MENU_CATALOG) + sidebar (v-if da seção + RouterLink) + rota `/settings/marketplaces` (role:'admin').
- View `FRONTEND/src/views/settings/MarketplaceSettingsView.vue` — abas por marketplace (ML, Shopee, Amazon, TikTok Shop, Magalu).

### #2 Formatos de mídia por marketplace
- `DEFAULT_MEDIA_SPECS` no router com os formatos recomendados (pesquisados) por marketplace — mesclados na leitura, editáveis na tela (imagem: proporção/px/MB/formatos/fundo; clip: proporção/seg/MB/formato/entrega).

### #5 Drag-and-drop de fotos
- `AnunciosView.vue`: reordenação de fotos do wizard trocada dos botões ◀▶ (`moveImage`, removido) por **arrastar** com `vuedraggable` (já instalado). Capa = 1ª foto.

### Processo / Auditoria
- Avaliação prévia (consistency-auditor) sobre o plano pegou 2 CRÍTICOS antes de codar: #5 mirava `ImageUploader.vue` (código morto) → redirecionado ao `AnunciosView.vue` real; menu_key precisava em profiles.py + sidebar → feito nos dois.
- Auditoria de fechamento (quality-guardian + consistency-auditor): NÃO BLOQUEADO, sem CRITICAL/HIGH. Removida função órfã `moveImage`; prefixo documentado no CLAUDE.md.
- Verificação: `npm run build` OK; `pytest -m "not integration"` 25 passed (2 pré-existentes). Pendente: rodar migration 102 no Oracle ao subir.

> **Local apenas** — não commitado/enviado a pedido do usuário.

---

## 2026-06-12 — refactor(anuncios): helper _sync_fiscal_for_sku unifica padrão fiscal por SKU (local, não enviado)

Centralizou o padrão "monta payload → register_or_update_fiscal_information → trata retorno/erro" que estava repetido em 5 fluxos. Novo helper `async _sync_fiscal_for_sku(access_token, product, sku, cmig_crt, fiscal_overrides) -> str|None` (retorna aviso em falha, None em sucesso/sem-NCM; best-effort, não propaga).

Call-sites unificados: `publish_anuncio` (create), `publish_anuncio_with_variations`, `publish_anuncios_as_family`, `update_anuncio` (update), `sync_listing`. O endpoint dedicado de fiscal-information ficou de fora (contrato diferente: retorna resultado bruto + 400 sem NCM).

Melhorias de observabilidade (avaliadas pelo consistency-auditor antes de implementar):
- Mensagem de erro unificada ("Erro ao sincronizar fiscal_information") e chave única `fiscal_sync_warning` em todos os fluxos.
- Variação agora agrega avisos por SKU (dedupe + 5 primeiros + "… e mais N") no response — antes engolia falhas silenciosamente.
- Família anexa `fiscal_sync_warning` ao item de `results` do produto que falhar.

Auditoria: consistency-auditor (prévia, sobre o plano) aprovou com 4 cuidados — todos incorporados (chave única, dedupe/truncate, captura antes do append, mensagem canônica). quality-guardian (fechamento) NÃO BLOQUEADO, sem CRITICAL/HIGH, confirmou ausência de shadowing. Testes: `pytest -m "not integration"` 25 passed; teste funcional do helper nos 4 caminhos OK.

> **Local apenas** — não commitado/enviado a pedido do usuário (aguardando outras alterações antes de atualizar GitHub + servidor).

---

## 2026-06-12 — fix(anuncios): paridade do publish-as-family + regra de avaliação prévia

### publish-as-family
Alinhado aos fluxos simples e de variação: agora envia **descrição** (`post_item_description`, fallback `product.description`), **`fiscal_information` por SKU** (Faturador NFe), `video_id` (no `ml_form` e persistido no `ProductListing`) e grava `description_override`. Antes publicava itens da família sem descrição e sem fiscal (reproduzia "Sku not found" no Faturador).

### Governança (CLAUDE.md)
Nova seção **"Avaliação Prévia Obrigatória (antes de implementar)"**: para toda solicitação, o `consistency-auditor` avalia a solicitação do usuário + o plano de execução da Claude ANTES de codar (exceto tarefas triviais/somente-leitura).

### Auditoria desta entrega
quality-guardian: aprovado (sem CRITICAL/HIGH). consistency-auditor: sem bloqueio; pegou 1 MÉDIA (video_id não persistido no listing da família) — corrigido. Follow-up sugerido: helper `_sync_fiscal_for_sku` unificando o padrão fiscal repetido em 4 lugares. Verificação: `pytest -m "not integration"` 25 passed.

---

## 2026-06-12 — fix(anuncios): publicação carrega descrição, fiscal, vídeo e ficha técnica do produto

### Problema
Publicação de anúncios não levava vários campos do produto ao ML. **Variação**: sem descrição, sem fiscal (NCM/CEST/ORIGIN nem fiscal_information), sem dimensões/BRAND. **Simples**: descrição sem fallback ao produto; `video_id` e `attributes_json` (ficha técnica) nunca enviados em nenhum fluxo.

### Backend (`routers/anuncios.py`)
- **Novo helper `_collect_item_attributes(product, form, *, include_seller_sku)`**: centraliza produto→atributos (BRAND, SELLER_SKU, MODEL, NCM, CEST, GTIN, ORIGIN, dimensões do pacote + **ficha técnica via `product.attributes_json`**). `_build_ml_payload` passou a usá-lo + envia `video_id`.
- **Novo `_attrs_list_from_json`**: parseia `attributes_json` (formatos `{id,value_name}` e `{id,name,value}`).
- **Simples (`publish_anuncio`)**: descrição agora cai em `product.description`.
- **Variação (`publish_anuncio_with_variations`)**: usa produto representativo (`loaded_list[0]["product"]`) para atributos-pai (fiscal/ficha/dimensões/BRAND), `video_id`, descrição (`post_item_description`, fallback produto) e **`fiscal_information` por SKU de cada variação**. `_load_variation_product` passou a devolver o objeto `product`.
- **Update de variação**: atualiza descrição no ML (`update_item_description`) + persiste `description_override`.

### Frontend (`CatalogVariationsFormView.vue`)
- Campo **Descrição** (textarea) no form de variação; enviado no payload; pré-preenchido na edição. Placeholder indica que, se vazio, usa a descrição do produto (fallback do backend).

### Observações
- Com os fallbacks no backend, a publicação carrega os campos do produto **mesmo sem digitar nada** no formulário.
- Pendente opcional: pré-preencher descrição/fiscal no wizard simples (UX — backend já cobre o dado) e integrar atributos curados do `ProductMarketplaceCategory` nos fluxos principais.
- Verificação: `npm run build` OK; `pytest -m "not integration"` 25 passed (2 falhas pré-existentes em test_orders); teste funcional do helper (SELLER_SKU só no simples, BRAND sem duplicar, NCM limpo, ficha técnica mesclada).

---

## 2026-06-12 — fix(stock): backfill de reservas órfãs não toca mais no estoque event-sourced

### Causa
O `backfill_orphan_dispatches` rodava `confirm_dispatch`, que **decrementa `stock_quantity`**. Mas o estoque de PG/CMIG é **event-sourced** ([services/fiscal/stock_calculator.py](BACKEND/services/fiscal/stock_calculator.py)): o pedido `shipped`/`delivered` já é a saída canônica. Resultado: **dupla contagem** — o backfill baixou o físico de novo, depois o recompute sobrescreveu. Diagnóstico no SKU 5510: NFe entrada (13) − 8 entregas = 5 (correto); o backfill tinha zerado pra 0 e exigido recompute manual.

### Mudança
- `backfill_orphan_dispatches` → **`backfill_orphan_reservations`**: agora chama `release_reservation` (libera só `reserved_quantity`, loga `unreserve`), **sem tocar no estoque físico**. Removido `floor_zero` e a projeção de físico.
- Endpoint `POST /stock/backfill-orphan-dispatches` → **`POST /stock/release-orphan-reservations`** (perm. "estoque").

### Correção de dados (produção)
- Recompute canônico dos 6 produtos tocados pelo backfill anterior: 5393 14→16, 5465 251→247, 5505 5→6 (5510/5249/5528 já corretos). Todos com `armazenado == canônico`.
- Pendente: propagar o estoque novo ao ML (job `sync_stock` 30min, ou push manual).

---

## 2026-06-11 — fix(stock): reconciliador de reservas agora reconstrói variantes + diagnóstico de reserva órfã

### Contexto
Anúncio do kettlebell (PG 5510) mostrava "Local: 5 un. (0 disp.)" sem reserva aparente. Investigação: `local_stock_available = max(0, stock_quantity − reserved_quantity)` ([anuncios.py:636](BACKEND/routers/anuncios.py#L636)); a coluna `reserved_quantity` do produto estava em 8.

### Mudança de código
- **`recompute_reservations_from_movements`** ([services/stock_reservation_service.py:684](BACKEND/services/stock_reservation_service.py#L684)) agora **também reconstrói `reserved_quantity` das variantes** (`CatalogProductVariant`/`CMIGProductVariant`). Antes só reconstruía o produto-pai (`pg`/`cmig`), deixando as variantes à deriva — agravado porque `mark_awaiting_return` (pg+cmig) e o release órfão-FULL (cmig) **não logam movimento de variante**. A reconstrução das variantes vem dos **itens dos pedidos cuja reserva-pai está ativa** (fonte confiável), não dos movimentos `variant_*` (incompletos). Retorno agora inclui `pg_variants_updated`/`cmig_variants_updated`.

### Diagnóstico (produção)
- Recompute rodado: 11 produtos PG atualizados; kettlebell **manteve reservado=8** — porque NÃO é drift: são **7 pedidos `agencia` reais** (561, 581, 582, 601, 621, 622[qty2], 661) **`delivered` no ML mas presos em `status=downloaded`** no sistema, sem movimento de `dispatch`. Reserva nunca liberada e estoque físico nunca baixado → tanto `reserved=8` quanto `physical=5` estão não-confiáveis pra esse SKU.
- Lacuna sistêmica: `confirm_dispatch` no caminho de entrega tem o erro engolido ([webhook_service.py:385](BACKEND/services/webhook_service.py#L385)); entregas `agencia`/`flex` detectadas sem `status_changed` não disparam baixa.

### Backfill seguro (novo)
- **`backfill_orphan_dispatches`** ([services/stock_reservation_service.py](BACKEND/services/stock_reservation_service.py)) + endpoint **`POST /api/v1/stock/backfill-orphan-dispatches`** (perm. "estoque"): acha pedidos não-FULL `shipped`/`delivered` com reserva ativa sem `dispatch` e roda `confirm_dispatch`. **Dry-run por padrão** (`apply=false`); `floor_zero` trava físico dos afetados em ≥ 0 e sinaliza `would_go_negative`.
- **APLICADO em produção** (`apply=true`, `floor_zero=true`): 15 pedidos despachados, 6 produtos corrigidos, reservas órfãs zeradas. Verificado: 15/15 com movimento `dispatch`, 0 reservas remanescentes. SKU 5510 travado em físico=0 (precisa contagem manual no galpão). Os pedidos seguem `status=downloaded` (confirm_dispatch não altera status — só estoque/auditoria).
- Scripts temporários em `sandbox/` (run_recompute_reservations.py, diag_reserves_5510.py, run_backfill_dryrun.py, run_backfill_apply.py, verify_dispatch.py).
- **Pendente:** corrigir causa raiz (confirm_dispatch engolido/não disparado em entregas por polling) pra não reacumular.

---

## 2026-06-11 — feat(dashboard): Dashboard de Marketplaces (matriz + visitas/perguntas/ADS + ApexCharts)

Novo painel de marketplaces no formato matriz (Hoje / Ontem / 7 dias / 7 dias antes / Este Mês / Mês Anterior) com 12 métricas: Qtd Pedidos, Cancelados, Full, Flex, Outros, Faturamento (+FULL/+FLEX), Visitas, Conversão, Perguntas, Gasto no ADS.

### Diagnóstico de fontes
- Pedidos/Cancelados/Full/Flex/Faturamento → calculados ao vivo da tabela `orders` (campos `status`, `shipping_mode`, `sale_amount`, `created_at`), sem API externa.
- Visitas/Perguntas/ADS → só existem na API do ML e não eram persistidos → criado snapshot diário.

### Backend
- **Migration `Scripts SQL/101_marketplace_metrics_daily.sql`** (idempotente): tabela `marketplace_metrics_daily` (1 linha por conta/dia: visits, questions_total, questions_unanswered, ads_cost) com unique `(account_id, metric_date)`; + índices e `ix_orders_dropshipper_created` para as agregações.
- **Modelo `MarketplaceMetricDaily`** em `BACKEND/models/integration.py`.
- **Job `BACKEND/tasks/sync_marketplace_metrics.py`** (4x/dia via `CronTrigger hour="2,8,14,20" minute=10` em `scheduler.py`): para cada conta ML ativa, coleta visitas (breakdown por dia, com backfill de ontem), perguntas do dia e gasto em ADS; upsert por conta/dia. Tolera falha por conta; pula `requires_reauth`.
- **Helper `get_account_visits_by_day`** em `services/ml_service.py` (o existente era fixo em 7 dias agregados).
- **Endpoint `GET /api/v1/dashboard/marketplace`** em `routers/dashboard.py`: janelas em fuso America/Sao_Paulo; escopo por `dropshipper_id` (admin/GO veem tudo) + filtros opcionais `account_id`/`platform`; retorna `rows` (12 métricas × 6 janelas), `extras` (ticket médio, ACOS, margem, taxa de cancelamento) e `row_meta`.

### Frontend
- **ApexCharts** adicionado (`apexcharts` + `vue3-apexcharts`, registrado em `main.js`).
- **`FRONTEND/src/views/MarketplaceDashboardView.vue`**: barra de filtros (conta + plataforma), 4 cards hero (Faturamento, Pedidos hoje, Conversão, ACOS), matriz, donut Full/Flex/Outros, barras Pedidos/período, gauge de Conversão.
- **`FRONTEND/src/components/dashboard/MetricsMatrix.vue`**: tabela-matriz com cores condicionais e setas (7d vs 7d antes; mês vs mês anterior); linhas ML-only com badge "ML".
- Rota `dashboard/marketplace` em `router/index.js` + item "Dashboard Marketplaces" na sidebar.

### Verificação
- `npm run build` OK; imports do backend OK (`routers.dashboard`, `tasks.sync_marketplace_metrics`, `tasks.scheduler`, `services.ml_service`); `pytest -m "not integration"` 25 passed (as 2 falhas de `test_orders` são pré-existentes — `MockResult` sem `scalar`, confirmado via stash).
- Pendente em produção: rodar a migration 101 no Oracle e o 1º disparo do job (visitas/ADS = 0 até então).

> Nota git: o commit `54ab716` (eship), feito por processo paralelo durante a sessão, absorveu os arquivos de backend deste dashboard. O frontend permaneceu não-commitado.

---

## 2026-06-11 — fix(integrations): refresh OAuth ML coordenado + isolamento da conta no callback

Correção da causa de o sistema "perder a conexão" com as contas ML e da mistura
da conta CMIG com a sessão logada no navegador.

**Causa raiz (perda de conexão):** o refresh token do ML é de uso único (rotaciona
a cada uso). O refresh estava espalhado em 5 lugares sem coordenação (job sync_tokens,
anuncios, stock, simulator, DRE) → duas renovações concorrentes com o mesmo refresh
token davam `invalid_grant` → conta marcada `requires_reauth` → caía.

**Estabilização:**
- `services/ml_auth.get_valid_token` agora é o ponto ÚNICO de refresh: lock por
  `account_id` (PM2 = 1 worker), re-leitura da conta dentro do lock, e recuperação
  no `invalid_grant` (se outro caminho já renovou, usa o token novo em vez de desativar).
- `_refresh_with_retry` só retenta em erro de conexão (não em invalid_grant nem
  read-timeout, que poderiam gastar o token de uso único); timeout explícito (20s).
- Unificados os refresh duplicados: `sync_tokens` (margin 1h, proativo), `stock`,
  `simulator` e `anuncios` passam a chamar `ml_auth.get_valid_token`.

**Isolamento browser ↔ conta:**
- `ml_callback` valida que o vendedor autorizado é o da conta (`platform_user_id`/
  e-mail). Se divergir, NÃO sobrescreve e redireciona com instrução (sair do ML no
  navegador / aba anônima). Mostra o vendedor conectado no sucesso.
- `OAuthSuccessView` trata `status=wrong_account` e exibe a conta conectada.

**Verificação:** pytest 20 passed (2 falhas pré-existentes de test_orders, sem relação);
`npm run build` OK; deploy `685e0c2`, pm2 restart, health local+HTTPS 200.

---

## 2026-06-08 — feat(financial): Gestão Financeira (DRE de marketplace por CMIG)

Nova aba **Gestão Financeira (DRE)** dentro de Financeiro: P&L mensal por CMIG, no formato
Entrada → Custo Operacional → Margem de Contribuição → Custo Fixo → Lucro Líquido, com
sincronização por mês (ícone ↻) contra o Mercado Livre.

Modelo de 3 camadas somadas por linha: snapshot ML (cache) + lançamentos manuais + imposto derivado.
- **Migrations 89/90/91**: `dre_snapshots` (cache mensal por CMIG), `dre_entries` (lançamentos manuais
  com recorrência via `recurrence_group_id`), e `cmig_fiscal_config.tax_estimate_pct` (% imposto DRE).
- **Models**: `models/dre.py` (DRESnapshot, DREEntry); `tax_estimate_pct` na CMIGFiscalConfig.
- **`services/ml_auth.py`**: extraído `get_valid_token` (padrão antes duplicado em anuncios/stock/simulator).
- **`services/ml_service.py`**: billing (`get_billing_periods/summary/details`) + ADS
  (`get_advertisers`, `get_ads_cost`, header `api-version: 2`).
- **`services/dre_service.py`**: `sync_month` (operacional via agregação SQL de `orders` + ADS +
  conciliação billing, best-effort/tolerante a falha), `build_dre` (monta a grade), CRUD de
  lançamentos com expansão de recorrência e edição/exclusão "esta/futuras".
- **Router**: endpoints `/financial/dre`, `/dre/sync`, `/dre/cmigs`, `/dre/entries` (CRUD), com
  `require_menu_permission("financeiro")` + checagem de acesso à CMIG.
- **Frontend**: `FinancialView` vira abas (Conta Corrente + DRE); novos `DRETab.vue` (grade +
  sync por mês + export CSV/print) e `DREEntryModal.vue` (lançamentos); campo "% Imposto (DRE)" no
  `CmigFiscalConfigCard`.
- **Testes**: `tests/test_dre.py` (math da grade, _month_range, recorrência cruzando o ano) — 3 verdes.
- **Verificação**: `npm run build` OK; app sobe e registra as rotas `/financial/dre*`; pytest verde
  (exceto 2 falhas pré-existentes em test_orders por limitação do MockResult, não relacionadas).
- **Pendências**: export Excel/PDF é client-side (CSV + print) — endpoint dedicado fica p/ fase 2;
  escopos OAuth de `/billing` e `/advertising` precisam validação contra conta ML real (degradam
  para operacional sem quebrar). Auditorias quality-guardian/consistency-auditor/ADR-0006 recomendadas.

---

## 2026-06-07 — change(separation): imprimir etiqueta marca pedido como "separado"

Nova regra: ao imprimir a etiqueta de um pedido na gaiola, ele já vira **separado** (por pedido),
sem esperar a conclusão da gaiola. A consulta de separação mostra o status da gaiola sempre que
o pedido pertence a uma.

- `cart_labels`: além de `label_printed_at`, marca `item_status='separated'`, `order.status='separated'`,
  `separated_at/by`. (No modo scan a etiqueta só sai após bipar 100%, então a separação fica conferida.)
- `remove_order_from_cart`: passa a permitir remover pedido já separado (gaiola aberta), revertendo
  `order.status` (→ paid/downloaded conforme pagamento) e limpando carimbos. `cancel_cart` alinhado.
- `SeparationInfoModal`: seção "Gaiola" (código/status/modo) exibida sempre que há gaiola.
- Data fix #742: tinha etiqueta impressa (23:40) → marcado como separado (gaiola 21 aberta);
  `shipped_at` órfão já havia sido limpo.

---

## 2026-06-07 — feat(orders): detalhes de separação/coleta nos ícones da Gestão de Pedidos

Os ícones 5 ("Pedido Separado") e 6 ("Coletado p/ Entrega") do `OrderStatusStepper` agora são
clicáveis e abrem um modal com os detalhes vindos do módulo de gaiola.

- Backend `GET /orders/{id}/separation-info`: junta `order.separated_*`/`dispatched_*` com a gaiola
  (`picking_cart_id` → cart_number/cart_mode/status) e resolve nomes dos operadores.
- `OrderStatusStepper.vue`: passos `separated`/`shipped` clicáveis quando alcançados (emits
  `click:separated`/`click:shipped`).
- Novo `SeparationInfoModal.vue` + wiring em `OrderListView.vue`: modal com data/hora, usuário,
  modo (Manual/Bipagem), código e status da gaiola (separação) e data/hora + usuário da coleta.
- Sem migration (campos já existem). Pedidos separados fora de gaiola exibem detalhes parciais.

---

## 2026-06-07 — feat(users): botão único "Novo Usuário" com Perfil definindo o acesso

Tela de cadastro de usuários (`UsersView.vue`) tinha 2 botões ("Novo Operador Logístico" e
"Novo Gestor de Conta"). Unificados em um só botão "Novo Usuário", modal simples (como o do UGO)
com campo **Perfil de Acesso** (como na edição) para definir os acessos.

- Backend: novo endpoint `POST /auth/register/user` (`auth.py`) + schema `RegisterUserRequest`.
  O `profile_id` define o papel via `base_role` do perfil; sem perfil → `ugo`. GO não pode criar
  admin/go (anti-escalonamento). Para `base_role == 'ac'` cria um `ACProfile` (endereço/plano
  podem vir vazios). Endpoints antigos `/register/ugo` e `/register/ac` mantidos.
- Frontend: botão único; modal mostra Perfil no cadastro (admin); campos de AC
  (CPF/endereço/plano) aparecem só quando o perfil selecionado é de Gestor de Conta.
- Verificado: `py_compile` backend OK, `npm run build` OK.

---

## 2026-06-07 — fix(separation): NF-e da gaiola ficava presa em "processando"

Causa: `cart_emit_nfe` emitia no ML e marcava `pending`, mas **não sincronizava o resultado
de volta** (a Gestão de Pedidos faz esse sync após emitir). Como não há job de sync de NF-e no
scheduler, o pedido ficava `pending` para sempre mesmo com a nota já autorizada no ML.

- Novo helper `_sync_nfe` (reusa `_ml.get_order_fiscal_data` + `_extract_nfe_fields`).
- `cart_emit_nfe`: após emitir, sincroniza e retorna `nfe_status`/`nfe_url` atualizados.
- `GET /carts/{id}/nfe`: para pedidos `pending/in_process` sem chave, puxa o estado do ML
  (finaliza notas presas ao abrir o NF-e da gaiola).
- Data fix: pedido #742 (venda 2000016821664834) sincronizado — estava `authorized` no ML, DANFE ok.

---

## 2026-06-07 — fix(separation): gaiola criada por admin ficava órfã de galpão (invisível ao Gest.Log)

Causa: `create_cart` usava `warehouse_id = current_user.warehouse_id`. Admin não tem galpão
(`warehouse_id=NULL`), então a gaiola ficava com `warehouse_id=NULL` e o filtro de `list_carts`
(`warehouse_id == <galpão do usuário>`) nunca casava — o Gest.Log do galpão não via a gaiola
do admin (e `_get_cart_scoped` também bloqueava o acesso).

- `create_cart` agora resolve o galpão via `_resolve_cart_warehouse`: Gest.Log usa o próprio;
  admin usa `body.warehouse_id` ou, havendo um único galpão, o único; com vários, exige escolha (400).
- Data fix: gaiolas existentes com `warehouse_id=NULL` reatribuídas ao galpão único (MIG/1) —
  a gaiola aberta #21 voltou a ser visível ao Gest.Log.
- Resultado: toda gaiola tem galpão; todos os Gest.Log do galpão (e admin) veem/editam as mesmas gaiolas.

---

## 2026-06-07 — feat(separation): Fase 2 — status de envio/NF-e, emissão, etiqueta oficial ML

Separação passou a espelhar a Gestão de Pedidos e a operar o ciclo completo da gaiola.

### Backend
- Migration `88_picking_cart_print_flags.sql`: `label_printed_at/by`, `nfe_printed_at/by` em `picking_cart_orders`.
- `list_pending_orders` retorna `shipment_status`/`nfe_status`/`nfe_key`/`nfe_url`.
- `add_orders_to_cart`: só aceita `shipment_status='ready_to_ship'`; adicionar a gaiola concluída a reabre (`separated→open`).
- `conclude_cart`: trava por **etiqueta impressa** de todos (NF-e opcional); marca todos separados. `separate_order` removido.
- Etiqueta **oficial do ML** (`label-jobs` + `labels.pdf` combinando `shipment_ids` por conta via `ml_service.get_shipment_label`); manual usa etiqueta interna. Marca `label_printed_at`.
- NF-e na gaiola: `POST emit-nfe` (claim atômico anti-dupla-emissão, só com etiqueta) e `GET nfe?mark=1` (carimba impressão). Emissão na lista reusa `POST /orders/{id}/emit-nfe`.

### Frontend (`SeparationView.vue`)
- Colunas Envio (shipment_status) e NF-e; botão "Emitir NF-e" na lista; seleção/gaiola só para Prontos p/ Envio.
- Modal "adicionar a gaiola aberta"; ícones de etiqueta/NF-e com cor (impresso); trava de Concluir = todas etiquetas impressas.

### Auditoria (nível Full) + correções
quality-guardian / consistency-auditor / adr-consistency-checker em paralelo. Sem CRITICAL; 2 HIGH corrigidos:
- **dupla emissão de NF-e** (irreversível) → claim atômico `UPDATE ... WHERE nfe_status IS NULL`.
- **re-fetch de etiqueta ML no lote** → `label-jobs`/lote ignoram etiquetas já impressas (reimpressão é por pedido).
- MEDIUM: emit-nfe bloqueia gaiola cancelada/entregue; `SHIPMENT_MAP` completo; filtro CMIG por string; 422 em labels.pdf sem seletor.
- ADR-0005 atualizado (revisão Fase 2).

### Verificação
- Migration 88 aplicada no Oracle (4 colunas). `import main` OK (16 rotas). `pytest -m "not integration"` 15 passed (2 pré-existentes). `npm run build` OK.
- Smoke DB-only das travas (ready_to_ship/etiqueta/reabertura) com revert — **pós-deploy**.

---

## 2026-06-06 — feat(separation): módulo SEPARAÇÃO p/ Operador Logístico (pedidos não-FULL)

Nova opção de menu "SEPARAÇÃO" (menu_key `separacao`) onde o Operador Logístico separa,
etiqueta e despacha os pedidos não-FULL do seu galpão (entregues pelo Galpão).

### Backend
- Migrations `85_picking_carts.sql` (picking_carts/picking_cart_orders/picking_cart_items),
  `86_orders_separation_columns.sql` (orders: separated_at/by, dispatched_at/by, picking_cart_id),
  `87_separacao_menu_key.sql` (menu_key `separacao` nos perfis admin + gl).
- Models `models/picking.py` (PickingCart, PickingCartOrder, PickingCartItem) + 5 colunas em `Order`.
- `services/picking_service.py` (lógica pura: expansão de kits, consolidação, conferência de código).
- `services/picking_list_service.py` (PDF da lista de picking consolidada por catálogo).
- `services/label_service.py` estendido: registry `LABEL_LAYOUTS` (`10x15` térmica + `a4_4up`) e
  `render_shipping_labels(orders_meta, layout)` multi-pedido.
- `routers/separation.py` (14 rotas) com `require_menu_permission("separacao")` + escopo por galpão.
  Dois modos de gaiola: **manual** e **scan** (bipagem — só separa com 100% conferido). Entrega à
  transportadora marca pedidos `shipped` e baixa estoque via `confirm_dispatch` (reuso).
- `menu_key` `separacao` adicionada ao `MENU_CATALOG` em `profiles.py`; router registrado em `main.py`.

### Frontend
- `views/separation/SeparationView.vue` (lista de pedidos + workspace da gaiola, manual e bipagem) e
  `views/separation/CartsListView.vue` (entrega à transportadora). Rotas `/separacao` e
  `/separacao/gaiolas`. Seção "SEPARAÇÃO" na sidebar + legacy menus ugo/admin.

### Auditoria (nível Full) + correções
Rodados quality-guardian, consistency-auditor e adr-consistency-checker em paralelo.
Corrigidos todos os CRITICAL/HIGH antes do fechamento:
- **C-1/CRUD**: novo `POST /carts/{id}/cancel` devolve pedidos à lista (reverte picking_cart_id +
  status separated→paid) — status `cancelled` antes inalcançável. Botão de cancelar no frontend.
- **H-1 (IDOR/PII)**: cláusula de galpão aplicada também nas queries de Order em `labels.pdf` e `nfe`.
- **H-2 (escopo NULL)**: `_get_cart_scoped` NULL-safe + `_ensure_warehouse` bloqueia operador sem galpão.
- **H-3 (corrida bipagem)**: incremento atômico `UPDATE ... WHERE scanned_qty < expected_qty` + rowcount.
- **H-4 (baixa silenciosa)**: `deliver` retorna `failed_dispatch` e loga `error`.
- **HIGH consistência**: `_resolve_base` agora faz fallback via `resolve_order_item_link`
  (ProductListing/DP/SKU) — cobre pedidos ML vinculados só pelo anúncio (picking list + bipagem de kits).
- **M-2**: `consolidate` não colapsa mais itens sem produto/SKU. **M-4**: `add_orders` retorna `skipped`.
- ADR-0005 criado (Carrinho Gaiola + estados separated/shipped); prefixo `/api/v1/separation` e ADRs
  0004/0005 adicionados ao CLAUDE.md.

### Verificação
- `import main` OK; 15 rotas `/separation/*` registram. ORM `configure_mappers()` OK.
- `pytest tests/test_picking_service.py` 5 passed; suíte `-m "not integration"` 15 passed
  (2 falhas **pré-existentes** em test_orders — MockResult sem `.scalar()`, router orders.py não tocado).
- Smoke dos PDFs (10x15, a4_4up, lista) gera `%PDF` OK. `npm run build` OK.
- **Pendente:** smoke ponta-a-ponta com usuário `ugo` em produção (migrations 85/86/87 já rodadas).

---

## 2026-06-06 — feat(stock): FULL atribuído ao CMIG + histórico completo com venda/marketplace

### Fase 1 — Atribuição FULL correta
- Novo `resolve_full_product(db, order, item)` em `full_stock_service`: resolve o produto de um item FULL preferindo o `cmig_product_id` do anúncio (ProductListing por ml_item_id+account_id), pois FULL pertence à conta CMIG. Mesma lógica do sync-full.
- `_apply_full_reservation` (reserva) e `apply_full_order_shipped` (baixa) passam a usar o resolver → movimentos e FullStock vão para o CMIG product, não mais para o PG.
- Backfill `sandbox/backfill_full_attribution.py`: re-aponta stock_movements FULL e reconstrói FullStock.reserved_qty de PG→CMIG (qty reconciliado depois via sync-full).

### Fase 2/3 — Histórico completo + venda/marketplace
- `stock_movements.build_movements_response` retorna `full_movements` (trilha FULL: full_in/out/reserve/unreserve/return), com nº da venda, plataforma, NF-e e link externo do marketplace. Não entra no saldo local.
- Endpoint inline `/stock/{type}/{id}/movements` enriquecido com order_platform/platform_order_id/marketplace_url.
- StockControlView: botão (ícone) por linha abre o `StockMovementsModal` (histórico completo); coluna Pedido do histórico inline vira link interno + link externo do marketplace.
- StockMovementsModal: link direto para a venda no marketplace nos pedidos + nova seção "Movimentações no FULL".

### Verificação
- `import main` OK; `pytest -m "not integration"` 10 passed (2 falhas pré-existentes em test_orders); `npm run build` OK.
- **Pendente:** deploy + rodar backfill de atribuição + sync-full por CMIG em produção.

---

## 2026-06-06 — feat(inventory): módulo de Inventário + estoque do PG read-only

### Objetivo
- Tirar a edição direta de estoque da tela PG (era `PUT /pg/{id}/stock`, sobrescrita no recompute) e centralizar toda alteração de estoque físico num documento de Inventário.

### Modelo / dados
- `BACKEND/models/inventory.py`: `Inventory` (number, mode 'baseline'|'adjustment', catalog_type 'pg'|'cmig', cmig_id, status draft|finalized|cancelled, created_by/finalized_by) e `InventoryItem` (system_qty snapshot, counted_qty, delta).
- Migration `Scripts SQL/84_inventories.sql`: cria as tabelas + índice + injeta menu_keys `inventario`/`inventario_criar` nos perfis de sistema (admin+gl criam; go+gc só veem).

### Cálculo (durável, sobrevive a recompute)
- `stock_history._fetch_inventory_events_for_product` + tratamento `source=='inventory'` no `stock_calculator`:
  - **baseline** → reseta o saldo para o contado na data (replay cronológico no CMIG; piso de data no PG, descartando eventos anteriores).
  - **adjustment** → soma o delta congelado (counted − system).
- Sem inventário, o comportamento é idêntico ao anterior (zero regressão).

### API / permissões
- `routers/inventories.py` (registrado em main.py em `/api/v1/inventories`): list/create/get/update-items/finalize/cancel. Leitura por `inventario`, escrita por `inventario_criar`.
- `PUT /pg/{id}/stock` agora retorna **410** (descontinuado).
- `MENU_CATALOG` ganhou `inventario` e `inventario_criar` (seção ESTOQUE GL) — configuráveis no cadastro de Perfil.

### Frontend
- PG: campo de estoque virou **somente leitura** com cadeado (`SupplierProductListView.vue`).
- Menu "Inventário" na seção ESTOQUE (`AppSidebar.vue`) + mapas legados (admin/ugo/go/ac).
- Rotas + `views/inventory/InventoryListView.vue` (grid) e `InventoryFormView.vue` (criar: modo+catálogo; contar: grid de produtos, rascunho/finalizar/cancelar).

### Verificação
- `python -c import main` OK; `pytest -m "not integration"` 10 passed (2 falhas pré-existentes em test_orders, mock sem `.scalar()`); `npm run build` OK.
- **Pendente:** rodar migration 84 no Oracle de produção; criar ADR do padrão "eventos de inventário no cálculo de estoque"; auditoria (quality-guardian/consistency-auditor) antes do fechamento formal.

---

## 2026-06-06 — fix(stock): pedidos FULL não debitam mais o estoque do galpão (dupla baixa)

### Problema (contabilização de estoque FULL)
- O cálculo canônico do estoque LOCAL (`stock_calculator` / `stock_history`) contava TODOS os pedidos `shipped/delivered`, **sem excluir os pedidos FULL**.
- Para um produto no FULL, o galpão era debitado 2x: (1) pela NF-e de transferência CMIG→CNPJ FULL (correto) e (2) pelo pedido FULL recontado como saída local (errado). As vendas do FULL "vazavam" para a contabilidade do galpão, deixando CMIG/PG subdimensionados/negativos.
- O recompute roda a cada pedido novo e a cada mudança de status, então o erro era ativo e recorrente.

### Correção (Etapa 1 — núcleo)
- Novo predicado único `local_order_clause()` em `BACKEND/services/stock_history.py`: `coalesce(Order.shipping_mode,'') != 'full'`. NULL/'desconhecido' são tratados como LOCAL (só exclui o que é comprovadamente FULL).
- Aplicado no WHERE de: `_fetch_order_events_for_cmig_product`, `_fetch_direct_pg_order_events`, `_fetch_kit_component_events` (stock_history) e nas subqueries `kit_usage` + `direct_pg_order_qty` de `calculate_pg_product_stock` (stock_calculator).
- Semântica final: NF-e de transferência = única saída do galpão; pedido FULL = baixa só do FullStock (via `apply_full_order_shipped`).

### Backfill (Etapa 2)
- `POST /stock/recompute-all` reconstrói o estoque local correto a partir dos eventos já corrigidos.
- `POST /stock/cmig/{id}/sync-full` por CMIG realinha o FULL com a verdade do ML.

### Verificação
- `py_compile` OK; suíte `pytest -m "not integration"`: 10 passed. As 2 falhas em test_orders.py são pré-existentes (mock sem `.scalar()` em orders.py:479) e não relacionadas.

---

## 2026-06-05 — fix(users): grid mostra perfil de acesso atribuído, não só o papel

### Problema
- Na tela de Usuários, a coluna "Perfil" exibia sempre `roleLabel(u.role)` (papel: ac/ugo/...). Ao vincular um Perfil de Acesso (`profile_id`) via modal de edição, o grid continuava mostrando o papel antigo (ex.: Ianelli alterada para "Gestor Operacional" seguia aparecendo como "Gestor de Conta").

### Correção (`FRONTEND/src/views/settings/UsersView.vue`)
- Nova função `userProfile(u)` resolve `u.profile_id` na lista `profiles` já carregada (admin).
- Coluna "Perfil" passa a usar `profileLabel(u)` (label do perfil de acesso quando há um; senão, label do papel) e `profileBadge(u)` (cor pelo `base_role` do perfil ou pelo papel).
- Fallback para `roleLabel`/`roleBadge` preservado para usuários sem perfil atribuído e para visualizadores não-admin (que não carregam `profiles`).

---

## 2026-06-02 — feat(anuncios): pré-flight de status no ML antes de agrupar (+ sync DB)

**Contexto:** depois de remover a interpretação enganosa de cause 374, o erro real do ML chegou ao frontend: `{"cause":374,"message":"BODY_INVALID_FIELDS","error":"The field family name is invalid","status":400}`. Tecnicamente correto, mas críptico — o usuário não sabe que a causa é "anúncio fechado/deletado no ML".

**Mudança:** `create_variation_group` agora faz pré-flight via `ml_service.get_items_bulk` (1 chamada ao ML para até 20 anúncios) ANTES de tentar setar `family_name`. Se algum anúncio não está `active` no ML:

1. **Atualiza `listing.status` no DB** com o status real (closed/paused/etc.) — corrige o out-of-sync local.
2. **Retorna 422 `listings_not_active`** listando cada anúncio + status real, com mensagem clara e instrução "Remova-os da seleção ou republique".

Frontend (`CatalogVariationsFormView.vue`):
- Trata o novo `type: "listings_not_active"` exibindo a info-alert azul (não erro vermelho) com message + instruction + lista de anúncios.

**Efeito:** ao tentar agrupar os 6 anúncios MLB198238 (todos closed/deleted no ML), o usuário verá:
> 6 anúncio(s) não estão ativos no Mercado Livre e não podem ser agrupados. O status local foi atualizado para refletir o estado real do ML.
> Remova-os da seleção (ou republique se necessário) e tente novamente com apenas anúncios em status 'active'.
> #2906: MLB6889642226 está closed no ML
> #2907: MLB6889665386 está closed no ML
> ...

E o DB fica sincronizado de quebra.

---

## 2026-06-02 — fix(anuncios): remove interpretação enganosa de cause 374 no agrupamento

**Contexto:** ao tentar agrupar os 6 anúncios MLB198238 (Foam Roller), o backend respondia "A categoria usa variações tradicionais — não aceita agrupamento por family_name", o que está errado: diagnóstico via API ML revelou que MLB198238 É User Products, os 6 anúncios já estavam agrupados via `family_id=6875168885521809`, e o motivo real da falha era que todos estão `status=closed` + `sub_status=deleted` no ML (DB local out-of-sync) — não permitem mais alteração de `family_name`.

A mensagem enganosa vinha de duas heurísticas frágeis em `routers/anuncios.py`:

1. **`_validate_category_supports_family_name`** (pré-flight): assumia que categoria sem `catalog_domain` ⇒ "tradicional rejeita family_name". Não é verdade — sem testar não dá pra saber.
2. **Catch de `'"cause":374' in err_msg` no rollback de `create_variation_group`**: assumia que cause 374 do ML em `set_item_family_name` ⇒ "categoria tradicional". Mas cause 374 também acontece com item fechado/deletado, BRAND/MODEL divergentes, etc.

**Fix:**

- Removida a função `_validate_category_supports_family_name` e a chamada em `create_variation_group`.
- Removido o branch que reescrevia o erro do ML como `type: "category_not_supported"`.
- Agora os erros do ML por listing sobem direto para `ml_errors[]` e a UI mostra o motivo real (frontend já tem o tratamento via `groupErrorDetails`).

**Efeito:** quando o agrupamento falhar, o usuário vê o erro específico por anúncio (ex.: "available_quantity is not modifiable ... status:closed") em vez da mensagem genérica e errada sobre "categoria tradicional".

**Próximos passos sugeridos (não feitos aqui):**

- Sincronizar status dos 6 listings MLB198238 — DB diz `published` mas ML diz `closed/deleted` (impacta estoque/relatórios).
- Avaliar implementação de fluxo de publicação 1-a-1 para categorias User Products no wizard de variações.

---

## 2026-06-02 — revert(anuncios): heurística de requires_family_name volta ao original

**Contexto:** o fix anterior (commit `c97e54c`) afrouxou `requires_family_name` para excluir categorias com `attribute_types: "variations"` e atributos `allow_variations`. A teoria era que esses sinais indicavam suporte a variações tradicionais. **Validação em produção provou o contrário:** MLB198238 (Foam Roller) tem ambos os sinais, mas o ML rejeitou o POST `/items` com:
- cause 369: `body.required_fields` — exige `family_name`, `price` OU `available_quantity` no nível raiz
- cause 374: `The field variations is invalid with family name`

Conclusão: o único sinal confiável de User Products é `catalog_domain + has_catalog_required_attr`. Os outros campos da API ML são enganosos para essa classe de categoria.

**Fix:** restaurada a heurística original `requires_family_name = bool(catalog_domain) and has_catalog_required_attr`. Comentário ampliado documentando a armadilha para futuro.

**Efeito:** MLB198238 volta a ser bloqueado em "Criar com Variações" com o alerta "Esta categoria usa o modelo User Products". O fluxo correto é publicação 1-a-1 via `catalog_product_id` e depois agrupamento por `family_name` em "Agrupar anúncios existentes".

---

## 2026-06-02 — fix(catalog): EAN não aparecia ao selecionar produto PG no wizard de variações

**Problema:** ao adicionar variações em "Criar com Variações" e selecionar um produto PG, a coluna EAN ficava vazia mesmo o produto tendo EAN cadastrado no DB. `onProductSelected` em [CatalogVariationsFormView.vue:971](FRONTEND/src/views/catalog/CatalogVariationsFormView.vue#L971) lê `product.ean`, mas `GET /catalog` ([routers/catalog.py:48-69](BACKEND/routers/catalog.py#L48-L69)) não incluía esse campo na resposta — só CMIG (`/cmigs/{id}/products`) já retornava.

**Fix:** adicionados `ean` e `model` ao dict de cada item em `list_catalog` (campos já existem no modelo `CatalogProduct`). Mudança aditiva — não quebra os outros consumidores de `/catalog` (`AnunciosView`, `CatalogView`, `ManualOrderView`).

---

## 2026-06-02 — fix(anuncios): MLB198238 (e similares) deixavam de aceitar variações

**Problema:** ao tentar publicar anúncio com variações em MLB198238 (Foam Roller), os dois modos do wizard travavam com mensagens contraditórias — "Criar com Variações" alegava "categoria User Products" e "Agrupar anúncios existentes" alegava "categoria usa variações tradicionais". A categoria de fato aceita o array `variations` (atributo `attribute_types: "variations"` + `COLOR` com tag `allow_variations`), mas a heurística `requires_family_name = bool(catalog_domain) and has_catalog_required_attr` em `get_category_variation_support` ([routers/anuncios.py:3685](BACKEND/routers/anuncios.py#L3685)) marcava qualquer categoria com catálogo + atributos `catalog_required` como User Products only.

**Fix:** endurecer a detecção para só marcar `requires_family_name=true` quando NÃO houver sinais de variação tradicional:
```python
requires_family_name = (
    bool(catalog_domain)
    and has_catalog_required_attr
    and not supports_via_setting     # attribute_types != "variations"
    and not has_allow_variations_attr  # sem atributos com tag allow_variations
)
```
Reordenado o cálculo de `has_allow_variations_attr` e `supports_via_setting` para acima de `requires_family_name`.

**Efeito:** MLB198238 e categorias similares (catálogo presente mas variações tradicionais aceitas) voltam a permitir publicação via `POST /anuncios/publish-with-variations`. Categorias puramente User Products (sem `allow_variations` nem `attribute_types: variations`) continuam bloqueadas corretamente.

---

## 2026-06-01 — feat(stock): Fases 1 e 2 — SSOT + reserva FULL + snapshots diários

Ver [ADR-0004](docs/decisions/ADR-0004-stock-ssot-fases.md) para o panorama.

**Fase 1 — SSOT canônico e reserva FULL:**

Migração SQL:
- `Scripts SQL/81_full_stock_reserved.sql` — adiciona `reserved_qty` em `full_stock` (idempotente, captura ORA-01430).

Backend:
- `models/full_stock.py` — `FullStock.reserved_qty` + property `available_qty` = `max(0, qty − reserved_qty)`.
- `services/stock_view.py` (novo) — `get_stock_card()` retorna dict canônico (físico/reservado/disponível Local + FULL por conta); `load_full_per_account_map()` para batch sem N+1.
- `services/stock_reservation_service.py` — `reserve_stock`/`release_reservation` deixam de fazer `return` cedo no FULL: agora debitam `full_stock.reserved_qty` da conta ML do pedido e geram movement_type `full_reserve`/`full_unreserve` (field `full_stock_reserved`).
- `services/full_stock_service.py:apply_full_order_shipped` — ao debitar `qty` (shipped), também libera `reserved_qty` no mesmo movimento (`_adjust_full_stock(release_reserved=True)`).
- `routers/stock.py` — endpoint `GET /stock/card/{product_type}/{product_id}?account_id=` expõe SSOT pra UI.
- `routers/anuncios.py:_serialize_listing` — campos LIVE `full_stock_physical/reserved/available` em paralelo com `qty_full` legado; rota `GET /anuncios` pré-carrega `full_per_account_map` em batch e passa pro serializer.
- `routers/orders.py:_serialize_order_list` — `available_quantity` por item passa a usar `qty − reserved_qty` do FullStock (não mais snapshot).

Frontend:
- `AnunciosView.vue` — badge "X disp." prioriza `full_stock_available` (live) com fallback no cache `qty_full`. Tooltip Full ML mostra físico/reservado/disponível.

**Fase 2 — Trilha contábil + reconciliação diária:**

Migração SQL:
- `Scripts SQL/82_stock_snapshots.sql` — cria `stock_snapshots` com índice único por (snapshot_date, product_type, product_id) + índices por produto e CMIG (idempotente, captura ORA-00955).

Backend:
- `models/stock_snapshot.py` (novo) — modelo da trilha histórica.
- `tasks/daily_stock_reconcile.py` (novo) — job APScheduler: (a) `recompute_reservations_from_movements` (reconciliação rápida) e (b) UPSERT em `stock_snapshots` para cada produto com saldo não-zero.
- `tasks/scheduler.py` — registra `daily_stock_reconcile` no cron 02:30 UTC (~23:30 BRT).
- `routers/stock.py` — endpoint `GET /stock/snapshots` com filtros por produto/CMIG/janela.

**Fase 2.4 (Custo Médio Ponderado) — em standby.**
Documentado em ADR-0004 como decisão contábil que precisa de alinhamento com contador antes de implementar (escolher entre Médio Ponderado, PEPS, UEPS; reprocessar histórico; coexistir com `cost_price` opt-in por CMIG).

**Verificações:**
- `ast.parse` em 10 arquivos Python: OK.
- Import test (`stock_view`, `daily_stock_reconcile`, `FullStock.reserved_qty`, `StockSnapshot`): OK.
- `npm run build`: OK (24s).
- `pytest tests/ -m "not integration"`: 10 passed; 2 falhas pré-existentes em `test_orders.py` (mocks incompletos no conftest, idênticas antes/depois — confirmado via `git stash`).

---

## 2026-06-01 — fix(stock): contagem FULL somava listings duplicados que compartilham pool no ML

**Sintoma:** Após `/sync-full`, a contagem da coluna FULL estava inflada — somava o `available_quantity` de cada anúncio. Quando N MLBs apontam pro mesmo produto via catálogo/family/optin (mesmo `user_product_id`), eles compartilham UM pool de estoque no galpão do ML, mas estávamos somando N vezes.

**Fix em `BACKEND/routers/stock.py:sync_full_stock_for_cmig`:**
- `services/ml_service.py:get_items_bulk`: passou a incluir `user_product_id` nos attributes.
- Substituído `agg[key] += available_qty` por dedupe via `seen_pools[(ptype, pid, pool_key)] = qty`, onde `pool_key = "UP:{user_product_id}"` quando existe ou `"MLB:{platform_item_id}"` caso contrário.
- Listings com o mesmo `user_product_id` somam **uma única vez** ao `full_stock`; anúncios não-catálogo (sem `user_product_id`) continuam como pools independentes (correto — cada MLB é um pool próprio).
- Resposta agora retorna `unique_pools` e `duplicate_listings` para diagnóstico.
- Frontend: toast agora mostra "N pool(s) de estoque distintos" e quantos anúncios compartilham pool.

---

## 2026-06-01 — fix(stock): Fase 0 — disponível LIVE em Anúncios e Pedidos (não mais snapshot)

**Sintoma:**
- Card de Anúncio mostrava "Local: 13 un." e "13 disp." para produto com 4 disponíveis reais (resto reservado).
- Card de pedido mostrava "X disponíveis após esta venda" estático, não atualizando após vendas FULL.

**Causa raiz:** `ProductListing.qty_local`, `qty_full` e `available_quantity` são snapshots gravados no último sync ML — não refletem estoque atual. UI lia direto deles.

**Backend (`anuncios.py:_serialize_listing`):**
- Adicionados 3 campos calculados live a partir do produto vinculado (`cmig_product` ou `catalog_product`):
  - `local_stock_physical` = `stock_quantity`
  - `local_stock_reserved` = `reserved_quantity`
  - `local_stock_available` = `max(0, físico − reservado)`
- `qty_full`/`qty_local`/`product_stock` mantidos por compat (deprecados na UI).

**Backend (`orders.py`):**
- Pré-carrega `local_stock_map[(product_type, product_id)]` em batch (`stock_quantity`, `reserved_quantity` de CatalogProduct/CMIGProduct vinculados aos listings dos itens).
- Pré-carrega `full_stock_map[(product_type, product_id, account_id)]` em batch da tabela `full_stock`.
- `_serialize_order_list` agora calcula `available_quantity` live por item:
  - FULL → `FullStock.qty` da conta ML do pedido.
  - Local → `max(0, stock - reserved)` do produto vinculado.
  - Fallback para snapshot do listing apenas se sem vínculo de produto.
- Novos campos no payload do item: `available_local`, `available_full`.

**Frontend (`AnunciosView.vue`):**
- Badge "X disp." passa a usar `qty_full` (FULL) ou `local_stock_available` (live, local).
- Badges "Galpão" / "Local" mostram `X físico (Y disp.)` com tooltip detalhando físico/reservado/disp.
- `qty_local` e `available_quantity` snapshots não são mais lidos.

**Frontend (`OrderListView.vue`):**
- "X disponíveis após esta venda" → "X disp. no Full" ou "X disp. no galpão", com tooltip explicando a fonte do cálculo.

**Limitação consciente (tratada em Fase 1):**
- FULL ainda não tem conceito de reservado — após uma venda FULL ser baixada e antes do shipping confirmar, `FullStock.qty` ainda mostra o saldo pré-venda. Fase 1 adicionará `FullStock.reserved_qty` + movement_types `full_reserve`/`full_unreserve` para resolver isso.

---

## 2026-06-01 — fix(stock): listar produtos que só têm estoque FULL (sem unidade local)

**Sintoma:** Após `/sync-full` gravar 4 linhas em `full_stock` para uma CMIG, a tabela de Controle de Estoque continuava vazia.

**Causa raiz:** `/stock/summary` filtrava apenas produtos com `stock_quantity/reserved/awaiting_return/pending_validation/unfit > 0` (estoque local). Produtos vendidos exclusivamente via Full (sem unidades no galpão) não passavam pelo WHERE — então mesmo com `full_stock.qty > 0`, eles eram filtrados ANTES do passo de agregação que preenche a coluna FULL.

**Fix em `BACKEND/routers/stock.py:stock_summary`:**
- Pré-computa `full_pg_ids` / `full_cmig_ids` (sets de IDs com `FullStock.qty > 0`) escopados por `account.cmig_id` (respeita `cmig_id`/`ac_cmig_ids`).
- WHERE de PG/CMIG agora aceita `(filtro_local) OR id IN (ids_com_full)`.
- Agregação de `full_rows` também passou a respeitar o escopo (`marketplace_account_id IN scoped_accts`) para não vazar FULL de outras CMIGs.

---

## 2026-06-01 — feat(stock): botão "Atualizar Estoque FULL" para AC na tela de Controle de Estoque

**Pedido:** Na tela de Controle de Estoque, no acesso AC, ter um botão que atualize o estoque do FULL da CMIG selecionada lendo do Mercado Livre.

**Backend (`BACKEND/routers/stock.py`):**
- Novo endpoint `POST /stock/cmig/{cmig_id}/sync-full`.
- RBAC: AC só pode chamar para CMIGs em que é administrador; UGO/admin/GO liberados.
- Para cada `MarketplaceAccount` ML ativa da CMIG, pega listings publicados com `logistic_type='fulfillment'` ou `is_full=true`, faz refresh do token quando necessário, busca em lote em `/items` via `ml_service.get_items_bulk`.
- Zera `full_stock.qty` das contas da CMIG antes de reconstruir (evita resíduo de anúncios despublicados).
- Atualiza `listing.qty_full` com `available_quantity` do ML e agrega em `full_stock` por (`product_type`, `product_id`, `account_id`).
- Retorna `{cmig_id, accounts_processed, accounts_skipped, listings_synced, listings_errors, errors[]}`.

**Frontend (`views/stock/StockControlView.vue`):**
- Botão "Atualizar Estoque FULL" (amarelo, ícone `fa-cloud-download-alt`) aparece apenas quando há CMIG selecionada.
- Chama o endpoint, mostra spinner durante a chamada, exibe toast com resumo e recarrega a lista. Erros logam no console e disparam toast de aviso.

---

## 2026-06-01 — feat(stock): seletor de Galpão/CMIG, colunas SKU/EAN e ordenação no Controle de Estoque

**Pedido:** Na tela de Controle de Estoque, permitir filtrar por Galpão (produtos PG) ou Conta CMIG, exibir SKU e EAN dos produtos, ordenar por SKU, Nome, Físico ou Disponível. AC só pode ver suas CMIGs.

**Backend (`BACKEND/routers/stock.py`):**
- `/stock/summary` agora aceita `scope` (`pg|cmig`), `warehouse_id`, `cmig_id`, `sort_by` (`sku|name|physical|available`) e `sort_dir` (`asc|desc`).
- Resposta inclui `sku`, `ean`, `warehouse_id`, `cmig_id` por item. Para CMIG, `sku` = `sku_cmig` e `warehouse_id` vem do join com `cmigs`.
- Busca expandida para casar título, SKU e EAN.
- RBAC: AC entra com `scope="cmig"` forçado e filtro `cmig_administrators.user_id = current_user.id`. Tentar `cmig_id` fora do escopo → 403; sem CMIGs administradas → lista vazia.
- `/stock/{type}/{id}/movements` liberado para AC com check de scope (somente CMIGs administradas).

**Frontend:**
- `views/stock/StockControlView.vue`: botões de scope (Todos / Galpão (PG) / CMIG), dropdowns de Galpão (`/warehouse`) e CMIG (`/cmigs`), colunas SKU e EAN, headers clicáveis em SKU/Produto/Físico/Disponível com indicador asc/desc. AC vê apenas o dropdown de CMIG (sem botão de scope nem Galpão).
- `router/index.js`: rota `/estoque` agora aceita `role: ['ugo', 'ac']`.
- `components/common/AppSidebar.vue`: item "Controle de Estoque" adicionado também na seção do AC.

---

## 2026-06-01 — fix(orders): exclusão de pedido falhava com 500 (FK Oracle não cascateava)

**Pedido:** Excluir pedidos manuais 541 e 542 retornava `500 Internal Server Error`.

**Causa raiz:** `_delete_order` em `routers/orders.py` só limpava `webhook_events` e chamava `db.delete(order)`. A cascade ORM `cascade="all, delete-orphan"` no `Order.items` não é confiável no `AsyncSyncSession` (não eager-load), e várias FKs apontam pra `orders` sem `ON DELETE CASCADE` no Oracle: `order_items.order_id`, `stock_movements.order_id`, `invoices.order_id`, `returns.order_id`.

**Fix em `BACKEND/routers/orders.py:_delete_order`:**
- DELETE explícito em `order_items` e `stock_movements`.
- UPDATE setando `invoices.order_id = NULL` e `returns.order_id = NULL` (preserva NF-e e devolução, só desconecta).
- DELETE explícito do `Order` via SQL (evita ORM cascade).
- `WebhookEvents` só é limpo quando `platform_order_id` existe (skip para pedidos manuais).

Cobre tanto `DELETE /orders/{id}` quanto `POST /orders/bulk-delete` (ambos usam `_delete_order`).

---

## 2026-05-30 — feat(catalog): Fase 2 — agrupar anúncios existentes por family_name (User Products)

**Pedido:** Para categorias User Products (que rejeitam o campo `variations` no POST /items), implementar o caminho oficial do ML: publicar cada cor/tamanho como anúncio individual normal e depois **agrupar** N anúncios pela mesma `family_name`. O ML renderiza eles como variações (pickers) na VIP. Refatoração validada com a doc oficial (https://global-selling.mercadolibre.com/devsite/variations-global-selling).

**SQL (`Scripts SQL/78_listings_variation_groups.sql`):**
- `ALTER TABLE product_listings ADD variation_group_id VARCHAR2(36)` (UUID local).
- `ALTER TABLE product_listings ADD family_name_ml VARCHAR2(200)` (valor enviado ao ML).
- Index `ix_listings_variation_group`. Migrations idempotentes via `DECLARE ... EXCEPTION`.

**Backend:**
- `models/product.py` — `ProductListing.variation_group_id` e `.family_name_ml`.
- `services/ml_service.py:set_item_family_name(token, item_id, family_name)` — PUT `/items/{id}` setando ou limpando (`None` desagrupa).
- `routers/anuncios.py` — 6 endpoints novos:
  - `POST   /anuncios/groups` — cria grupo a partir de `[listing_ids]`, valida (mesma conta, mesma categoria, mín 2 listings, sem listings já agrupados), gera UUID, calcula `family_name` automático ou usa o informado, aplica PUT em cada item ML (com rollback se falhar no meio).
  - `GET    /anuncios/groups?account_id=X` — lista grupos da conta.
  - `GET    /anuncios/groups/{group_id}` — detalhes do grupo.
  - `POST   /anuncios/groups/{id}/add` — adiciona listing ao grupo (revalida compat).
  - `POST   /anuncios/groups/{id}/remove` — remove listing do grupo; se sobrar só 1 listing, desagrupa todo o grupo (grupo de 1 = ruído).
  - `DELETE /anuncios/groups/{id}` — desagrupa todos (limpa `family_name` no ML).
- `_serialize_listing` expõe `variation_group_id`, `family_name_ml`, `is_variation_grouped`.

**Frontend (`CatalogVariationsFormView.vue`):**
- Novo toggle "Como quer publicar?" com 2 cards: **Criar com variações** (categorias tradicionais — fluxo atual) e **Agrupar anúncios existentes** (User Products — fluxo novo).
- Modo agrupar:
  - Seção 1: seleciona conta ML.
  - Seção 2: tabela de anúncios selecionados + botão "Adicionar anúncio" que abre modal com filtro por título/MLB, lista todos os anúncios `status=published` da conta, oculta os já selecionados ou já agrupados.
  - Seção 3: input de `family_name` (placeholder com sugestão automática derivada do prefixo comum dos títulos) + validações em tempo real (mesma categoria, mín 2 listings).
  - Botão "Criar grupo de variações" → `POST /anuncios/groups`.
- `AnunciosView.vue` — badge verde "🟢 Variação" quando `a.is_variation_grouped`, tooltip mostra `family_name` ou `variation_group_id`.

**Decisão arquitetural:**
A abordagem original da Fase 1 (criar 1 anúncio com array `variations`) continua funcionando para categorias **não** User Products. A nova Fase 2 cobre o restante (maioria das categorias modernas do ML) com fluxo nativo do modelo Pendings User Products. Trade-off explícito ao usuário: precisa publicar cada cor individualmente primeiro, depois agrupar. Em troca: chamadas ao ML 3× menores, sem risco de UserProductRepeatedError, sync de estoque já funciona (cada anúncio é independente), reversibilidade trivial (`family_name=null`).

---

## 2026-05-30 — fix(catalog): detectar categorias User Products que rejeitam variações via POST /items

**Pedido:** Ao publicar anúncio com variações na categoria MLB123037 (Bolas de Pilates), o ML retornou:
```
"The field variations is invalid with family name"
"The body does not contains some or none of the following properties [family_name, price, available_quantity]"
```

**Diagnóstico:** A categoria está sob o modelo **User Products** do ML (`settings.catalog_domain = MLB-PILATES_BALLS` + atributos BRAND/MODEL com tag `catalog_required`). Nesse modelo:
- O ML exige `family_name` no item-pai (não `title`)
- Variações **não podem** ser enviadas via `POST /items` — só via API de catálogo (`catalog_product_id`)
- Esta limitação é documentada pelo próprio ML mas não estava sendo detectada

**Fix (`BACKEND/routers/anuncios.py:get_category_variation_support`):**
- Detecta categoria sob User Products: `settings.catalog_domain != null` E pelo menos um atributo com tag `catalog_required`.
- Quando detectado, `supports_variations = false` + novos campos na resposta: `requires_family_name: true`, `catalog_domain: "..."`, `block_reason: "..."`.

**Fix (`FRONTEND/src/views/catalog/CatalogVariationsFormView.vue`):**
- Mensagem vermelha específica para categorias User Products explicando o motivo do bloqueio e direcionando o usuário para a publicação padrão do Catálogo.

**Consequência:** A feature de Anúncios com Variações fica limitada às categorias que **ainda não migraram** para User Products. Categorias modernas do ML (a maioria) estão sob esse modelo e só aceitam variações via fluxo de catálogo (`catalog_product_id`) — fora do escopo desta feature na fase 1.

---

## 2026-05-30 — fix(fiscal): NFe entrada CMIG sem recalcular estoque + excluir finalized + bug catalog_product_id

**Pedido:** (1) Entrada manual com produtos CMIG não atualizava estoque automaticamente e não aparecia opção de "recalcular estoque". (2) Permitir excluir NFe não-transmitida à SEFAZ revertendo estoque (para PG e CMIG).

**Diagnóstico:**
- Botão "Reaplicar estoque PG" (`InvoiceDetailView.vue`) tinha `v-if="hasPgItems"` — não aparecia para NFes com itens apenas CMIG. O backend `reapply-stock` já cobria CMIG E PG via `recompute_after_invoice_change`, mas a UI estava enganosa.
- Resposta do backend usa `cmig_recomputed`/`pg_recomputed`, mas o frontend lia `matched_pg`/`unmatched` — toast sempre mostrava "nenhum item PG nesta nota" mesmo em sucesso.
- `delete_invoice` aceitava só `status='draft'`. NFe `finalized` (sem SEFAZ) não podia ser excluída.
- **Bug colateral**: `InvoiceFormView.vue` não passava `catalog_product_id` no payload do item (mesmo o `selectProduct` setando) — itens PG ficavam sem o FK e o `affected_products_from_invoice` precisava cair em fallback de SKU/EAN.

**Backend (`BACKEND/routers/invoices.py:delete_invoice`):**
- Permite excluir `draft` (sem efeito colateral) e `finalized` (reverte estoque).
- Para `finalized` + `direction='in'`: captura `affected_products_from_invoice` ANTES do `db.delete()`, depois roda `recompute_cmig_product_stock` e `recompute_pg_product_stock` em cada produto — o replay event-sourced para de enxergar os eventos da NFe deletada e zera/reverte o cache de `stock_quantity`.
- `authorized` e demais status continuam bloqueados (precisam cancelar via SEFAZ).

**Frontend (`InvoiceDetailView.vue`):**
- Botão "Reaplicar estoque PG" → renomeado para **"Recalcular Estoque"**, sem condição de origem (sempre aparece em `finalized`/`authorized`). Toast agora usa `cmig_recomputed`/`pg_recomputed`.
- `canDelete` cobre `draft` + `finalized`. Label dinâmico ("Excluir Rascunho" / "Excluir NFe"). Modal de confirmação avisa que o estoque será revertido em entradas finalized.

**Frontend (`InvoiceFormView.vue` — bug-fix):**
- `itemForm` reativo agora tem `catalog_product_id: null` no estado inicial.
- `openItemModal` carrega `catalog_product_id` ao editar.
- `saveItem` envia `catalog_product_id` no payload — garante que itens PG persistem o FK e o recompute encontra o produto sem fallback.

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

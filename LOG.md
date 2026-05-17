# LOG de alterações — Sistema Drop

> Resumo cronológico das alterações feitas via Claude. Mais recente no topo.

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

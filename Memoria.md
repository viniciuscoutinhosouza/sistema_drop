# Memória de Trabalho — Sistema Drop

> Registro de continuidade entre os locais de trabalho do dono (**CASA**, **ESCOL**, **NOTEBOOK**).
> Mantém apenas os **últimos 5 dias** de trabalho. Cada tarefa concluída vira uma entrada com local, data/hora e o resumo entregue.
> **Entrada mais recente no topo** — ao baixar o projeto do GitHub, a Claude apresenta a primeira entrada abaixo.

---

## 2026-11-08 — CASA — Integração Bling (ERP) por CMIG via OAuth2 — Fase 1 (conexão) — ✅ EM PRODUÇÃO (commits `32477b0` + `1270923`)

**Pedido do dono:** criar uma SKILL sobre a API do Bling + planejar e implementar a **conexão da Conta
CMIG com o Bling**. Depois: tornar o **Client ID/Secret configuráveis na integração da conta**.

**Entregue (EM PRODUÇÃO):**
- **Skill `bling-api`** (`.claude/skills/bling-api/`) + `DOCs/integracao-bling-registro-app.md` (passo a
  passo do dono registrar o app). Itens não validados ao vivo marcados `[confirmar]`.
- **Conexão OAuth2 POR CMIG** (ADR-0040, não `MarketplaceAccount` — molde Google Drive ADR-0038):
  tabela `cmig_bling_accounts` (tokens cifrados Fernet, UNIQUE cmig_id, UPSERT na reconexão),
  `services/bling_service.py` (authorize/exchange/get_valid_token com refresh sob lock por-CMIG;
  state CIFRADO anti-IDOR), `routers/bling.py` (`/api/v1/cmigs/{cmig_id}/bling` autenticado + callback
  público). Permissão `bling_gerenciar` (ac/admin) AND `assert_cmig_access`. Card `CmigBlingConfigCard`
  no CmigDetailView. Migrations 179 (tabela) + 180 (permissão).
- **Credenciais do app configuráveis POR CMIG** (migration 181): `client_id` + `client_secret_enc`
  (cifrado) editáveis no card; `PATCH /credentials`; `.env` (`BLING_CLIENT_ID/SECRET`) = app PADRÃO
  fallback. Secret nunca retorna; vazio = manter.
- Trio de auditoria 2x (feature + delta): 0 CRÍTICO; 2 HIGH da 1ª rodada corrigidos (html.escape no
  callback + refresh do 401 sob lock). `pytest` 401 ok (2 pré-existentes) + 12 testes Bling; build OK.
- **Deploy verificado em produção** (`1270923`): migrations 179/180/181 aplicadas, tabela+colunas no
  Oracle, 5 rotas+callback no OpenAPI, `/docs` 200, domínio 200, `.env` com 3 chaves. App padrão do
  dono (client_id `258cbbf…`) já no `.env`.

**Pendente do dono (só ele faz — OAuth real não é testável no DEV):** em **Administração ▸ Integrações**,
na conta **Bling**, botão **"Integração Bling (ERP)"** → (opcional) ajustar Client ID/Secret → **Conectar**
→ autorizar no Bling → ver "Conectado". (A UI foi MOVIDA do card da CMIG para Integrações a pedido do dono
em 08/11 — commit da emenda a confirmar; backend por-CMIG intocado.) Se não habilitar p/ perfil não-admin,
habilitar `bling_gerenciar` no Perfil de Acesso.
**Fase 2 (importar categorias/produtos/kits → CMIG ou PG) ✅ EM PRODUÇÃO 08/11 (commit `f3f4859`)**
(migrations 182/183 aplicadas, `bling_import_service` + job assíncrono + `CmigBlingImport.vue` no card
Bling; upsert pular/atualizar; imagens baixadas anti-SSRF; estoque NÃO importado — zera só no create;
kit→componentes destino CMIG; guard product_mode; dedup escopado por galpão). Trio: quality-guardian
pegou 3 CRÍTICOS (coluna `catalog_products.bling_product_id` que NÃO existia — pré-auditoria errou — +
estoque zerado no update) + 2 ALTOS (escopo PG, SSRF) — todos corrigidos e re-verificados.
**Estoque (09/11):** toggle "Importar estoque" (opt-in) cria um **inventário baseline** finalizado que
reseta o saldo = qtd Bling (SSOT-correto, `services/inventory_service.import_stock_baseline`; kits fora).
**Fix 429 (09/11):** throttle do `bling_service` estava no limite exato (3/s) → import falhava em tudo;
ajustado p/ ~2,2 req/s + backoff. **Pendente do dono:** exercitar a importação REAL pela tela
(Administração ▸ Integrações → conta Bling → Importar catálogo). **Follow-ups:** variações entram flat (agrupar pai+variantes); seletor por produto/
categoria (backend pronto, UI só "importar tudo"); kit no destino PG.

---

## 2026-11-07 — ESCOL — Fix: recuperação do 539 vinculava nota de OUTRO mês (incidente nº 10) — ✅ EM PRODUÇÃO (commit `34b5afe`)

**Pedido do dono:** a nota 8909 (pedido 14302) foi emitida pelo sistema mas aparece com "Rejeição 539
Duplicidade"; e notas próprias precisam ser reportadas ao ML/Shopee. Investigar + plano.

**Diagnóstico (produção):** a 8909 está "autorizada" na tela, MAS os logs mostram que ela foi
**mal-vinculada à chave de uma nota de AGOSTO**. Sequência: a 8909 transmitiu o nº 10 em novembro
(chave AAMM 2611, cNF 44744381) → SEFAZ rejeitou com **539** porque o nº 10 já fora autorizado em
**agosto** (chave AAMM 2608, cNF 16968356, dhRecbto 10/08 — outra venda) → a recuperação do 539
vinculou a 8909 à chave de agosto. **Causa-raiz (bug):** `_mesma_identidade_fiscal` comparava
`c_uf/cnpj/modelo/serie/n_nf` mas **NÃO o AAMM** → nº 10 de agosto passou como "a mesma nota" do nº 10
de novembro. Consequência: o pedido 14302 **não tem nota própria válida** (a dele foi rejeitada); a
#6638 (nº 9, chave de agosto, emissão de out) provavelmente tem o mesmo defeito. Contador da série 3
dessincronizado (agosto consumiu números que o contador reusou). **Confirmei a Distribuição DFe NÃO
recupera XML próprio (cStat 641 "indisponível para o emitente")** — então `recuperar_xml_por_chave`
não serve p/ nota própria.

**Fix item 1 (EM PRODUÇÃO — commit `34b5afe`, só backend, sem migration):** incluído o **AAMM** na
identidade de `_mesma_identidade_fiscal`. 539 de mês diferente agora é **recusado** (nota→`rejected`,
operador reemite) em vez de vincular à nota errada. Teste de regressão novo (suíte fiscal 8 passed no
servidor). Backend restart health 200. **NÃO enviei a chave de agosto ao ML** (seria reportar a venda
errada) — parei a tempo.

**Remediação feita (dados):** 8909 resetada (`authorized`→`rejected`, chave de agosto removida); pedido
14302 com `nfe_status`/`nfe_key` limpos; **baixa fantasma de estoque revertida** (a falsa autorização
tinha `stock_updated=True`; recomputado → PG 342 = 21, correto).

**Descoberta decisiva (07/11):** a **série 3 do CNPJ da MIG (000275) está consumida na SEFAZ até 51+**
por um emissor FORA do sistema (outro sistema MIG — Bling/ERP?). Testado ao vivo: reemissão deu **539
em TODOS** os números 11–51 (10 tentativas). O fix funcionou perfeito (todos viraram `rejected` limpo,
zero mal-vínculo). A única nota série 3 REAL do sistema é a **nº 1** (jul); 8/9/10 eram mal-vínculos.
A CMIG 161 (série 3 até 415840) é **outro cliente** (Pegoraro/Harmony, CNPJ diferente, notas de entrada)
— sem relação. **Conclusão: série 3 é inviável p/ emissão própria da MIG.**

**Decisão do dono (07/11):** NÃO usar a emissão própria do sistema p/ o 14302 — **vai emitir no
ML/Shopee**. Parei antes de testar série dedicada (100/900). Config fiscal deixada em série 3 / next 52
(emissão própria abandonada por ora).

**Follow-ups:** (a) se algum dia quiser o sistema emitindo NF-e própria da MIG, **definir uma série
dedicada** (a 3 está morta — confirmar uma livre com a contabilidade); (b) #6638 (nº 9) é outro
mal-vínculo (sem pedido) — resetar quando for tratar; (c) estrutural: emissão própria **salvar o XML**
(a recuperação por consulta não salvava → Distribuição DFe dá 641 p/ nota própria) e **reportar ML/Shopee**
como passo visível/re-tentável (hoje a tela Fiscal não reporta ao ML).

---

## 2026-11-06 — CASA — Fix: NF-e quebrava ao emitir (bairro do ML vinha como objeto) — ✅ EM PRODUÇÃO (commit `600ae1f`)

**Pedido do dono:** a venda ML `2000019354389432` dava erro ao emitir a NF-e — identificar e corrigir.

**Diagnóstico (produção):** NÃO era mais o CPF (o fix `5ed146a` resolveu — o documento resolve certo
via billing_info). O fluxo passava do gate do CPF e quebrava no INSERT do cliente com
`DPY-3002: Python value of type "dict" is not supported`: o ML devolve `neighborhood`/`city`/`state`
como objeto `{id,name}` e o **bairro** (`neighborhood`) ia cru para a coluna String `people.neighborhood`.
`city`/`state` já eram desembrulhados na mesma função; o `neighborhood` ficou de fora. Afetava todo
pedido ML novo cujo comprador ainda não existia como `Person`. Bug EXPOSTO pelo `5ed146a` (que destravou
o gate), não causado por ele.

**Fix (EM PRODUÇÃO — commit `600ae1f`, só backend, sem migration):** criado `services/address_parser.py`
como **ponto único** (`parse_buyer_address`/`addr_text`) que desembrulha `{id,name}`, trata dict legado
serializado, normaliza UF (`BR-SP`→`SP`; falha alto em UF inválida) e sempre devolve `str`. A emissão de
NF-e (`invoices._upsert_customer_from_order`) e a **etiqueta** (`label_service._format_address` — tinha o
MESMO defeito, imprimia o objeto no papel) passam a usar o helper. eShip/content_declaration já tratavam;
o XML da NF-e lê das colunas da Person → conserta por consequência.

**Auditoria:** consistency-auditor (achou e mandou incluir a etiqueta no fix) + quality-guardian
(0 crítico/alto, LGPD/segurança OK). Suíte 391 ok (2 pré-existentes) + 7 testes novos. **Verificado em
produção:** HEAD do servidor `600ae1f`, backend online sem ImportError, `/docs` 200, domínio 200, e o
pedido 14302 reproduzido no venv de produção → cliente montado (customer id=4825, UF=PR) em vez do
DPY-3002.

**Pendente do dono:** emitir a NF-e desse pedido (14302 / `2000019354389432`) pela tela — agora deve sair.
Se falhar, aí é na transmissão SEFAZ (não testável sem emitir de verdade) — me mandar a mensagem exata.

---

## 2026-11-06 — ESCOL — Fix: NF-e não emitia "sem CPF/CNPJ" (ML não devolve mais o doc no GET /orders) — ✅ EM PRODUÇÃO (commit `5ed146a`)

**Pedido do dono:** 2 vendas ML (14035 Maria Angela SP→MT; 14304 Dhaniel CNPJ) não emitiam NF-e pelo
sistema — investigar e corrigir.

**Diagnóstico (produção):** o 14035 estava com `buyer_document` NULL → `create_invoice_from_order` ⇒
`_upsert_customer_from_order` retorna None ⇒ 400 "Pedido sem CPF/CNPJ do comprador". MAS o comprador
TEM CPF (96***04) — ele vive no `GET /orders/{id}/billing_info` do ML (o `GET /orders` **não devolve
mais** o documento, privacidade). O eShip já busca isso via `ensure_buyer_document`; **a emissão de
NF-e NÃO buscava** — lia `order.buyer_document` direto. Por isso pedido já enviado ao WMS (doc
preenchido pelo eShip) emitia, e pedido ainda não enviado (ex.: 14035, `downloaded`) falhava. O 14304
já tinha o doc (foi enviado ao eShip → `shipped`) e no meu teste o rascunho+prévia montam OK — era só
reemitir.

**Fix (EM PRODUÇÃO — commit `5ed146a`, só backend, sem migration):** reusa o ponto único
`ensure_buyer_document(db, order)` (platform-aware: ML→billing_info, Shopee→fonte própria, manual→no-op)
no início de `create_invoice_from_order`, antes de montar a nota — best-effort com `logger.warning`.
Descartada a ideia inicial de "consumidor não identificado" (o CPF existe; seria mudança fiscal
desnecessária e arriscada — o consistency-auditor apontou 3 CRÍTICOS contra ela).

**Auditoria (trio):** quality-guardian 0 CRÍTICO/ALTO (1 MÉDIO do log incorporado); adr-checker CONFORME
(regra de ouro ADR-0020 intacta — ramo por plataforma dentro do helper); consistency-auditor sem lacuna
de paridade (todos os caminhos de emissão própria convergem em `create_invoice_from_order`; Faturador ML/
DC-e/upload Shopee não montam destinatário → não precisam). **Verificado em produção:** 14035
`buyer_document` NULL→96***04, rascunho+prévia do XML montam OK; backend restart health 200, startup
sem erro, código deployado confere.

**Pendente do dono:** reemitir os 2 pedidos pela tela (agora deve sair). Se o 14304 ainda falhar, é na
TRANSMISSÃO SEFAZ (não testável sem emitir de verdade) — me mandar a mensagem exata. Follow-up BAIXO:
`webhook_service.py:597` ainda grava `buyer_document` da fonte que o ML aposentou (já compensado pelo fix).

---

## 2026-11-05 — CASA — Conta de marketplace DESATIVADA some de todo local operacional — ✅ EM PRODUÇÃO (commit `8bbb18c`)

**Pedido do dono:** conta desativada (`is_active=False`) não deve mais aparecer em NENHUM ponto
operacional (dropdowns, filtros, listas, estoque). "Sempre manter escondido, em todos os pontos."

**Diagnóstico (varredura back+front):** o front NÃO tem store central de contas — ~13 telas chamam
`GET /accounts` cada uma por si. O vazamento principal era UM só: `list_accounts` filtrava `is_deleted`
mas não `is_active`. Jobs de sync e webhooks JÁ filtravam `is_active`.

**Entregue:**
- **Central** `routers/integrations.py::list_accounts`: param `include_inactive_account` (default False);
  `_visible` esconde `is_active=False` por padrão → corrige os ~13 dropdowns de uma vez.
- **Exibição secundária** (`is_active==True`): `atendimento_access.py` (ramo AC), `listings.py`
  `list_listings` (NÃO o guard de mutação), `stock.py`+`stock_view.load_full_per_account_map(active_only=True)`
  (Controle de Estoque — opção B: esconde FULL da conta desativada da LEITURA; saldo fica no banco).
- **Gestão vê tudo** (reativar/config): `IntegrationsView`, `CmigDetailView`, `FullCnpjsView` mandam
  `include_inactive_account:true`.
- **NÃO tocado** (contábil/histórico): DRE (filtrar subestimaria receita), captura de NF-e histórica,
  recompute FULL, lookups por id, guards de mutação, jobs/webhooks.

**Auditoria (quality+consistency):** 1 ALTO corrigido (2ª leitura de FULL na visão principal ainda
mostrava); DRE mantida íntegra. pytest 385 ok (2 pré-existentes); build front OK.

**Deploy 2026-11-05 (commit `8bbb18c`, sem migration):** FF `d1f78b7..8bbb18c`; build OK (`index-17ffd122.js`);
PM2 restart; `/docs` 200; `include_inactive_account` no OpenAPI; startup sem ImportError; domínio 200.
Regra gravada na memória (todo seletor de contas novo nasce filtrando `is_active`). **Consequência a
lembrar:** pausar anúncio / responder claim aberto de conta recém-desativada exige reativá-la.

---

## 2026-11-05 — CASA — Shopee na Separação/Carrinho Gaiola (ADR-0005/0020 emendadas) — ✅ EM PRODUÇÃO (commit `d1f78b7`)

**Pedido do dono:** "Em Separar Pedidos, preciso ver os pedidos da SHOPEE que precisam ser separados" —
e escolheu o **fluxo completo** (não só ver): separar + despachar + etiqueta + NF-e, dentro da tela.

**Contexto:** a Separação era só-ML de propósito (ADR-0005/0020: "picking é só ML; Shopee tem logística
própria"). Mudança estrutural (nível Full) revertendo essa decisão, por pedido do dono.

**Entregue (regra de ouro ADR-0020 intacta — tudo por ramo/rota/função nova):**
- **Novo `services/shopee_dispatch.py`** (ponto único, user-agnóstico, não importa routers): gate NF-e
  validada → `ship_order` (idempotente) → etiqueta. `shopee_logistics.py` passou a **delegar** (fim das
  cópias do miolo).
- **`separation.py`**: classificador único `_order_bucket` (ml/shopee/manual); Shopee entra na
  elegibilidade; rota `GET /carts/{id}/orders/{oid}/shopee-label` (gerar etiqueta = **DESPACHA** na
  Shopee; 202 se gerando); `cart_emit_nfe` ramo Shopee (emite própria SEFAZ + **anexa automático na
  Shopee** — o dono escolheu "upload automático"; probe anti-duplicata p/ loja Invoice Issuer; claim
  atômico anti-duplo-clique); `_bundle_ensure_nfe`+`bundle.zip` ramo Shopee; `deliver_cart` Shopee (ship
  antes de shipped; **NÃO** chama `confirm_dispatch` p/ Shopee — estoque event-sourced; `failed_ship` não
  derruba o lote; gaiola só `delivered` se sem falha); guards anti-remover/cancelar Shopee já despachado.
- **Front**: `printShopeeLabel` (202/PDF/ZPL), ramos Shopee em etiqueta/NF-e/DANFE, botão NF-e liberado
  **antes** da etiqueta (ordem Shopee invertida), `CartsListView` surfacea `failed_ship` (falha-alto),
  HelpModal atualizado.

**Ordem do operador (Shopee):** bipar → **Emitir NF-e** (emite + anexa na Shopee) → **Etiqueta**
(DESPACHA; se validando, "clique de novo") → **Separar (foto)** → **Entregar**.

**Auditoria (trio):** quality-guardian **1 CRÍTICO** (dupla baixa da reserva no deliver → `reserved_quantity`
negativo) + **1 HIGH** (dupla NF-e própria concorrente) — **ambos corrigidos**; consistency-auditor (lacunas
de front corrigidas: deliver silencioso, DANFE Shopee, help modal); adr-consistency-checker **CONFORME**.
pytest **385 ok** (2 pré-existentes) + 15 testes novos; build front OK.

**Deploy 2026-11-05 (commit `d1f78b7`, sem migration):** fast-forward `d53a478..d1f78b7`; `npm run build`
OK; PM2 restart; `/docs` 200; rota `/shopee-label` no OpenAPI; bundle novo no nginx; domínio 200.
**Pendente do dono:** validar com um pedido Shopee REAL (o DEV não fala com a Shopee) — percorrer
emitir NF-e→etiqueta/ship→entregar→SHIPPED e conferir que `reserved_quantity` NÃO fica negativo.
**Follow-ups:** pular Declaração de Conteúdo postal p/ Shopee no bundle; botão DANFE Shopee dentro da gaiola.

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

# Plano — Paridade Shopee no Sistema Drop (sem alterar o Mercado Livre)

> ## 📌 STATUS ATUAL (2026-07-18) — ponto de retomada
>
> **✅ FEITO E EM PRODUÇÃO:**
> - **F0 — fundação** (commit `8674db9`): corrigiu o `ImportError` que quebrava
>   `POST /accounts/{id}/sync-orders` (ML **e** Shopee); assinatura do push agora `url+body`;
>   `get_order_list` com paginação + propaga erro. Testes em `BACKEND/tests/test_shopee.py`.
> - **Fase 1 — conexão de conta robusta** (commit `0e27021` + **migration 132** já aplicada em
>   PROD e DEV): `services/shopee_auth.py` (token coordenado com lock, espelha `ml_auth`);
>   `shopee_service.get_shop_info` + `get_shops_by_partner`; validação de identidade no
>   `shopee_callback` (loja divergente → `wrong_account`); `SHOPEE_API_BASE` por env (toggle
>   sandbox); colunas `marketplace_accounts.shop_region/shop_status/main_account_id`.
> - Gate honrado em ambos: `pytest -m "not integration"` = 157 passed / 2 falhas pré-existentes;
>   nenhuma linha nova em bloco `if platform == "mercadolivre"` (ML intocado).
>
> **⛔ BLOQUEIO (o que estamos esperando):**
> - A conta do dono na Shopee está **em análise** para liberar a criação do **app** no Open
>   Platform. Só depois disso sai o **`partner_id` + `partner_key`**.
> - Em PROD hoje: `SHOPEE_PARTNER_ID`/`SHOPEE_PARTNER_KEY` **vazios**; **zero** contas Shopee
>   conectadas.
>
> **▶️ QUANDO O DONO TROUXER O ID/CHAVE DO APP — retomar assim:**
> 1. **Corrigir o `SHOPEE_REDIRECT_URI` no `.env` de PROD** (só com autorização do dono, não
>    tocar `.env` sem mandar): hoje aponta para `.../api/v1/**integrations**/shopee/callback`,
>    mas a rota real é `.../api/v1/**accounts**/shopee/callback`. Cadastrar essa MESMA URL no
>    console do Open Platform.
> 2. Configurar `SHOPEE_PARTNER_ID` e `SHOPEE_PARTNER_KEY` no `.env` de PROD.
> 3. Conectar uma loja em Integrações → "Conectar Shopee". (Ideal: também um **sandbox** para os
>    POST de escrita — `SHOPEE_API_BASE` já é configurável por env.)
> 4. **Pré-voo** (scripts assinados SOMENTE-LEITURA contra a loja real): `get_shop_info`,
>    `get_order_detail`, `get_pending_buyer_invoice_order_list`, `get_buyer_invoice_info`,
>    `get_escrow_detail`, `get_shipping_parameter`, `get_category` — capturar os schemas reais.
> 5. Implementar **Fases 2→7** com evidência (ordem: pedido rico → fiscal/anexo NF-e → logística
>    → publicação → categorias → custos).
>
> Regra de ouro (mantida): nenhum diff altera bloco `if platform == "mercadolivre"`.


## Context

O Sistema Drop já é multi-conta **Mercado Livre + Shopee** no modelo de dados
(`MarketplaceAccount.platform` / `Order.platform` / `ProductListing.account.platform`), mas a Shopee
está **pela metade**: conecta a conta (OAuth cru, sem validação de identidade), recebe pedido novo
(esqueleto pobre — sem CPF, sem itens detalhados) e sincroniza estoque básico. Falta: conexão robusta,
pedido rico, **fiscal (anexo de NF-e)**, logística/etiqueta, publicação/gestão de anúncio, categorias,
custos.

O objetivo é dar à Shopee **paridade operacional e de venda** com o ML, **sem tocar em nada que já
funciona no ML**. A arquitetura tem "costuras" que já ramificam por plataforma — a Shopee entra por
elas ou por rotas/serviços novos, **nunca** editando o interior de um `if platform == "mercadolivre"`.

### Correções sobre a primeira versão deste plano (o dono apontou, e estavam certas)

1. **Conexão de conta Shopee** ganhou seção própria e detalhada (estava rasa).
2. **A Shopee TEM fiscal/NF-e** — eu errei ao descartar. São **dois faturadores distintos**:
   - **Emissor de NF-e do Seller Center**: a Shopee **emite** a NF-e pelo vendedor (grátis, **só
     Simples Nacional**, exige certificado A1 no painel). É **UI-only — não há API** para disparar.
   - **Open Platform API (fiscal)**: modelo de **ANEXAR** a nota que o vendedor emitiu por fora —
     `order/upload_invoice_doc`, `order/get_pending_buyer_invoice_order_list`,
     `order/get_buyer_invoice_info`, `order/download_invoice_doc`. **Este é o encaixe do Drop**, que
     já emite NF-e própria via SEFAZ (ADR-0015/0016). A nota tem de ser **anexada e validada pela
     Shopee (contra a SEFAZ) ANTES do `ship_order`** — fiscal é pré-requisito da logística.
3. O estudo foi aprofundado contra a doc oficial (`open.shopee.com`) via o agente `shopee-especialista`
   e a skill `shopee-api`; os pontos que a doc (SPA anti-bot) não permitiu confirmar campo-a-campo
   estão listados e são fechados por uma **etapa de verificação ao vivo** (Pré-voo) antes de codar.

### Decisões do dono (confirmadas)
1. Publicação/gestão Shopee entra pela superfície **agnóstica `routers/listings.py`** + subtela Shopee
   enxuta. `routers/anuncios.py` e `AnunciosView.vue` ficam **100% ML, intocados**.
2. Plano **completo** de todas as fases.
3. Sem-par no ML (Faturador batch ML, DC-e, Mercado Ads, análise de concorrência ML, reputação/claims
   ML) fica documentado; NF-e de pedido Shopee usa a **emissão própria SEFAZ + anexo via API Shopee**.

## Princípio inviolável (regra de ouro de cada PR)

**Nenhum diff altera linhas dentro de um bloco `if platform == "mercadolivre"`.** Toda adição Shopee é
ramo novo em costura que já ramifica, ou função/rota/arquivo novo. `pytest -m "not integration"` +
`npm run build` são **gate de regressão** antes de cada entrega. Registrar em **ADR-0020**.

---

## Pré-voo — Verificação ao vivo (fecha as lacunas de schema ANTES de codar)

A doc oficial da Shopee (SPA anti-bot) não permitiu confirmar alguns schemas campo-a-campo. Antes de
implementar cada fase, rodar **scripts one-off assinados (somente-GET/leitura)** contra uma **loja BR
real** (o `shopee_service._sign` já existe) e ler o `response` cru, resolvendo com evidência:
`public/get_shops_by_partner`, `shop/get_shop_info`, `order/get_pending_buyer_invoice_order_list`,
`order/get_buyer_invoice_info`, `order/get_order_detail`, `order/get_escrow_detail`,
`logistics/get_shipping_parameter`. Onde possível, usar o **sandbox**
(`partner.test-stable.shopeemobile.com`) para os POST de escrita (`upload_invoice_doc`, `ship_order`,
`add_item`). Isso elimina o risco de montar payload errado.

---

## F0 — Hotfixes de fundação (PRIMEIRO; risco baixíssimo; bugs reais já confirmados no código)

1. **`routers/integrations.py:760`** — importa `_sync_ml_integration, _sync_shopee_integration` (com
   underscore) mas `tasks/sync_orders.py` define `sync_ml_integration` (:117) e `sync_shopee_integration`
   (:181) **sem** underscore → **ImportError** → `POST /accounts/{id}/sync-orders` **quebrado para ML e
   Shopee**. Corrigir o import (bug confirmado por leitura direta).
2. **`shopee_service.verify_push_signature` (:120)** — assina só o `body`; a base oficial do push é
   `url + body`. Corrigir e validar contra push real do sandbox.
3. **`get_order_list` (`shopee_service.py:94`)** — sem paginação (`page_size=50` fixo, só
   `READY_TO_SHIP`) e **engole erro** (`return []` na :116). Implementar paginação (`more`/`next_cursor`),
   aceitar faixa de status e **propagar/logar** o `error`.

**Verificar:** teste de assinatura do push contra vetor conhecido; `/sync-orders` numa conta Shopee
volta a funcionar.

---

## FASE 1 — Conexão de conta Shopee robusta (fundação; risco baixo)

Hoje: `shopee_authorize (integrations.py:693)` gera `state` e monta a URL assinada; `shopee_callback
(:707)` troca `code`+`shop_id` por token e grava `access_token`/`refresh_token`/`token_expires_at
(14400s=4h)`/`shop_id`. **Problemas:** (a) **sem validação de identidade** (o ML valida em :642-669);
(b) **não busca `get_shop_info`** — nome/região/status da loja ficam vazios (`platform_username` nulo);
(c) refresh Shopee é **inline e sem lock** (`sync_tokens.py:36`), não seta `requires_reauth` em falha;
(d) sem suporte a **sandbox** (host fixo) nem a **conta principal multi-loja**.

**Backend:**
- **`services/shopee_service.py`**: `get_shop_info(access_token, shop_id)` (nome/região/status —
  base de loja) e `get_shops_by_partner()` (endpoint **público** `public/get_shops_by_partner`:
  `authed_shop_list[]` com `shop_id`, `shop_name`, `region`, `status`, `expire_time` — para reconciliar
  quais lojas autorizaram o app). Tornar `SHOPEE_API_BASE`/`SHOPEE_AUTH_BASE` **configuráveis por env**
  (`config.py`) para alternar produção⇄sandbox sem tocar código.
- **`shopee_callback (integrations.py:707)`** — acrescentar validação de identidade análoga ao ML:
  após `exchange_code`, chamar `get_shop_info` e **conferir** que o `shop_id` retornado bate com
  `account.shop_id`/dono esperado; em divergência, **não** sobrescrever e redirecionar
  `?status=wrong_account` (mesmo padrão do ML). Gravar `platform_username = shop_name`,
  `requires_reauth = False`. **Este é ramo Shopee — não toca o ML.**
- **Novo `services/shopee_auth.py`** espelhando `services/ml_auth.py:60`:
  `get_valid_shopee_token(account, db, *, margin_seconds=300)` — lock por conta, re-leitura sob lock,
  refresh via `refresh_shopee_token` (rotaciona **access + refresh**, ambos salvos), marca
  `requires_reauth=True` em `invalid`. Trocar o ramo Shopee de `sync_tokens.py:36` para usar este
  caminho coordenado (sem tocar o ML).
- **(Opcional) Conta principal multi-loja**: `token/get` aceita `main_account_id` e autoriza várias
  lojas; `get_shops_by_partner` enumera. **Fora do MVP** (o modelo atual é 1 conta = 1 `shop_id`);
  deixar `get_shops_by_partner` pronto para reconciliação e registrar multi-loja como evolução.

**Frontend:** o botão "Conectar Shopee" e `connectOAuth` (`/shopee/authorize`) **já existem**
(`IntegrationsView.vue`). Ajustes: exibir **nome/região/status da loja** após conectar (hoje só
"connected"); tratar `?status=wrong_account` no `OAuthSuccessView` (a lógica já existe para o ML).

**Migrations:** `Scripts SQL/132_shopee_account_fields.sql` (idempotente) — adicionar a
`marketplace_accounts` (se necessário) `shop_region VARCHAR2(10)`, `shop_status VARCHAR2(20)`,
`main_account_id NUMBER` (nulo por ora). `shop_id`/`platform_username`/`requires_reauth` **já existem**.

**Verificar:** conectar loja no sandbox; callback com `shop_id` divergente é recusado; `get_shop_info`
popula nome/região; refresh coordenado renova sem corrida.

---

## FASE 2 — Pedido rico + estoque (operacional; risco baixo)

**Valor:** o dono vê o pedido Shopee com comprador, CPF, itens/SKU/preço; estoque sincroniza.

**Backend:**
- `shopee_service.py`: `get_order_detail(access_token, shop_id, order_sn_list)` (buyer, `recipient_address`,
  `item_list` com sku/preço, `pay_time`, `ship_by_date`).
- **Enriquecer `webhook_service.process_shopee_order (:712)`** **sem tocar `process_ml_order`**: após
  criar o pedido, chamar `get_order_detail` e preencher `buyer_document`/`buyer_document_type` (de
  `get_buyer_invoice_info` — ver Fase 3), `platform_status`, itens reais. Manter
  `shipping_mode=MODE_DESCONHECIDO` (correto — rede própria Shopee).
- `tasks/sync_orders.py:181` e ramo Shopee de `tasks/sync_stock.py`: usar
  `shopee_auth.get_valid_shopee_token`.

**Frontend:** nenhum novo (OrderListView/MarketplaceDashboard já multi). Só validar o pedido completo.

**Migrations:** nenhuma (colunas de `Order` já existem).

**Verificar:** sandbox — pedido → push → `Order`+`OrderItem`+buyer. Teste de `process_shopee_order` com
fixture de `get_order_detail`.

---

## FASE 3 — Fiscal: anexar NF-e ao pedido Shopee (risco médio; pré-requisito da logística)

**Valor:** cumprir a obrigação fiscal da Shopee BR reaproveitando a **emissão própria SEFAZ** que o
Drop já tem (ADR-0015/0016). Sequência oficial: pedido `READY_TO_SHIP` → **emitir NF-e (Drop/SEFAZ)** →
`upload_invoice_doc` → **Shopee valida na SEFAZ** → só então `ship_order` (Fase 4).

**Backend:**
- `shopee_service.py`: `get_pending_buyer_invoice_order_list()` (fonte canônica do que falta anexar),
  `get_buyer_invoice_info(order_sn_list)` (CPF/CNPJ + tipo `personal|company` + nome/endereço que o
  **comprador** exigiu — alimenta `buyer_document` do pedido), `upload_invoice_doc(order_sn, file_type,
  file, access_key?)` (anexa DANFE/XML; **confirmar no Pré-voo** se aceita XML e/ou PDF, base64 vs
  multipart, se leva `access_key`), `download_invoice_doc(order_sn)`.
- **Reusar a emissão própria** (`services/fiscal/…`): `resolve_nfe_xml(order)` dá `(xml, chave, kind)`
  e `services/fiscal/sefaz/danfe.gerar_danfe` dá o PDF — anexar via `upload_invoice_doc`.
- **Novo `routers/shopee_fiscal.py`** (ou ramo em `routers/orders.py` **apenas por função nova**, sem
  tocar guards ML): `GET /shopee/orders/pending-invoice`, `POST /shopee/orders/{id}/upload-invoice`
  (emite se preciso → anexa → guarda status), `GET /shopee/orders/{id}/invoice-status`.
- Job de conciliação: pollar `get_pending_buyer_invoice_order_list` e, para pedidos do Drop já com NF-e
  autorizada, anexar automaticamente; marcar `shopee_invoice_status` no pedido.
- **Decisão de negócio a alinhar** (documentar, não codar): se algum vendedor do Drop usa o **Emissor
  do Seller Center** (Shopee emitindo), isso **conflita** com a emissão própria — escolher uma fonte
  por CMIG. Sem API para o emissor Shopee; então o Drop assume o anexo.

**Frontend:** no detalhe/lista do pedido Shopee, status fiscal ("nota pendente / anexada / validada")
e botão "Emitir + anexar NF-e" (`v-if platform==='shopee'`).

**Migrations:** `Scripts SQL/133_shopee_invoice.sql` — `orders.shopee_invoice_status VARCHAR2(20)`
(`pending|uploaded|validated|rejected`) e, se útil, `shopee_invoice_uploaded_at`.

**Verificar:** sandbox — emitir NF-e (homologação SEFAZ) → `upload_invoice_doc` → status validado →
liberar `ship_order`. Conferir que o fluxo fiscal do ML (Faturador/DC-e) segue intocado.

---

## FASE 4 — Logística: etiqueta + rastreio (risco médio; depois do fiscal)

**Valor:** despachar pedido Shopee pela rede própria (modelo **diferente** do ML — sem Flex/Full/
cross-docking; etiqueta é documento **assíncrono**), após a nota validada.

**Backend:**
- `shopee_service.py`: `get_shipping_parameter`, `ship_order`, `create_shipping_document` (assíncrono),
  `get_shipping_document_result`, `download_shipping_document` (PDF), `get_tracking_number`.
- **Novo `routers/shopee_logistics.py`** (NÃO tocar `separation.py`, cujos 9 guards ML assumem
  `shipment_id` ML): `POST /shopee/orders/{id}/ship`, `GET /shopee/orders/{id}/label`,
  `GET /shopee/orders/{id}/tracking`. **Bloquear `ship` se `shopee_invoice_status != validated`.**
- Preencher `Order.tracking_code`/`tracking_url`/`shipment_status`/`label_url` (colunas já existem).
- Poll do documento assíncrono (job curto).

**Frontend:** botão "Despachar / Etiqueta" (`v-if platform==='shopee'`) no OrderListView/detalhe → novo
router (não a UI de separação ML).

**Migrations:** se guardar `shopee_package_number`, `Scripts SQL/134_shopee_shipment.sql`.

**Verificar:** sandbox — `ship_order` (com nota validada) → poll documento → PDF → tracking. Etiqueta ML
(`orders.py:3088`) inalterada.

---

## FASE 5 — Publicação / gestão de anúncio (risco médio; via `listings.py`)

**Backend (em `routers/listings.py`, o template agnóstico):**
- `shopee_service.py`: `update_item`, `unlist_item` (pause/reactivate), `get_item_list`, `add_item` com
  imagens (`upload_image`/`media_space`), `delete_item`, variações (`add_model`/`update_tier_variation`
  — hoje `create/update_stock/update_price` usam `model_id=0`).
- `pause_listing (listings.py:293)` — hoje só ML (:309); adicionar `elif platform=="shopee":
  unlist_item(unlist=True)`; criar `reactivate_listing` agnóstico. Enriquecer `_build_shopee_item
  (:343)` para item completo (peso, dimensões, imagens, `logistic_info`). Gravar `item_id` em
  `ProductListing.platform_item_id` (já agnóstico).

**Frontend:** subtela/aba de publicação Shopee **enxuta** (não `AnunciosView`). `PublishCategoryPicker`
já aceita `marketplace='shopee'`; `ListingManager.vue` já tem placeholder "ID do item Shopee".

**Migrations:** reusa `ProductListing` (`variations_json` CLOB já existe).

**Verificar:** sandbox — publicar/pausar/reativar/editar. Regressão: publicar/pausar item ML idêntico.

---

## FASE 6 — Categorias / atributos / marcas Shopee (risco baixo; habilita a Fase 5)

**Backend:** `shopee_service.py`: `get_category`, `get_attributes`, `get_brand_list`,
`category_recommend`. Endpoints com ramo Shopee em `listings.py`/`product_categories.py`
(`Category.shopee_category_id` já existe). Cache local da árvore Shopee.
**Frontend:** `PublishCategoryPicker` consumindo categorias/atributos Shopee.
**Migrations:** se cachear árvore, `Scripts SQL/135_shopee_categories.sql`.
**Verificar:** sandbox — árvore, atributos obrigatórios, publicar item que exige atributo.

---

## FASE 7 — Custos / comissão / simulador Shopee (risco baixo; valor gerencial)

**Backend:** `shopee_service.py`: `get_escrow_detail` (comissão + frete + taxas por pedido) → preencher
`Order.platform_fee` no ramo Shopee. Simulador Shopee **separado** do `routers/simulator.py` (ML):
comissão por categoria + frete rede própria.
**Frontend:** card de fees no detalhe do pedido (multi).
**Migrations:** reusa `platform_fee`; breakdown opcional.
**Verificar:** comparar `get_escrow_detail` com fatura real do sandbox.

---

## Fora de escopo (documentado)

- **Emissor de NF-e do Seller Center (Shopee emitindo)**: **não tem API** — o Drop usa o caminho de
  **anexo** (Fase 3) com sua emissão própria. Se um vendedor usa o emissor Shopee, é decisão por CMIG
  (uma fonte só de emissão), não código.
- **Faturador batch ML / DC-e**: intrínsecos do ML.
- **Mercado Ads, competitor_analysis ML, reputação/claims/messages ML, simulador ML**: permanecem
  ML-only. Shopee Ads/chat/reputação têm APIs próprias — fase futura, fora da paridade v1.
- `routers/anuncios.py` + `AnunciosView.vue`: permanecem ML, intocados.

## Matriz capacidade ML → Shopee (corrigida)

| Capacidade ML | Shopee | Situação |
|---|---|---|
| Conexão de conta + token coordenado | `shopee/authorize`+`get_shop_info`+`shopee_auth` | Viável (F1) |
| Pedido rico (list+detalhe+CPF) | `get_order_list`+`get_order_detail`+`get_buyer_invoice_info` | Viável (F2/F3) |
| **NF-e do pedido** | **emissão própria SEFAZ + `upload_invoice_doc`** | **Viável, diferente (F3)** — anexo, não emissão pela Shopee |
| Etiqueta/tracking | `ship_order`+`create_shipping_document`+`get_tracking_number` | Viável, diferente (F4) |
| Publicar/pausar/editar + variações | `add_item`/`unlist_item`/`update_item`/`tier_variation` | Viável, diferente (F5) |
| Categorias/atributos/marcas | `get_category`/`get_attributes`/`get_brand_list` | Viável, diferente (F6) |
| Comissão/custos | `get_escrow_detail` | Viável, diferente (F7) |
| Faturador batch ML / DC-e | — (Drop emite própria + anexa) | Impossível pela Shopee; usar anexo |
| Mercado Ads / competitor / reputação ML | Shopee Ads/chat (API própria) | Fora de escopo v1 |

---

## Migrations (todas idempotentes, em `Scripts SQL/`)
- `132_shopee_account_fields.sql` — `shop_region`, `shop_status`, `main_account_id` em
  `marketplace_accounts`.
- `133_shopee_invoice.sql` — `shopee_invoice_status`, `shopee_invoice_uploaded_at` em `orders`.
- `134_shopee_shipment.sql` (se necessário) — `shopee_package_number` em `orders`.
- `135_shopee_categories.sql` (se cachear a árvore).

## Arquivos-chave

**Novos:** `BACKEND/services/shopee_auth.py`, `BACKEND/routers/shopee_fiscal.py`,
`BACKEND/routers/shopee_logistics.py`, `DOCs/decisions/ADR-0020-paridade-shopee-por-costuras.md`,
subtela Shopee de publicação (frontend), migrations acima.

**Editados (só ramos Shopee / costuras que já ramificam):** `BACKEND/services/shopee_service.py`
(expansão grande), `BACKEND/services/webhook_service.py` (`process_shopee_order`),
`BACKEND/routers/integrations.py` (F0 + validação de identidade no callback Shopee),
`BACKEND/routers/listings.py` (pause/reactivate/build Shopee), `BACKEND/config.py`
(`SHOPEE_API_BASE`/sandbox), `BACKEND/tasks/{sync_orders,sync_stock,sync_tokens}.py` (ramo Shopee →
token coordenado). **`ml_service.py`, `ml_auth.py`, `anuncios.py`, `separation.py`, `simulator.py`,
`campaign_ads.py`, `messages.py`, `claims.py` NÃO são editados.**

## Verificação (entregue = verificado)

1. **Pré-voo ao vivo** por fase: script assinado somente-leitura contra loja BR real + sandbox para os
   POST, fechando os schemas que a doc não expôs (`upload_invoice_doc`, `get_buyer_invoice_info`,
   `get_shops_by_partner`, `get_shop_info`, `get_escrow_detail`).
2. **Gate de regressão ML** por fase: `cd BACKEND && pytest -m "not integration"` verde (baseline: 150
   passed / 2 falhas pré-existentes) + `npm run build`.
3. **Grep de segurança**: nenhum diff altera linha dentro de `if platform == "mercadolivre"`.
4. **Sandbox Shopee** exercitando o caminho de cada fase, consultando o agente `shopee-especialista` e
   a skill `shopee-api`.
5. **Prova no ambiente do dono**: validar o caminho real em produção após deploy (regra do CLAUDE.md).

## Lacunas ainda a confirmar no Pré-voo (não assumir — verificar)
- Schema exato de `upload_invoice_doc` (aceita XML e/ou DANFE? base64/multipart? leva `access_key`?).
- Prazo/janela (SLA) para anexar a nota no BR.
- Existência de `push code` fiscal dedicado (usar poll de `get_pending_buyer_invoice_order_list` como
  fonte canônica, independente de push).
- Nome do array multi-loja no `token/get` com `main_account_id`; campos de `get_shop_info`; host de
  sandbox vigente.

# ADR-0020 — Paridade Shopee por costuras agnósticas (sem tocar o ML)

**Data:** 2026-07-25
**Status:** ✅ Aceito — Fases 1-7 entregues (config LIVE em produção)
**Decisores:** Vinicius (proprietário)

## Contexto

O Mercado Livre é o marketplace maduro do Sistema Drop: pedidos, fiscal (Faturador ML + SEFAZ
própria — ADR-0015/0016/0017), logística/separação (ADR-0005), anúncios, estoque e custos já
rodam em produção e são o caminho crítico do dono. A Shopee, por outro lado, estava **pela metade**
— OAuth de conta, leitura de pedido e webhook/push funcionavam (F0-Fase 2), mas faltava fiscal,
logística, publicação/gestão de anúncios e custos.

Completar a Shopee mexendo na superfície comum (webhook_service, listings.py, separation.py,
sync_orders/sync_stock, orders) trazia um risco inaceitável: **regredir o ML** — o sistema que o
dono usa todo dia e que **não é validável no DEV** (o refresh token do ML é de uso único; ver
`feedback_verificar_em_producao`). Qualquer diff dentro de um caminho que o ML percorre poderia
quebrar produção sem que os testes locais acusassem.

Havia ainda a tentação de "emitir a nota pela Shopee" (a plataforma tem endpoints fiscais BR).
Mas o Sistema Drop **já emite** documento fiscal próprio (NF-e/DC-e — ADR-0015/0017); a Shopee
espera apenas **receber** o XML/PDF já emitido.

## Decisão

Dar à Shopee **paridade operacional** (Fases 1-7 do `DOCs/PLANO_PARIDADE_SHOPEE.md`) entrando
**SEMPRE** por **ramo, rota ou função nova**, ou por costura que **já ramifica por plataforma** —
**NUNCA** alterando uma linha dentro de um bloco `if platform == "mercadolivre"`. É a **regra de
ouro**: o caminho do ML é intocável; a Shopee é aditiva.

Concretamente:

- **Rotas Shopee isoladas sob `/api/v1/shopee`** — routers novos `shopee_fiscal.py`,
  `shopee_logistics.py`, `shopee_catalog.py`. Nada de estender os routers do ML.
- **`services/shopee_service.py`** concentra toda a conversa com a Shopee (assinatura HMAC-SHA256,
  fiscal, logística, catálogo, escrow), espelhando o papel do `ml_service.py`. Nenhuma função do
  `ml_service` é alterada para servir a Shopee.
- **Fiscal = ANEXAR, não emitir.** `upload_invoice_doc` **reusa a emissão fiscal própria**
  (`resolve_nfe_xml` → NF-e/DC-e já emitidos, ADR-0015/0017). A Shopee recebe o documento pronto;
  bloqueia (falha alto) se não houver NF-e/DC-e; a operação é reentrante.
- **Logística separada da separação do ML.** `separation.py` (Carrinho Gaiola, picking — ADR-0005)
  é **só ML**: um filtro protetor **exclui** a Shopee do picking. O fluxo Shopee (`ship`/`label`/
  `tracking`) mora em `shopee_logistics.py`, com gate de NF-e validada e reentrância.
- **`listings.py` agnóstico por ramificação existente.** Onde o router já ramifica por plataforma,
  a Shopee entra por um **novo ramo** (`_build_shopee_item` async com contrato BR; `pause` ganha um
  `elif shopee → unlist`; novo `reactivate`) — sem tocar o ramo do ML.
- **Superfície comum tocada só ADITIVAMENTE:** `main.py` só ganha `include_router` novos; migrations
  são **aditivas** (colunas novas `orders.shopee_invoice_status`, `orders.shopee_platform_fee` via
  `Order.platform_fee`); o frontend ramifica por `v-if`.

## Consequências

- **Positivas:** o ML permanece byte-idêntico no caminho crítico — nenhuma regressão possível por
  construção (não há diff no ramo ML). A Shopee ganha paridade real (fiscal, logística, publicação,
  custos) reusando o motor fiscal próprio já auditado. Superfície comum audível: cada toque é um
  `include_router`, uma coluna nova ou um `v-if`.
- **Negativas / limites:** há **duplicação deliberada** entre `shopee_service` e `ml_service`
  (assinatura, mapeamento de status, blocos de envio) — o preço de não acoplar os dois. Partes
  dependem de **evento/ação do dono** para validação real (a Shopee BR não expõe tudo no sandbox):
  `upload_invoice_doc` (encoding real do anexo), `ship_order`/etiqueta (exige pedido
  `READY_TO_SHIP`), `add_item` (publicar item de teste real) e a **Push Key LIVE** no `.env`.
- **Config LIVE em produção:** `.env` com `partner_id 2039749` + chave live + host de produção;
  loja real "Made In Group" (`shop_id 1556009762`) conectada (conta id 141).

## Alternativas consideradas

- **Emitir a NF-e/DC-e pela Shopee** (usar os endpoints fiscais de emissão da plataforma):
  rejeitada — o Sistema Drop já emite documento fiscal próprio (ADR-0015/0017); a Shopee só precisa
  **receber** o XML. Emitir por lá duplicaria a fonte fiscal e fugiria da SEFAZ própria.
- **Generalizar os fluxos do ML para "multi-plataforma"** (refatorar webhook_service/listings/
  separation para um contrato comum): rejeitada — exigiria mexer no caminho do ML, que **não é
  validável no DEV** e é o crítico do dono. O risco de regressão supera o ganho de DRY.
- **Estender os routers/serviços do ML com ramos Shopee dentro deles:** rejeitada — viola a regra de
  ouro; um erro no ramo Shopee poderia vazar para o fluxo ML compartilhado.

## Arquivos

- `BACKEND/services/shopee_service.py` — assinatura HMAC + todas as funções fiscais/logística/
  catálogo/escrow (`get_buyer_invoice_info`, `upload_invoice_doc`, `build_ship_block`,
  `map_shopee_shipment_status`, `get_category`/`get_attribute_tree`/`get_brand_list`, `add_item`,
  `unlist_item`, `get_escrow_detail`, …).
- `BACKEND/routers/shopee_fiscal.py` — `/api/v1/shopee`: pending-invoice, populate-buyer,
  upload-invoice (reusa `resolve_nfe_xml`), invoice-status.
- `BACKEND/routers/shopee_logistics.py` — ship (gate NF-e), label (poll 202), tracking.
- `BACKEND/routers/shopee_catalog.py` — categorias/atributos/marcas.
- `BACKEND/routers/listings.py` — ramo Shopee (`_build_shopee_item`, `pause→unlist`, `reactivate`).
- `BACKEND/routers/separation.py` — filtro protetor excluindo Shopee do picking ML.
- `FRONTEND` — ListingManager (reativar/preview/toasts) + botões de Custos, ramificados por `v-if`.
- Migrations aditivas: `135_orders_shopee_invoice_status.sql` (e coluna de custo via `Order.platform_fee`).

# ADR-0014 — Estoque-teto do fixo, pausa/reativação automática por disponibilidade, FULL derivado na leitura e sync horário de metadados do ML (sem estoque)

**Data:** 2026-06-28
**Status:** Aceito (implementado)
**Decisores:** Vinicius (proprietário)

## Contexto

Quatro ajustes pedidos pelo dono ao revisar o ciclo de estoque dos anúncios, todos
tocando o caminho de sincronização ML e estendendo ADR-0004/0008/0010:

1. **Estoque fixo cego.** `stock_mode='fixed'` + `keep_stock_fixed=True` reenviava o
   `fixed_quantity` cru a cada ciclo, podendo anunciar mais do que o galpão tem.
2. **Pausa implícita e sem reativação.** Quando o disponível zerava, o job apenas
   enviava `available_quantity=0` e confiava no auto-pause do ML (frágil em itens de
   catálogo) — e nunca reativava quando o estoque voltava.
3. **Anúncio não "enxergava" o FULL.** Ao mandar produto (PG ou CMIG) de uma NF-e para
   o FULL, nada no anúncio identificava que ele passou a ter lastro no FULL nem os
   vínculos/saldos (Local = PG ou CMIG; FULL = sempre CMIG).
4. **Sem detecção de mudanças feitas direto no ML.** Promoções, descrição, status e a
   condição FULL/não-FULL alteradas pelo vendedor no painel do ML não voltavam ao sistema.

## Decisões

### 1. Estoque fixo vira TETO (`min(fixed_quantity, disponível)`)

- Em `tasks/sync_stock.py` e na publicação/edição (`routers/anuncios.py`), quando o anúncio
  é `stock_mode='fixed'` + `keep_stock_fixed=True` **e tem vínculo de produto resolvível**,
  envia-se `min(fixed_quantity, available_to_push(db, listing))`.
- Anúncio fixo **sem** vínculo de produto mantém o `fixed_quantity` puro (não há disponível
  a comparar — preserva o caso "isca").
- Consequência: o fixo nunca expõe mais do que existe; se o disponível zera, o teto vira 0
  e o anúncio é pausado pela regra (2).

### 2. Pausa/reativação automática explícita (coluna `auto_paused`)

- Nova coluna `product_listings.auto_paused` (Boolean, default False).
- No `sync_stock`, decisão de pausar usa **`available_to_push` puro** (não o `min` com o
  fixo): se `disponível == 0` e o anúncio não é FULL → `update_item_status("paused")` e
  `auto_paused=True`. Se `disponível > 0` e `auto_paused=True` → `update_item_status("active")`
  e `auto_paused=False`.
- **Nunca reativa anúncio pausado manualmente** pelo dono (só reativa o que tem
  `auto_paused=True`). Isso evita que o sync brigue com o status que o job de metadados (4)
  traz do ML e que o sistema "ressuscite" um anúncio pausado de propósito.
- Respeita ADR-0008: como a pausa olha `available_to_push`, que só zera quando LOCAL **e**
  FULL estão zerados, um anúncio não-FULL com lastro no FULL continua ativo.
- Critério de "anúncio está no FULL" = `logistic_type`/`is_full` do **próprio anúncio**
  (decisão do dono).

### 3. FULL do anúncio é DERIVADO na leitura (sem coluna redundante)

- **Não** se persiste flag de "tem FULL" no anúncio (seria 2ª fonte de verdade que
  dessincroniza nas baixas FULL). A leitura do anúncio deriva, via
  `full_stock_service.available_for_product()` (resolvendo o CMIG espelho mesmo para anúncio
  só-PG), os campos exibidos: `has_full_stock`, `full_cmig_product_id` (CMIG espelho), saldo
  **Local** (PG ou CMIG) e saldo **FULL** (sempre CMIG).
- O gatilho de "passou a ter FULL" é o próprio crédito em `full_stock` feito por
  `apply_nfe_saida_to_full` (ADR-0010) — nenhuma escrita extra no anúncio é necessária.

### 4. Job horário de metadados do ML — tudo MENOS estoque

- Novo `tasks/sync_listings_from_ml.py` (`IntervalTrigger(hours=1)`, todas as contas ML
  ativas), no mesmo padrão de `ml_fiscal_sync` (`tracked_job` + `task_db` + sequencial por
  conta + `stats`).
- Sincroniza do ML para o DB: título, preço/`original_price`, descrição, status,
  `logistic_type`/`is_full`, atributos, fotos, categoria (`category_name`/path), visitas e
  **promoções**.
- **NÃO** toca em estoque: `available_quantity`, `qty_full`, `qty_local` ficam intocados.
- Promoções: `deal_ids`/`original_price` do item **não são confiáveis** (comprovado ao vivo:
  vieram vazios com promoções ativas). Fonte canônica = `GET /seller-promotions/items/{id}?app_version=v2`
  (nova função `ml_service.get_item_promotions`).
- Reuso: estende o helper `_apply_ml_item_to_listing` (compartilhado com `POST /import`) com
  parâmetro `sync_stock=False`, mantendo paridade de campos (categoria/visitas/promo) com o
  import em lote.
- Interação com (2): o job escreve `listing.status` a partir do ML; o `auto_paused` garante
  que o `sync_stock` só reativa o que ele mesmo pausou — sem flapping de status.

## Consequências

- **Positivas:** fixo deixa de oversell; anúncios pausam/reativam sozinhos conforme o
  disponível real (LOCAL+FULL); o anúncio passa a mostrar Local/FULL e o CMIG dono do FULL
  sem nova fonte de verdade; mudanças feitas direto no ML (promoção/descrição/FULL) voltam ao
  sistema de hora em hora, sem importar estoque.
- **Negativas / riscos aceitos:**
  - 1 coluna nova (`auto_paused`, migration idempotente).
  - O job horário multiplica chamadas à API do ML (multiget 20/lote + descrição + promoções
    por item) — mitigado por sequencial-por-conta e `Semaphore` nas promoções. Em 429/erro o
    lote/item é tratado como vazio (sem crash) e recuperado no próximo ciclo (job idempotente
    horário). Backoff/retry explícito é melhoria futura.
  - "Fixo vira teto" muda o contrato da feature de estoque fixo (era valor cru) — decisão
    explícita do dono registrada aqui.

## Referências
- `BACKEND/tasks/sync_stock.py` (teto do fixo + pausa/reativação via `auto_paused`)
- `BACKEND/tasks/sync_listings_from_ml.py` (job horário de metadados — novo)
- `BACKEND/services/ml_service.py` (`update_item_status`, `get_item_promotions` — novo)
- `BACKEND/services/full_stock_service.py` (`available_to_push`, `available_for_product`)
- `BACKEND/routers/anuncios.py` (`_apply_ml_item_to_listing` com `sync_stock=False`; leitura derivando FULL)
- `BACKEND/models/product.py` (`ProductListing.auto_paused`)
- `Scripts SQL/114_listing_auto_paused.sql`
- ADR-0004 (estoque SSOT), ADR-0008 (anúncio não-FULL anuncia FULL quando LOCAL=0), ADR-0010 (FULL sempre CMIG)

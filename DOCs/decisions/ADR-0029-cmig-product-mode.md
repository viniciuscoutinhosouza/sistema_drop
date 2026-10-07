# ADR-0029 — Modo de produto da CMIG (`product_mode`: both / cmig_only / pg_only)

**Status:** Aceito
**Data:** 2026-10-07
**Complementa:** [ADR-0024](ADR-0024-galpao-work-type-dropship-multilojas.md) (work_type do Galpão), [ADR-0010](ADR-0010-full-sempre-cmig.md) (FULL é sempre CMIG)

## Contexto

O dono quis, **por CMIG**, escolher quais grupos de produto a empresa usa: **PG + CMIG** (`both`),
**só CMIG** (`cmig_only`) ou **só PG** (`pg_only`). Na UI (Catálogo, Pedido Manual) só deve aparecer o
grupo usado. **Exceção:** em `pg_only`, o produto CMIG ainda aparece **no envio ao FULL** — porque o
estoque FULL é sempre do produto CMIG (ADR-0010, espelho auto-criado).

Já existia o `warehouse.work_type` (ADR-0024): `multilojas` bloqueia publicar PG no **galpão inteiro**.
`product_mode` é um **segundo eixo, ortogonal e mais fino** (por CMIG), não um substituto.

## Decisão

- **`cmigs.product_mode`** VARCHAR2(20) DEFAULT `'both'` NOT NULL + CHECK (`both|cmig_only|pg_only`) — migration 149. Default preserva o comportamento atual; **sem backfill** por work_type (eixos ortogonais).
- **Ponto único de enforcement** (`services/product_mode.py::assert_product_group_allowed(cmig, warehouse, *, is_pg, is_cmig, is_full)`):
  - `is_full` → **isento** (retorna no topo): o FULL sempre pode usar CMIG (ADR-0010).
  - PG (não-full) **bloqueado** se `work_type == 'multilojas'` **OU** `product_mode == 'cmig_only'` (multilojas vence por AND).
  - CMIG (não-full) **bloqueado** se `product_mode == 'pg_only'`.
  - `work_type_guard.assert_pg_allowed_for_account` foi reescrito como **adaptador que delega** a esse guard — a regra multilojas deixou de ser duplicada (antes havia cópias inline em `manual_orders`/`catalog`).
- **Precedência:** multilojas (galpão) sempre vence no eixo PG. CMIG nunca é bloqueado por work_type — só por `product_mode == 'pg_only'`.
- **Fail-loud (não só UI):** os pontos de mutação — publicar anúncio (`anuncios.py`), publicar listing ML/Shopee (`listings.py`), adicionar item de Pedido Manual (`manual_orders.py`) — chamam o guard e retornam **403** no grupo proibido. Esconder a aba no front é só UX.
- **`/catalog` permanece escopado por galpão** (não por CMIG) — o enforcement de modo vive no ponto de publicação/add-item (onde a CMIG é conhecida); o front esconde a aba conforme a CMIG selecionada.

## Isenções (NÃO filtrados por `product_mode`)

- **Envio/estoque FULL**: `full_stock_service`, `sync_stock`, `full_cnpjs`, ramo FULL de anúncios/estoque — nunca passam pelo guard.
- **Criação/import de CMIGProduct**: permitida em qualquer modo (inclusive `pg_only`) — o espelho FULL precisa existir (ADR-0010).
- **Publicar anúncio CMIG direto em `pg_only` É intencionalmente bloqueado** (regra do dono: em Somente PG, o produto CMIG aparece **apenas no envio ao FULL**, que é push de estoque, não publicação). Anúncio FULL no sistema é PG-linkado (estoque do espelho CMIG), logo passa como PG, não como CMIG-direto.
- **Separação / kit**: separação opera sobre pedido já validado; componente PG dentro de kit CMIG é base (não venda PG direta) — nenhum dos dois é filtrado.

## Frontend

CatalogView e ManualOrderView calculam a visibilidade das abas PG/CMIG por `activeCmig.product_mode`
+ `isMultilojas` e **re-selecionam** a aba visível quando a ativa some. Seletor de "Modo de produto"
no cadastro/edição da CMIG. FULL intocado.

## Consequências

- **Positivo:** controle fino por CMIG do grupo de produto, com um ponto único de enforcement (fim das cópias inline da regra multilojas). FULL preservado (ADR-0010). Zero regressão (todas as CMIGs nascem `both`).
- **Verificação:** `tests/test_product_mode.py` (16 casos — matriz modo × is_pg/is_cmig/is_full × work_type, incl. isenção FULL e "multilojas vence"). Auditado (quality-guardian: sem bloqueios; consistency-auditor: ponto único + 2 serializers + exceção FULL confirmados).
- **Nota:** `product_mode` NÃO toca os caminhos de estoque/FULL — é só visibilidade/autorização de grupo na venda local e na publicação.

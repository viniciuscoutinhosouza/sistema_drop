# ADR-0024 — Tipo de trabalho do Galpão: Dropship × MultiLojas

Data: 2026-09-23
Status: Aceito

## Contexto

Um Galpão (Warehouse) agrega várias contas de marketplace (via CMIG). Até aqui, toda conta podia
vender qualquer produto do **Produto Geral (PG)** — o catálogo-base do galpão — além dos produtos
da sua própria **CMIG**. O dono precisa de um segundo modelo operacional em que o PG serve **apenas
de base** para o cadastro na CMIG e **cada conta vende só a própria CMIG** (multi-lojas isoladas
sob o mesmo galpão físico).

## Decisão

O Galpão passa a ter um **tipo de trabalho** (`warehouses.work_type`, migration 137, `NOT NULL`
default `dropship` — backfill dos existentes):

- **`dropship`** — a conta vende produtos do **PG** + a própria **CMIG** (comportamento histórico).
- **`multilojas`** — o PG é só base; a conta **só vende a própria CMIG**. Publicar um produto do PG
  é **bloqueado**.

### Enforcement — ponto ÚNICO

`services/work_type_guard.assert_pg_allowed_for_account(account, is_pg_publish, db)` é o único lugar
que decide. Resolve o `work_type` por **conta → CMIG → Warehouse** e, se `multilojas` e a publicação
for de PG, levanta **403**. Não age para `dropship`, conta sem CMIG, ou publicação de produto CMIG.

Aplicado em **todos** os caminhos de publicação (senão vaza):
- `routers/anuncios.py`: `/publish` (`bool(catalog_product_id)`), `/publish-with-variations`
  (`source=='pg'`), `/publish-as-family` (`source=='pg'`).
- `routers/listings.py`: `publish_listing` mode=`create` (`bool(product.catalog_product_id)`) —
  cobre **Mercado Livre e Shopee** (o caminho que a auditoria pegou faltando).

Caminhos de **import/sync** de anúncios já existentes (espelham o marketplace) **não** passam pelo
guard — não são publicação nova de PG (`integrations.py`, `services/listing_import.py`,
`anuncios.py` sync).

### UI (espelho, não é a fonte da verdade)

No **Catálogo**, quando o galpão do usuário (escopado a 1 galpão) é `multilojas`, a aba **Produto
Geral** é escondida e o Catálogo abre na CMIG. É conveniência; o backend é quem bloqueia.

### Falhar alto

`_norm_work_type` aceita só `dropship`/`multilojas`; valor inválido → **400** (não coage em silêncio
para `dropship`, senão o dono configuraria MultiLojas achando que salvou e ficava Dropship).

## Consequências

- **Positivas:** isolamento de venda por conta no modelo multi-lojas, com um ponto único de
  enforcement (fácil de auditar) que cobre ML e Shopee.
- **Fail-safe do enforcement:** se `work_type` resolver `None` (não ocorre — `CMIG.warehouse_id` é
  `NOT NULL` e a coluna tem default), o guard **não bloqueia** (permissivo). Aceito: melhor liberar
  do que travar venda por dado inconsistente.
- **Custo:** o guard re-consulta o `work_type` por publish (um join). Aceitável no volume atual;
  se crescer, carregar via `selectinload` na conta já resolvida.

## Relação com outras ADRs

- **ADR (isolamento do GO por galpão, 2026-09-23):** mesma direção — dados e agora venda escopados
  por galpão. O `work_type` é ortogonal ao papel: define a REGRA DE VENDA do galpão, não quem vê o quê.

## Pendências

- A UI do Catálogo usa o galpão do **usuário** (correto para usuário escopado a 1 galpão); para
  admin multi-galpão as duas abas aparecem (admin não é restringido). Se um dia precisar refletir o
  `work_type` da **conta selecionada** (não do usuário), expor `work_type` na serialização da conta.

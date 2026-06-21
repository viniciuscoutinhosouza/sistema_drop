# ADR-0012 — Coletor de busca ML local (Camoufox) acessado por HTTP, fora do servidor

**Data:** 2026-06-20
**Status:** Aceito (implementado — Fase 0 + integração na Análise de Concorrência)
**Decisores:** Vinicius (proprietário)

## Contexto

A busca livre por palavra-chave do Mercado Livre na API oficial (`/sites/MLB/search`)
foi **descontinuada (403)**. A Análise de Concorrência (ADR-0011) passou a enxergar
só itens de **catálogo** (buy box) e **highlights** de categoria — sem a busca por
texto, que é a fonte mais rica de concorrentes diretos.

A alternativa é navegar o `mercadolivre.com.br` por um browser anti-detect
(**Camoufox**, kit do projeto BPFCAR_FINANCEIRAS) e raspar o grid de resultados.
Restrições descobertas:

- O **servidor de produção** é uma VM Oracle Free Micro (1 GB RAM, Linux): **não roda
  Firefox/Camoufox**; a shape tem RAM fixa; a opção free ARM (24 GB) não roda o binário
  x86 do Camoufox.
- **Mais grave:** Akamai (proteção do ML) pontua **IP de datacenter** agressivamente.
  Rodar do IP da Oracle Cloud seria detectado mesmo com fingerprint perfeito.
- Anti-detect só funciona bem a partir de **IP residencial**.

## Decisão

**O coletor é um módulo separado que roda LOCALMENTE (máquina do operador, IP
residencial) e expõe uma API HTTP; o backend na Oracle a consome como 3ª fonte.**

- **Módulo:** `tools/collector/` — API FastAPI própria (`collector_api.py`) rodando na
  venv dedicada `.venv-camoufox` (Python 3.11). `POST /collect {query, limit?, headless?}`
  → roda Camoufox local (anônimo) → devolve `items[]` com `item_id` (MLB…), título,
  preço, vendedor. Núcleo de scraping em `ml_search.py`. Um navegador por vez (lock +
  threadpool, pois Playwright sync bloqueia).
- **Modelo de chamada = request/response síncrono** (não worker-pull com fila). O
  backend chama a API do coletor de dentro de `_gather_ml` via `httpx` (await, com
  timeout generoso), exatamente como já chama a API do ML. **Não** há parking/resume,
  **nem** tabela de jobs, **nem** novo router/role no backend — a complexidade do
  worker-pull foi evitada porque o request/response cabe no pipeline existente (ADR-0011).
- **Autenticação:** secret compartilhado (`COLLECTOR_API_TOKEN`) em
  `Authorization: Bearer`, seguindo o padrão de caller-não-humano do projeto (webhooks),
  **não** um usuário/role fantasma.
- **Reachability:** a máquina local fica atrás de NAT/CGNAT → expor por **túnel**
  (Cloudflare Tunnel/ngrok). A URL pública vai em `COLLECTOR_API_URL` no `.env` do
  backend. O túnel carrega só o tráfego de controle; o Camoufox sai pelo IP residencial.
- **Opt-in e degradação graciosa:** `COLLECTOR_ENABLED=False` por padrão. Desligado,
  indisponível, com erro ou captcha → a análise **completa com catálogo + highlights**
  (comportamento atual), apenas registrando o aviso em `errors`. Nunca derruba o estudo (M3).
- **Rastreabilidade:** itens raspados são marcados `source: "search_scraped"` (ao lado
  de `catalog`/`highlights`) no `all_results_raw`; `search_study.scraped_count` expõe a
  contagem. A IA e auditorias sabem a origem.

## Consequências

**Positivas:** recupera a busca por texto sem expor o IP de datacenter; isolado do
backend (venv/processo/máquina próprios); zero custo de infra (IP residencial); some a
complexidade de fila do worker-pull; seguro por padrão (opt-in + degradação).

**Negativas / riscos aceitos:**
- **ToS do ML:** raspar páginas viola os termos (skill `mercado-livre-api`: "nunca
  crawl"). Mitigações: navegação **anônima** (sem login → sem conta atrelada), volume
  baixo, IP residencial. Risco aceito pelo dono.
- **Dependência de máquina local ligada + túnel** para a 3ª fonte funcionar; produção
  24/7 fica em aberto (provável worker x86 dedicado + proxy residencial) — **decisão
  pendente**, registrado que **não** deve rodar no servidor Oracle.
- **Fragilidade de scraping:** classes do ML mudam → o parser usa o ID via âncora
  (sinal forte) + seletores múltiplos + fallback; título/preço são best-effort.
- **Latência:** Camoufox é lento (segundos) → `COLLECTOR_TIMEOUT` generoso; o passo de
  progresso "Consultando Mercado Livre" da ADR-0011 já cobre a espera (sem novo status).

## Alternativas consideradas

- **Rodar Camoufox no servidor Oracle** (com mais RAM): inviável (shape fixa; ARM não
  roda x86; IP de datacenter detectado). Rejeitada.
- **Worker-pull com fila de jobs no backend** (`ml_collection_jobs`, parking/resume,
  expiração via APScheduler): mais robusto p/ 24-7 e desacoplado, mas exige tabela,
  router, role/secret, refactivação de task e ADR de mudança de padrão. Descartado para
  esta fase por excesso de complexidade — o request/response síncrono atende o uso
  on-demand atual. Fica como evolução se a produção 24/7 exigir.

## Adendo (2026-06-20) — Busca por relevância, 120 itens paginados

Evolução do contrato da 3ª fonte (não muda a arquitetura):
- O coletor **pagina** a busca pública do ML (clica "Seguinte"; fallback URL `_Desde_N`)
  até juntar **120 itens** na ordem de **relevância** (default do ML — sem `_OrderId_`).
  Cada item carrega `search_rank` (1..N). Checa captcha **por página** e para no 1º.
- O `search_rank` é propagado ao backend por **mapa `item_id→rank`** (`_fetch_scraped_ids`
  retorna `(ids, rank_map, err)`), porque o multiget de detalhes não preserva ordem.
  `_gather_ml` aplica `it["search_rank"]` e monta `search_study.top_by_relevance`.
- **Custo de token:** a IA recebe apenas `top_by_relevance[:25]` + agregados + top10 por
  vendas; os 120 crus ficam só no `result_json` (memória/auditoria), como `all_results_raw`.
- **Limites acoplados:** `COLLECTOR_LIMIT` (backend) = `COLLECTOR_DEFAULT_LIMIT` (coletor) = 120;
  `COLLECTOR_TIMEOUT` (330s) > `SUBPROCESS_TIMEOUT` (300s) > navegação das ~3 páginas.
- Metodologia (memorando): o `_SYSTEM_PROMPT` passou a descrever **três** fontes (catálogo /
  busca por relevância 120 / highlights) e instrui a IA a usar os itens por relevância como
  **amostra de mercado** (keywords, preço, intensidade), comentando individualmente só o top10.

## Adendo (2026-06-21) — ML bloqueou /items; coletor vira fonte PRIMÁRIA

O ML estendeu o bloqueio: além da busca (`/search`), agora `GET /items/{id}` e
`/items?ids=` retornam **403 `PolicyAgent / PA_UNAUTHORIZED_RESULT_FROM_POLICIES`**
para anúncios de **terceiros** (concorrentes), mesmo autenticado. Isso matou o passo
de enriquecimento (`fetch_item_details`/visitas/reputação) — `listings` ficava vazio
e a tela mostrava "falha ao carregar detalhes".

Decisão: **o coletor (busca raspada) passa a ser a FONTE PRIMÁRIA** dos concorrentes.
- O coletor raspa o **máximo** da página de busca por item: título, preço, preço
  original, vendedor, "X vendidos", avaliação/reviews, frete grátis, FULL, thumbnail,
  permalink, search_rank, sponsored.
- `_gather_ml` monta `listings` direto desses dados (`_build_listings_from_scraped`),
  com TODAS as chaves que o front lê (campos da API ausentes = `None`).
- **Enriquecimento via API desligado por flag** `ML_COMPETITOR_ENRICHMENT=False`
  (config). Quando ligado, `_enrich_via_api` é só um overlay best-effort (dormente
  enquanto o ML bloquear). Catálogo/highlights (que só davam IDs p/ a API morta)
  foram removidos do fluxo.
- `enrichment_off=true` viaja no `ml_data` → a IA não cita visitas/data/reputação e
  marca previsão como **baixa confiança**; o front troca o rótulo "por vendas"→"por
  relevância" e oculta colunas de Visitas/Reputação.
- `sold_quantity` vira **aproximado** (parse de "X vendidos"); `top_categories` usa a
  categoria sugerida (domain_discovery, ainda público) já que o raspado não traz
  category_id. Comissão na mediana segue best-effort (endpoint público).

## Adendo (2026-06-20) — Failover de múltiplas máquinas coletoras

`COLLECTOR_API_URL` aceita **lista separada por vírgula** de URLs (máquinas). O backend
(`_fetch_scraped_ids` → `_collector_endpoints`) tenta na ordem; se uma cair, der erro ou
**captcha**, passa para a próxima (IP residencial diferente — pode não ter captcha). Só
falha de vez se todas falharem (degradação graciosa preservada). `COLLECTOR_API_TOKEN` pode
ser 1 token compartilhado ou lista alinhada às URLs. Entradas vazias são ignoradas (permite
deixar a 2ª máquina pré-configurada e ligá-la depois). Resolve a fragilidade de uma única
máquina/túnel sem exigir named tunnel.

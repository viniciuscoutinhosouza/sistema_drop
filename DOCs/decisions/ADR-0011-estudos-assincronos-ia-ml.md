# ADR-0011 — Estudos assíncronos IA+ML: job in-process por request + estudo persistido como memória

**Data:** 2026-06-19
**Status:** Aceito (implementado — Análise de Concorrência)
**Decisores:** Vinicius (proprietário)

## Contexto

A tela "Análise de Concorrência" precisa orquestrar muitas chamadas ao Mercado Livre
(categoria, catálogo, concorrentes, preços, frete, visitas, reputação) e à IA
(`ai_service`) para sintetizar um estudo (título, categoria, faixa de preço, top
concorrentes, previsão). É lento (~30–90s), disparado sob demanda pelo usuário, e o
resultado deve ser guardado para reabrir, comentar e servir de **memória** a estudos
futuros do mesmo produto. Isso difere dos jobs periódicos (APScheduler) já existentes.

## Decisão

**Padrão de "estudo assíncrono IA+ML": job in-process por request + persistência reutilizável.**

- Tarefa longa disparada por request via `asyncio.create_task` retida em um set
  `_BG_TASKS` (mesmo padrão de `_sync_ml_fiscal`), **não** APScheduler (este fica para
  jobs periódicos). O endpoint `POST` cria o registro `status='running'` e agenda a task.
- **Contrato de status por polling**: `status ∈ {running, done, error}` + `progress_step`
  textual; o frontend faz `setInterval` (3s) em `GET /{id}` até `done`/`error`.
- **HTTP (ML/IA) sempre FORA de sessão de BD**; reabrir `task_db()` em sessões curtas por
  etapa (ADR-0001). Objetos ORM **não cruzam** para o background — recarregar por id
  dentro da sessão da task (ex.: a conta ML antes do `get_valid_token`, senão o refresh
  do token não persiste).
- **Resultado canônico em CLOB JSON** (`competitor_analyses.result_json`): guarda o estudo
  + os dados brutos do ML usados. É um snapshot (não fonte de verdade transacional) →
  JSON é adequado, sem tabelas normalizadas.
- **Memória/realimentação**: estudos `done` anteriores (até 3) + as `notes` do usuário
  entram no prompt da IA, escopados por `requester_user_id`. O `user_prompt` (comentário
  antes de iniciar) também vai ao prompt.
- **IA** via `ai_service` (config em `ai_configs`, chave base64). Adicionada
  `ai_service.complete(...)` com `max_tokens`/`timeout` para saída longa estruturada (JSON).

## Consequências

- Estudos são **pessoais** (escopo por `requester_user_id`; admin vê todos) — o histórico
  e a memória nunca vazam prompts/anotações entre usuários.
- A previsão de vendas/visitas/lucro é **estimativa da IA** (faixa + confiança), claramente
  rotulada (`disclaimer`); NÃO é tratada como estoque/SSOT (não conflita com ADR-0004/0008/0010).
- Coleta ML é **live** no momento do estudo e **congelada** no `result_json` (consistente
  com a filosofia do ADR-0006: live passthrough congelado vs. métrica diária persistida).
- Risco aceito: a task morre se o processo reiniciar (sem fila/retry persistente); estudos
  presos em `running` podem ser refeitos (DELETE bloqueia enquanto `running`).
- `price_to_win`/`health` (exigem item próprio publicado) ficam para um modo futuro
  "otimizar anúncio existente".

## Referências
- `BACKEND/routers/competitor_analysis.py`, `BACKEND/services/competitor_analysis_service.py`,
  `BACKEND/services/ml_service.py` (search_catalog_products/get_catalog_product/.../get_items_visit_stats_range),
  `BACKEND/services/ai_service.py` (`complete`), `BACKEND/models/competitor_analysis.py`,
  `Scripts SQL/111_competitor_analysis.sql`, `FRONTEND/src/views/analysis/CompetitorAnalysisView.vue`.
- ADR-0001 (AsyncSyncSession), ADR-0006 (live vs snapshot).

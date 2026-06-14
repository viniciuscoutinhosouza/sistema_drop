# ADR-0006 — Métricas de marketplace: consulta ao vivo (live passthrough) vs. snapshot diário persistido

**Data:** 2026-06-14
**Status:** Aceito (implementado)
**Decisores:** Vinicius (proprietário)

## Contexto

O sistema passou a ter **dois consumidores de métricas vindas de APIs de marketplace**
(Mercado Livre Ads / visitas / perguntas) com necessidades diferentes:

1. **Dashboard de Marketplaces** (`routers/dashboard.py`) — precisa comparar janelas
   (Hoje × Ontem × 7d × Mês × Mês anterior) e, portanto, de **histórico próprio**.
   Visitas/perguntas/ADS não existem no banco e a API do ML não devolve série
   arbitrária para trás de forma barata.
2. **Campanha ADS** (`routers/campaign_ads.py`, módulo novo) — tela exploratória de
   acompanhamento de campanhas/anúncios/ad groups por CMIG, com intervalo escolhido
   pelo usuário (até 90 dias, limite da API de Mercado Ads), números que mudam o
   tempo todo e granularidade de campanha/anúncio/dia sob demanda.

Surgiu a pergunta arquitetural: **toda métrica de marketplace deve ser persistida em
snapshot, ou pode ser consultada ao vivo?**

## Decisão

Adotar **dois padrões coexistentes**, escolhidos pela natureza do dado:

### Padrão A — Snapshot diário persistido (referência: ADR-0004, estoque)
- Usado pelo **Dashboard de Marketplaces**.
- Tabela `marketplace_metrics_daily` (`models/integration.py`) com upsert por
  `(account_id, metric_date)`, alimentada pelo job `tasks/sync_marketplace_metrics.py`
  (4x/dia). Leitura barata e resiliente; serve comparação entre janelas e histórico.
- **Quando usar:** quando o requisito exige histórico, comparação temporal,
  fechamento contábil, ou resiliência à indisponibilidade da API externa.

### Padrão B — Live passthrough (sem tabela, sem job)
- Usado pelo módulo **Campanha ADS**.
- O backend consulta a API de Mercado Ads na hora (token da conta via
  `ml_auth.get_valid_token`) e repassa o dado cru ao front; o front calcula as
  derivadas (`derive()`). Sem migration, sem job, sem cache.
- **Quando usar:** dado exploratório sob demanda, janela definida pelo usuário,
  alta cardinalidade (por campanha/anúncio/dia), em que o custo de modelar/persistir
  não se paga e o dado fresco é desejável.

## Consequências

- **Aceitas para o padrão B (Campanha ADS):**
  - Latência da API do ML em cada request; `asyncio.gather` no Raio-X e fan-out por
    conta em `/advertisers` multiplicam chamadas — mitigado com **tolerância por
    conta** (`try/except continue`) e validação de janela ≤90 dias antes de chamar.
  - **Sem trilha histórica:** relatório contábil/fechamento mensal de ADS **não** sai
    desta tela (o ML limita a 90 dias e nada é persistido). Se isso for pedido,
    migrar a métrica para o **Padrão A** (snapshot).
  - Exposição a rate limit do Mercado Ads; não há cache nem backoff nesta fase
    (aceitável por ser read-only de baixa frequência).

## Regra para a próxima tela de métricas

Antes de adicionar uma nova tela/relatório de métricas de marketplace, decidir
explicitamente entre A e B pelos critérios acima. Histórico/comparação/contábil ⇒ A.
Exploração sob demanda com janela do usuário ⇒ B. Registrar a escolha se fugir destes.

## Referências

- ADR-0004 — Estoque SSOT + snapshots (origem do padrão de snapshot).
- `BACKEND/tasks/sync_marketplace_metrics.py`, `BACKEND/routers/dashboard.py`,
  `BACKEND/models/integration.py` (`marketplace_metrics_daily`) — Padrão A.
- `BACKEND/routers/campaign_ads.py`, `BACKEND/services/ml_service.py`
  (bloco "Advertising / Product Ads") — Padrão B.
- `Levantamento_Campanha_ADS.md` — mapeamento da API de Mercado Ads.

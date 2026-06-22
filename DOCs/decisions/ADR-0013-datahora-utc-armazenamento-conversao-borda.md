# ADR-0013 — Data/hora: UTC aware no armazenamento/transporte, conversão para America/Sao_Paulo na borda

**Data:** 2026-06-21
**Status:** Aceito (implementado)
**Decisores:** Vinicius (proprietário)

## Contexto

Datas/horas vêm de duas origens: o **banco** (Oracle ATP, colunas `TIMESTAMP`,
`SYSTIMESTAMP`) e os **marketplaces** (Mercado Livre/Shopee, ISO com offset ou `Z`).
A apresentação no frontend estava **inconsistente**: cada tela reimplementava sua
própria formatação com `new Date(x).toLocaleString('pt-BR')` **sem `timeZone`** — ou
seja, renderizava no fuso do **navegador**, não num fuso fixo. Strings *naive* (sem
offset) eram reinterpretadas pelo `Date` como horário local do cliente. Resultado:
horários errados em telas como **Dashboard Marketplace** e **Análise de Concorrência**,
e bugs de *off-by-one* em cálculos de "hoje"/intervalos feitos via `toISOString()`
(meia-noite UTC ≠ meia-noite BRT — perto da virada do dia, o dia muda).

O Brasil (America/Sao_Paulo) está em **UTC-3 fixo** desde o fim do horário de verão
em 2019.

## Decisão

**Armazenar e transportar SEMPRE em UTC (aware); converter para o horário do Brasil
(America/Sao_Paulo) SÓ na borda — exibição e cálculos/filtros locais — através de uma
fonte única em cada lado.**

- **Frontend — fonte única:** [`FRONTEND/src/utils/formatters.js`](../../FRONTEND/src/utils/formatters.js)
  - `parseDate` / `formatDate` / `formatDateTime` / `formatTime`: usam
    `Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', ... })` — fuso fixo,
    independente do navegador.
  - Regras de parsing: `"YYYY-MM-DD"` (só-data) é **dia-calendário literal** (sem
    conversão de fuso → sem off-by-one); datetime **com** offset/`Z` é instante
    absoluto; datetime **sem** offset (*naive*) é tratado como **UTC** (espelha o
    armazenamento).
  - `brToday()` / `brDaysAgo(n)`: "hoje"/N dias atrás no fuso do Brasil via
    `Intl en-CA` (nunca `toISOString().slice(0,10)`, que usa UTC).
  - `brInputToUtcIso()`: input local (`datetime-local`, entendido como BRASIL) → ISO UTC
    para enviar ao backend.
- **Backend — fonte única:** [`BACKEND/services/datetime_br.py`](../../BACKEND/services/datetime_br.py)
  - `now_utc()` (aware, em vez de `datetime.utcnow()` naive), `now_br()`, `ensure_aware()`
    (naive → UTC), `to_br()`, `to_utc()`, `iso_utc()` (contrato de serialização: UTC
    `...+00:00`), `parse_marketplace_dt()` (ISO de marketplace, `Z`→`+00:00`, nunca levanta).
  - `BR_TZ = ZoneInfo("America/Sao_Paulo")` — único ponto de definição do fuso;
    módulos que precisam do BRT importam daqui (`from services.datetime_br import BR_TZ`).

## Consequências

- Telas exibem sempre o horário do Brasil, independente do fuso do cliente.
- Filtros de data (ex.: pedidos `date_from`/`date_to`, Campaign Ads) interpretam a
  data escolhida como **dia local do Brasil** e convertem para UTC na consulta — não
  cortam mais as últimas 3h do dia.
- Quem precisar de data/hora **não** reimplementa: usa os helpers. `datetime.utcnow()`
  (naive), `ZoneInfo("America/Sao_Paulo")` espalhado e `toISOString().slice(...)` para
  "hoje" são anti-padrões a evitar.
- Relação com [ADR-0006](ADR-0006-metricas-marketplace-live-vs-snapshot.md): preservada.
  As janelas do snapshot diário continuam em `metric_date` como **data-calendário BRT**;
  `orders.created_at` continua comparado em **UTC**; só `generated_at` passou a ISO-UTC
  (metadado, não métrica).

## Dívida conhecida (follow-up, fora do caminho crítico)

- `datetime.utcnow()` (naive) ainda presente em módulos fiscais (`invoices.py`,
  `fiscal_config.py`, `dfe_service.py`, `focus_service.py`, `fiscal_alerts.py`). São
  **escritas** de UTC wall-clock — a fonte única do frontend já as exibe corretamente
  (naive → UTC). Migrar para `now_utc()` exige checar cada call-site por subtração/
  comparação naive-vs-aware antes de trocar (risco de `TypeError`). Não bloqueia.
- `parse_marketplace_dt()` pode substituir a lógica duplicada
  `fromisoformat(...replace("Z","+00:00"))` em ~15 call-sites (webhooks, sync). Refator
  de higiene, sem mudança de comportamento.

# 📊 Campanhas ADS — Documentação de Telas e API do Mercado Livre

> Documento técnico para construção do módulo **Métricas > Campanhas ADS** em sistemas integrados ao Mercado Livre.  
> Baseado na análise visual do Mercado Turbo (v6.1.30) e na documentação oficial da API ML (atualizada em 18/02/2026 e 19/05/2026).

---

## Índice

1. [Visão Geral da Tela](#1-visão-geral-da-tela)
2. [Estrutura de Abas — Tipos de Campanha](#2-estrutura-de-abas--tipos-de-campanha)
3. [Aba PRODUCT — Filtrar Campanhas](#3-aba-product--filtrar-campanhas)
4. [Aba PRODUCT — Filtrar Anúncios](#4-aba-product--filtrar-anúncios)
5. [Aba CATÁLOGO/UP](#5-aba-catálogoup)
6. [Aba DISPLAY](#6-aba-display)
7. [Aba BRAND](#7-aba-brand)
8. [API do Mercado Livre — Autenticação e Anunciantes](#8-api-do-mercado-livre--autenticação-e-anunciantes)
9. [API — Product Ads — Campanhas](#9-api--product-ads--campanhas)
10. [API — Product Ads — Anúncios (Ads)](#10-api--product-ads--anúncios-ads)
11. [API — Product Ads — Ad Groups (Catálogo/UP)](#11-api--product-ads--ad-groups-catálogoup)
12. [Cálculos e Métricas Derivadas](#12-cálculos-e-métricas-derivadas)
13. [Glossário Completo de Métricas](#13-glossário-completo-de-métricas)

---

## 1. Visão Geral da Tela

A tela **Campanhas ADS** é o hub central de publicidade. O cabeçalho sempre exibe:

- **Título:** "Campanhas ADS" com ícone de interrogação (tooltip explicativo)
- **Tipo ativo:** Nome do tipo de campanha (ex: `Product Ads`, `Catálogo & Variações`, `Display Ads`, `Brand Ads`) com ícone e descrição curta
- **Contador:** Quantidade de campanhas/grupos do anunciante
- **Anunciante ativo:** Nome e ID (ex: `MADE_IN_GROUP - 1141188`)

### Layout Geral
┌─────────────────────────────────────────────────────────────────┐
│  Campanhas ADS  (??) │ 📦 Product Ads — descrição · N campanhas │
├─────────────────────────────────────────────────────────────────┤
│  [PRODUCT]  [CATÁLOGO/UP]  [DISPLAY]  [BRAND]                   │
├─────────────────────────────────────────────────────────────────┤
│  [FILTRAR CAMPANHAS]  [FILTRAR ANÚNCIOS]   (subabas)            │
├─────────────────────────────────────────────────────────────────┤
│  Filtros: Anunciante | Campanha | Status | Período | [Filtrar]  │
├─────────────────────────────────────────────────────────────────┤
│  Métricas Globais (cards resumo)                                 │
├─────────────────────────────────────────────────────────────────┤
│  ⚡ Insights Automáticos                                          │
├─────────────────────────────────────────────────────────────────┤
│  Lista de Campanhas (expansível)                                 │
└─────────────────────────────────────────────────────────────────┘

---

## 2. Estrutura de Abas — Tipos de Campanha

A navegação principal possui 4 abas, cada uma representando um produto do Mercado Ads:

| Aba | Ícone | Descrição exibida |
|---|---|---|
| **PRODUCT** | 📦 | Product Ads — Anúncios patrocinados de produtos no marketplace |
| **CATÁLOGO/UP** | 📚 | Catálogo & Variações — Grupos de famílias e catálogos de produtos |
| **DISPLAY** | 🖥️ | Display Ads — Banners e formatos visuais em posições premium |
| **BRAND** | 👑 | Brand Ads — Campanhas de marca com posicionamento exclusivo nas buscas |

> **Nota de implementação:** O estado vazio de DISPLAY e BRAND exibe uma tela de onboarding com 3 passos ("Defina seu objetivo" → "Crie sua campanha no Mercado Ads" → "Acompanhe a performance aqui") e um botão que redireciona para o Mercado Ads.

---

## 3. Aba PRODUCT — Filtrar Campanhas

### 3.1 Filtros disponíveis

| Campo | Tipo | Opções / Comportamento |
|---|---|---|
| **Anunciante** | Select | Lista de anunciantes do usuário (via API) |
| **Campanha** | Select | "Todas" + lista de campanhas do anunciante (ID + Nome) |
| **Status Campanha** | Select | `Todos`, `Ativa`, `Pausada` |
| **Período** | Date Range | Padrão: últimos 30 dias. Formato `DD/MM/AAAA – DD/MM/AAAA` |
| **Filtrar** | Botão | Dispara a consulta com os parâmetros selecionados |

### 3.2 Cards de Métricas Globais (Totalizadores)

Exibidos em linha horizontal, respondem ao período e filtros selecionados. Dados somados de todas as campanhas filtradas.

| Card | Campo API | Descrição visual |
|---|---|---|
| **RECEITA** | `total_amount` | Valor em BRL. Subtítulo: `R$ X,XX/clique` |
| **CUSTO** | `cost` | Valor em BRL. Percentual sobre receita. Subtítulo: `CPC R$ X,XX` |
| **LUCRO** | `total_amount - cost` | Valor e %. Subtítulo: `N un. vendidas` |
| **SOV** | `sov` | Percentual. Subtítulo: `Share of Voice` |
| **IMPRESSÕES** | `prints` | Número formatado. Subtítulo: `X/venda` |
| **CLIQUES** | `clicks` | Número. Subtítulo: `CTR X,XX%` |
| **ROAS** | `roas` | Formato `X,XXx`. Subtítulo: `XX% da meta` (com cor verde/vermelho) |
| **ACOS** | `acos` | Formato `X,XX%`. Subtítulo: `XXX% da meta` (com cor verde/vermelho) |

> **Lógica de cor do ROAS:** Verde se ≥ meta, vermelho se < meta.  
> **Lógica de cor do ACOS:** Verde se ≤ meta, vermelho se > meta.

### 3.3 Bloco de Insights Automáticos

Seção com fundo colorido (ícone ⚡) que exibe 4 cards de análise automática:

| Insight | Conteúdo |
|---|---|
| **ROAS** | Destaca campanha com maior ROAS e alerta sobre campanhas abaixo da meta |
| **ACOS** | Indica campanhas dentro/fora da meta. Destaca a melhor |
| **ORGÂNICO VS PAGO** | Compara vendas orgânicas vs pagas (quantidade e valor) |
| **TICKET MÉDIO** | Ticket médio da campanha e CPA geral |

> **Implementação:** Estes insights são calculados no frontend com base nos dados retornados pela API. Não há endpoint dedicado para eles.

### 3.4 Lista de Campanhas

Exibe `EXIBINDO N CAMPANHAS`. Cada linha contém:

**Cabeçalho da linha (colapsada):**
[👁] Nome da Campanha  [ATIVA/PAUSADA]  PROFITABILITY · ID XXXXXXX
ROAS    ACOS    RECEITA   CUSTO   LUCRO(i)
X,XXx   X,XX%   R$ X,XX   R$ X,XX  R$ X,XX

**Detalhe expandido (ao clicar no 👁):**

Linha 1 — Métricas financeiras:
RECEITA       CUSTO         LUCRO(i)      ROAS          ACOS          UN. VENDIDAS
R$ X,XX       R$ X,XX       R$ X,XX       X,XXx         X,XX%         N
X% dir/ind    CPC R$ X,XX   XX% margem    XX% meta      XX% meta      CPA R$ X,XX

Linha 2 — Métricas de tráfego:
IMPRESSÕES    CLIQUES       SOV           VENDAS ORG.   TICKET MÉDIO  CVR
X.XXX         N             XX,XX%        N – R$ X,XX   R$ X,XX       XX,XX%
X/un. vendida CTR X,XX%     Share of Voice               por venda     clique→venda

**Seção Metas de Performance (barra de progresso):**
ROAS:  [████████████████░░░] X,XXx / XX,XXx
ACOS:  [████░░░░░░░░░░░░░░░] X,XX% / X,XX%

**Seção Funil de Conversão (barras horizontais):**
Impressões  [████████████████████] X.XXX
Cliques     [██░░░░░░░░░░░░░░░░░░] N
Conversões  [█░░░░░░░░░░░░░░░░░░░] N
CTR         X,XX%   CVR   XX,XX%   CPC   R$ X,XX

---

## 4. Aba PRODUCT — Filtrar Anúncios

### 4.1 Filtros disponíveis

| Campo | Tipo | Comportamento |
|---|---|---|
| **Campanha** | Select | Lista de campanhas do anunciante + "Todas" |
| **Status dos Anúncios** | Select | `Todos`, `Ativo`, `Pausado` |
| **Período** | Date Range | Padrão: últimos 30 dias |
| **Filtrar** | Botão | Dispara a consulta |

### 4.2 Barra de Totalizadores da Visão de Anúncios

Exibida acima da tabela, em formato de tags/chips:
CVR X,XX%  |  🛍️ Orgânico N un. vendidas  |  ↓ Direto R$ X,XX  |  ↔ Indireto R$ X,XX
$ Receita R$ X,XX  |  🗂️ Custo R$ X,XX  |  💰 Lucro Ads R$ X,XX  |  % Margem X,XX%

### 4.3 Tabela de Anúncios

Colunas da tabela (com ordenação):

| Coluna | Campo API | Descrição |
|---|---|---|
| **ANÚNCIO** | `title` + `item_id` | Nome e código MLB do anúncio |
| **CAMPANHA** | `campaign_id` | ID da campanha |
| **STATUS** | `status` | Badge colorido: `Ativo` (verde) / `Suspenso` (vermelho) |
| **CLIQUES** | `clicks` | Total de cliques |
| **IMPRESSÕES** | `prints` | Total de impressões |
| **CTR** | `ctr` | Taxa de cliques (%) |
| **CUSTO** | `cost` | Investimento em BRL |
| **CPC** | `cpc` | Custo por clique |
| **CPA** | calculado: `cost / units_quantity` | Custo por aquisição |
| **QTD. VENDIDOS** | `units_quantity` | Unidades vendidas |
| **RECEITA** | `total_amount` | Receita total |
| **ACOS** | `acos` | % de custo sobre receita |
| **Ação** | — | Ícone 👁 "Raio-X do Anúncio" |

**Paginação:** 1 | 20 | 50 | 100 | 200 por página. Exibe `1-N de TOTAL`.

---

## 5. Aba CATÁLOGO/UP

Estrutura idêntica à aba PRODUCT, porém os dados representam **grupos de famílias** (Ad Groups) em vez de campanhas individuais.

### 5.1 Filtros

| Campo | Tipo | Comportamento |
|---|---|---|
| **Anunciante** | Select | Lista de anunciantes |
| **ID da Família** | Input texto | Filtro por `family_id` (ex: `3687571...`) |
| **ID da Variação** | Input texto | Filtro por `item_id` de variação (ex: `MLBU...`) |
| **ID do Anúncio** | Input texto | Filtro por `item_id` (ex: `MLB...`) |
| **Status** | Select | `Todos`, `Ativo`, `Pausado` |
| **Período** | Date Range | Padrão: últimos 30 dias |
| **Filtrar** | Botão | Dispara consulta |

### 5.2 Cards de Métricas Globais

| Card | Campo API | Descrição |
|---|---|---|
| **RECEITA** | `total_amount` | Valor BRL. Subtítulo: `Total atribuído ao período` |
| **CUSTO** | `cost` | % sobre receita. Subtítulo: `Investimento em ADS` |
| **LUCRO** | `total_amount - cost` | Valor e %. Subtítulo: `N un. vendidas` |
| **GRUPOS ATIVOS** | contagem dos `status: active` | Exibe `N de TOTAL` e `100% do total` |
| **ANÚNCIOS** | soma de `advertising_items_quantity` | Número. Subtítulo: `média de N por grupo` |
| **UNIDADES VENDIDAS** | `units_quantity` | Subtítulo: `N variações` |
| **ROAS** | `roas` | Formato `X,XXx`. Subtítulo: `Retorno sobre o investimento` |
| **ACOS** | `acos` | Formato `X,XX%`. Subtítulo: `Custo sobre a receita` |

### 5.3 Lista de Grupos (Ad Groups)

Exibe `EXIBINDO N GRUPOS`. Cada linha contém:
[👁] Nome do Produto  [ATIVO]  FAMÍLIA · XXXXXXXXXXXX
ANÚNCIOS  VARIAÇÕES  ROAS      RECEITA    CUSTO    LUCRO
N         N          X,XXx     R$ X,XX    R$ X,XX  R$ X,XX

> **Legenda:** `FAMÍLIA` corresponde ao `family_id` retornado pela API de Ad Groups. É o identificador de agrupamento no novo fluxo de Catálogo/UP.

---

## 6. Aba DISPLAY

### Filtros

| Campo | Tipo |
|---|---|
| **Anunciante** | Select (anunciantes com produto DISPLAY) |
| **Campanha** | Select |
| **Status** | Select: `Todos`, `Ativo`, `Pausado`, `Encerrado` |
| **Modelo de atribuição** | Select: `Por data do evento (padrão)`, `Por data do clique/impressão` |
| **Período** | Date Range |

### Estado vazio (onboarding)

Quando não há campanhas Display ativas, exibe:
✨ PRONTO PARA COMEÇAR
Você ainda não tem campanhas ativas neste canal
[Criar Campanha no Mercado Ads] (link externo)
① Defina seu objetivo → ② Crie sua campanha no Mercado Ads → ③ Acompanhe a performance aqui
💡 Dicas antes de começar:

Comece com orçamento baixo para validar a oferta antes de escalar.
Catálogo / Variações ajuda a entender qual cor ou tamanho realmente vende.
Acompanhe o ACOS nas primeiras 72h — ajustes finos fazem diferença.
Brand Ads protege seu tráfego de marca contra concorrentes no leilão.


---

## 7. Aba BRAND

### Filtros

| Campo | Tipo |
|---|---|
| **Anunciante Brand** | Select |
| **Campanha** | Select |
| **Tipo** | Select: `Todos` + tipos de Brand Ads |
| **Status** | Select: `Todos`, `Ativo`, `Pausado` |
| **Loja Oficial** | Select |
| **Período** | Date Range |

> Estado vazio idêntico ao DISPLAY.

---

## 8. API do Mercado Livre — Autenticação e Anunciantes

### 8.1 Autenticação

Todas as chamadas exigem `Authorization: Bearer $ACCESS_TOKEN` no header.  
A versão da API é definida pelo header `api-version: 2` (exceto o endpoint de anunciantes, que usa `Api-Version: 1`).

### 8.2 Consultar Anunciantes

**Endpoint:**
GET https://api.mercadolibre.com/advertising/advertisers?product_id={PRODUCT_ID}

**Headers:**
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json
Api-Version: 1

**Parâmetro obrigatório:**
- `product_id`: `PADS` (Product Ads) | `DISPLAY` | `BADS` (Brand Ads)

**Resposta:**
```json
{
  "advertisers": [
    {
      "advertiser_id": 1141188,
      "site_id": "MLB",
      "advertiser_name": "MADE_IN_GROUP",
      "account_name": "MLB - MADE_IN_GROUP"
    }
  ]
}
```

**Campos:**
- `advertiser_id` → ID usado em todas as demais chamadas
- `site_id` → `MLB` para Brasil
- `advertiser_name` → Nome do anunciante (exibido nos filtros)
- `account_name` → Nome da conta

> **Erro 404:** "No permissions found for user_id" → usuário sem Product Ads habilitado.

---

## 9. API — Product Ads — Campanhas

### 9.1 Listar Todas as Campanhas com Métricas

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/advertisers/{ADVERTISER_ID}/product_ads/campaigns/search

**Headers:**
Authorization: Bearer {ACCESS_TOKEN}
api-version: 2

**Query params:**

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `limit` | int | Não | Máx. elementos. Padrão: 50 |
| `offset` | int | Não | Paginação. Padrão: 0 |
| `date_from` | string | Sim (se metrics) | Formato `YYYY-MM-DD` |
| `date_to` | string | Sim (se metrics) | Formato `YYYY-MM-DD` |
| `metrics` | string | Não | Lista separada por vírgula |
| `aggregation` | string | Não | Padrão: `sum` |
| `aggregation_type` | string | Não | `DAILY` para dados diários |
| `metrics_summary` | bool | Não | `true` para totalizador global |
| `filters[status]` | string | Não | `active`, `paused` |
| `filters[campaign_ids]` | string | Não | IDs separados por vírgula |

**Métricas disponíveis:**
clicks, prints, ctr, cost, cost_usd, cpc, acos,
organic_units_quantity, organic_units_amount, organic_items_quantity,
direct_items_quantity, indirect_items_quantity, advertising_items_quantity,
cvr, roas, sov, direct_units_quantity, indirect_units_quantity,
units_quantity, direct_amount, indirect_amount, total_amount

**Exemplo de chamada:**
```bash
curl -X GET \
  -H 'Authorization: Bearer {ACCESS_TOKEN}' \
  -H 'api-version: 2' \
  'https://api.mercadolibre.com/advertising/MLB/advertisers/1141188/product_ads/campaigns/search?date_from=2026-05-15&date_to=2026-06-14&metrics=clicks,prints,ctr,cost,cpc,acos,organic_units_quantity,organic_units_amount,organic_items_quantity,direct_items_quantity,indirect_items_quantity,advertising_items_quantity,cvr,roas,sov,direct_units_quantity,indirect_units_quantity,units_quantity,direct_amount,indirect_amount,total_amount&metrics_summary=true'
```

**Resposta:**
```json
{
  "paging": { "offset": 0, "total": 4, "limit": 50 },
  "results": [
    {
      "id": 357722979,
      "name": "Campanha",
      "status": "active",
      "last_updated": "2026-05-01T10:00:00.000Z",
      "date_created": "2025-11-01T10:00:00.000Z",
      "strategy": "PROFITABILITY",
      "acos_target": 5.0,
      "roas_target": 20.0,
      "channel": "marketplace",
      "advertiser_id": 1141188,
      "budget": 500.0,
      "automatic_budget": false,
      "metrics": {
        "clicks": 7,
        "prints": 2357,
        "ctr": 0.30,
        "cost": 1.82,
        "cpc": 0.26,
        "acos": 1.32,
        "roas": 76.02,
        "sov": 13.64,
        "cvr": 42.86,
        "total_amount": 138.35,
        "direct_amount": 138.35,
        "indirect_amount": 0.0,
        "units_quantity": 3,
        "direct_units_quantity": 3,
        "indirect_units_quantity": 0,
        "organic_units_quantity": 21,
        "organic_units_amount": 874.0
      }
    }
  ],
  "metrics_summary": {
    "clicks": 41,
    "prints": 8416,
    "cost": 7.33,
    "roas": 18.87,
    "acos": 5.30,
    "sov": 3.41,
    "total_amount": 138.35
  }
}
```

### 9.2 Detalhes de uma Campanha Específica

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/product_ads/campaigns/{CAMPAIGN_ID}

**Métricas extras disponíveis apenas neste endpoint:**
impression_share, top_impression_share,
lost_impression_share_by_budget, lost_impression_share_by_ad_rank,
acos_benchmark

**Estratégias possíveis (`strategy`):**
- `PROFITABILITY` — Foco em rentabilidade (ROAS/ACOS objetivo)
- `INCREASE` — Foco em aumentar vendas
- `VISIBILITY` — Foco em visibilidade/alcance

---

## 10. API — Product Ads — Anúncios (Ads)

### 10.1 Buscar Todos os Anúncios com Métricas

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/advertisers/{ADVERTISER_ID}/product_ads/ads/search

**Headers:** `api-version: 2`

**Parâmetros adicionais (além dos de campanhas):**

| Parâmetro | Valores | Descrição |
|---|---|---|
| `sort` | `asc`, `desc` | Direção da ordenação |
| `sort_by` | nome do campo | Campo de ordenação (ex: `clicks`, `roas`) |
| `aggregation_type` | `DAILY`, `item` | Padrão: `item` |
| `filters[item_id]` | `MLB...` | Filtrar por ID do anúncio |
| `filters[statuses]` | `active,paused,hold,idle` | Filtrar por status |
| `filters[campaign_id]` | int | Filtrar por campanha |
| `filters[buy_box_winner]` | bool | Apenas vencedores do buy box |
| `filters[recommended]` | bool | Apenas anúncios recomendados |
| `filters[domains]` | string | Filtrar por domínio |
| `filters[logistic_types]` | string | Tipo de logística |

**Resposta por anúncio (campos principais):**
```json
{
  "item_id": "MLB4732966407",
  "campaign_id": 357839309,
  "ad_group_id": 1105406861,
  "title": "Rolo De Massagem 30 Cm Laranja-claro",
  "status": "active",
  "price": 49.90,
  "catalog_listing": false,
  "logistic_type": "xd_drop_off",
  "listing_type_id": "gold_special",
  "domain_id": "MLB-SPORTS_ACCESSORIES",
  "buy_box_winner": false,
  "condition": "new",
  "current_level": "unknown",
  "thumbnail": "http://...",
  "permalink": "https://...",
  "recommended": false,
  "family_id": 3824221379336018,
  "metrics": {
    "clicks": 0,
    "prints": 0,
    "cost": 0.00,
    "cpc": 0.00,
    "acos": 0.00,
    "roas": 0.00,
    "units_quantity": 0,
    "total_amount": 0.00
  }
}
```

**Status possíveis do anúncio:**
| Status | Significado |
|---|---|
| `active` | Anúncio ativo na campanha |
| `paused` | Pausado pelo vendedor |
| `hold` | Desabilitado (item pausado ou sem estoque no ML) |
| `idle` | Disponível mas em nenhuma campanha |
| `delegated` | Emprestado a outro advertiser |
| `revoked` | Devolvido ao dono |

### 10.2 Métricas de Anúncios de uma Campanha Específica

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/advertisers/{ADVERTISER_ID}/product_ads/campaigns/{CAMPAIGN_ID}/ads/metrics

**Útil para o "Raio-X do Anúncio" por campanha.**

---

## 11. API — Product Ads — Ad Groups (Catálogo/UP)

> Novo fluxo para anúncios de Catálogo e User Products. Usa `ad_group_id` como identificador central.

### 11.1 Buscar Ad Group por Item

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/advertisers/{ADVERTISER_ID}/product_ads/ads/search?filters[item_id]={ITEM_ID}

Retorna o campo `ad_group_id` e `family_id` no resultado.

### 11.2 Detalhe de um Ad Group

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/product_ads/ad_groups/{AD_GROUP_ID}

**Com métricas:**
GET /advertising/MLB/product_ads/ad_groups/{AD_GROUP_ID}?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&metrics=CLICKS,PRINTS,COST,CPC,CTR,DIRECT_AMOUNT,INDIRECT_AMOUNT,TOTAL_AMOUNT,...

**Campos de resposta relevantes:**
```json
{
  "id": 976667081,
  "ad_group_type": "FAMILY",
  "title": "Rolo Liberação Miofascial",
  "campaign_id": 357839309,
  "catalog_listing": true,
  "ad_group_external_id": "3824221379336018",
  "status": "ACTIVE",
  "metrics": { ... }
}
```

**Tipos de `ad_group_type`:**
| Tipo | Identificador externo |
|---|---|
| `CATALOG` | `parent_id` do item de catálogo |
| `FAMILY` | `family_id` do User Product |
| `ITEM` | `item_id` tradicional |

### 11.3 Buscar Todos os Ad Groups de um Anunciante

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/advertisers/{ADVERTISER_ID}/product_ads/ad_groups/search

**Filtros disponíveis:**
filters[ad_group_id], filters[statuses], filters[campaigns],
filters[original_advertiser_id], filters[q] (busca por nome),
filters[domains], filters[official_stores], filters[channel]

**Suporte a `metrics_summary=true`** para totalizar métricas de todos os grupos.

### 11.4 Anúncios de um Ad Group

**Endpoint:**
GET https://api.mercadolibre.com/advertising/{SITE_ID}/product_ads/ad_groups/{AD_GROUP_ID}/ads

Retorna todos os `item_id` (variações) pertencentes ao grupo, com suas métricas individuais.

---

## 12. Cálculos e Métricas Derivadas

As seguintes métricas são calculadas pelo frontend com base nos dados da API:

| Métrica | Fórmula | Exibição |
|---|---|---|
| **Lucro** | `total_amount - cost` | R$ X,XX (verde se positivo, vermelho se negativo) |
| **% Lucro (Margem)** | `(lucro / total_amount) * 100` | XX,XX% margem |
| **% Custo sobre Receita** | `(cost / total_amount) * 100` | Exibido ao lado do card CUSTO |
| **CPA** | `cost / units_quantity` | R$ X,XX |
| **Receita/Clique** | `total_amount / clicks` | R$ X,XX/clique |
| **Impressões/Venda** | `prints / units_quantity` | X.XXX/venda |
| **% da Meta (ROAS)** | `(roas / roas_target) * 100` | XX% da meta |
| **% da Meta (ACOS)** | `(acos / acos_target) * 100` | XX% da meta |
| **SOV (Share of Voice)** | `sov` (retornado direto) | X,XX% |
| **CVR (Taxa de Conversão)** | `(units_quantity / clicks) * 100` ou campo `cvr` | XX,XX% clique→venda |

---

## 13. Glossário Completo de Métricas

| Campo API | Nome exibido | Definição |
|---|---|---|
| `clicks` | CLIQUES | Cliques recebidos pelos anúncios no período |
| `prints` | IMPRESSÕES | Vezes que o anúncio foi exibido |
| `ctr` | CTR | Taxa de cliques: `clicks / prints * 100` |
| `cost` | CUSTO / INVESTIMENTO | Valor gasto em publicidade (BRL) |
| `cpc` | CPC | Custo por clique: `cost / clicks` |
| `acos` | ACOS | % investimento / receita: `cost / total_amount * 100` |
| `roas` | ROAS | Retorno sobre investimento: `total_amount / cost` |
| `sov` | SOV | Share of Voice: % vendas pagas / vendas totais |
| `cvr` | CVR | Taxa de conversão: `units_quantity / clicks * 100` |
| `total_amount` | RECEITA | Receita total atribuída (direta + indireta) |
| `direct_amount` | Receita Direta | Vendas do próprio anúncio clicado |
| `indirect_amount` | Receita Indireta | Vendas assistidas (clicou em outro item após ver o anúncio) |
| `units_quantity` | UN. VENDIDAS | Total de unidades vendidas (direto + indireto) |
| `direct_units_quantity` | Vendas Diretas | Unidades vendidas via clique direto |
| `indirect_units_quantity` | Vendas Indiretas / Assistidas | Unidades vendidas via influência indireta |
| `organic_units_quantity` | Vendas Orgânicas | Vendas sem publicidade no mesmo período |
| `organic_units_amount` | Receita Orgânica | Valor das vendas orgânicas |
| `direct_items_quantity` | Pedidos Diretos | Número de pedidos diretos |
| `indirect_items_quantity` | Pedidos Indiretos | Número de pedidos indiretos |
| `advertising_items_quantity` | Total Pedidos com Ads | `direct + indirect items` |
| `organic_items_quantity` | Pedidos Orgânicos | Número de pedidos sem publicidade |
| `impression_share` | Share de Impressões | % vezes exibido / total possível |
| `top_impression_share` | Share Top | Ganhos em primeiras posições |
| `lost_impression_share_by_budget` | Perdas por Orçamento | % não exibido por orçamento baixo |
| `lost_impression_share_by_ad_rank` | Perdas por Ranking | % não exibido por ranking inferior |
| `acos_benchmark` | ACOS Benchmark | ACOS objetivo usado por anúncios de alta performance |
| `acos_target` | Meta ACOS | ACOS objetivo definido na campanha |
| `roas_target` | Meta ROAS | ROAS objetivo definido na campanha (min: 1x, máx: 35x) |
| `strategy` | Estratégia | `PROFITABILITY`, `INCREASE` ou `VISIBILITY` |
| `budget` | Orçamento | Orçamento diário da campanha |
| `family_id` | ID da Família | Identificador do grupo de variações (User Products) |
| `ad_group_id` | ID do Ad Group | Identificador do agrupamento no novo fluxo |
| `ad_group_type` | Tipo de Ad Group | `CATALOG`, `FAMILY` ou `ITEM` |

---

## Observações Técnicas Importantes

### Limites da API
- Intervalo máximo de datas: **90 dias para trás**
- Dados atualizados às **10:00h GMT-3** diariamente
- Dados do dia atual: atualização a cada **15 minutos**
- Só é possível solicitar **um `aggregation_type` por vez**

### Endpoints Descontinuados (desde fev/2026)
Os seguintes endpoints **não devem mais ser usados:**
GET /advertising/product_ads/items/$ITEM_ID
GET /advertising/advertisers/$ADVERTISER_ID/product_ads/items
GET /advertising/product_ads/campaigns/$CAMPAIGN_ID
GET /advertising/advertisers/$ADVERTISER_ID/product_ads/campaigns
GET /advertising/product_ads/campaigns/$CAMPAIGN_ID/metrics
GET /advertising/product_ads/campaigns/$CAMPAIGN_ID/ads/metrics (versão antiga)
GET /advertising/product_ads/ads/search (versão antiga)

### Novo Fluxo (Catálogo/UP)
A partir de 2025/2026, o Mercado Livre unificou variantes em **Ad Groups**. O fluxo correto é:
1. Buscar `advertiser_id` via `/advertising/advertisers?product_id=PADS`
2. Buscar anúncios via `/product_ads/ads/search` → obter `ad_group_id`
3. Consultar Ad Group via `/product_ads/ad_groups/{ad_group_id}`
4. Consultar métricas das campanhas via `/product_ads/campaigns/search`

### Pré-requisitos para usar Product Ads
- Reputação **amarela ou superior**
- Mínimo de **15 dias** de cadastro no Mercado Livre
- Mínimo de **1 venda** (empresas) ou **10 vendas** (pessoas físicas)
- Sem faturas vencidas

Pronto! O documento está completo. Aqui um resumo do que foi mapeado e documentado:
O que foi explorado no Mercado Turbo:

As 4 abas de campanha (PRODUCT, CATÁLOGO/UP, DISPLAY, BRAND) com todos os filtros
Os cards de métricas globais totalizadores
O bloco de Insights
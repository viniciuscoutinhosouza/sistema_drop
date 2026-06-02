# ADR-0004 — Estoque: SSOT canônico + reserva FULL + snapshots diários

**Data:** 2026-06-01
**Status:** Aceito (Fase 1 + Fase 2.1–2.3 implementadas; Fase 2.4 em standby)
**Decisores:** Vinicius (proprietário)

## Contexto

A exibição de estoque do sistema vinha dos campos `qty_local`, `qty_full` e
`available_quantity` em `ProductListing` — snapshots gravados no último sync
ML, defasados em relação ao galpão real. Resultado: cards de Anúncio mostravam
"Local: 13 un." quando o produto tinha 4 disponíveis (resto reservado).

Mais grave: vendas FULL não passavam por reserva (pedido `shipping_mode='full'`
fazia `return` cedo no `reserve_stock`), então a janela "venda baixada →
shipped" ficava invisível — `FullStock.qty` só caía na hora do shipped, e o
card de Pedido mostrava o saldo errado por horas.

Sem trilha histórica contábil: não havia como responder "qual era meu estoque
em 31/12?" para fechamento fiscal.

## Decisões tomadas

### 1. SSOT (Single Source of Truth) canônico

- **Local (galpão MIG)** = `CatalogProduct.stock_quantity` / `reserved_quantity`
- **FULL (armazém ML)** = `FullStock.qty` / `FullStock.reserved_qty` (nova coluna)
- `ProductListing.qty_local`, `qty_full`, `available_quantity` continuam
  existindo como cache de **escrita** (alimentam sync ML), mas NÃO são usados
  para leitura na UI a partir da Fase 1.

### 2. Reserva FULL (Fase 1)

- Migration **81_full_stock_reserved.sql** adiciona `reserved_qty` em `full_stock`.
- `reserve_stock` agora reserva no FULL (em vez de `return` cedo): debita
  `full_stock.reserved_qty` e grava `movement_type='full_reserve'`.
- `release_reservation` libera com `full_unreserve`.
- `apply_full_order_shipped` debita `qty` e libera `reserved_qty` na mesma
  operação (parâmetro `release_reserved=True` em `_adjust_full_stock`).

### 3. Stock card centralizado (Fase 1)

- `services/stock_view.py` com `get_stock_card(db, product_type, product_id, account_id=None)`
  retorna o dict canônico (físico/reservado/disponível Local + FULL).
- Endpoint `GET /stock/card/{product_type}/{product_id}` expõe pra UI.
- `load_full_per_account_map(db, *, pg_ids, cmig_ids, account_ids)` para
  pré-carregamento em batch (sem N+1).

### 4. Snapshots diários + reconciliação (Fase 2.1–2.3)

- Migration **82_stock_snapshots.sql** cria tabela `stock_snapshots`.
- Job APScheduler `daily_stock_reconcile` (cron 02:30 UTC ≈ 23:30 BRT):
  1. Roda `recompute_reservations_from_movements` (reconciliação).
  2. UPSERT em `stock_snapshots` para cada produto com saldo não-zero.
- Endpoint `GET /stock/snapshots?product_type&product_id&from_date&to_date`
  permite consultar série histórica para relatório contábil.

## Decisões em standby

### Custo Médio Ponderado (Fase 2.4 — NÃO IMPLEMENTADO)

Substituir `cost_price` estático por `weighted_avg_cost` atualizado a cada
NF-e de entrada — clássico do método PEPS/UEPS/Médio Ponderado.

**Por que ficou em standby:**
1. Decisão **contábil**, não técnica — precisa alinhar com contador qual método
   adotar (Médio Ponderado, PEPS, ou UEPS).
2. Muda comportamento de todas as telas de margem/lucro (orders, dashboard,
   simulator, financial).
3. Requer reprocessamento histórico (recomputar custo médio retroativo a
   partir das NF-e antigas).
4. Pode coexistir com `cost_price` (opt-in por CMIG) — escopo a decidir.

**Próximo passo:** sessão dedicada com escopo definido pelo contador.

## Consequências

### Positivas

- Card "Local: 13" agora bate com o disponível real do galpão.
- Vendas FULL deixam de ser invisíveis na janela "baixada → shipped".
- Trilha histórica de estoque (`stock_snapshots`) permite fechamento contábil
  e relatórios "como era em DD/MM".
- Job de reconciliação diário corrige drifts de reservas automaticamente.

### Negativas

- 2 colunas novas + 1 tabela nova no Oracle (migrations 81 e 82 obrigatórias).
- Jobs APScheduler `sync_orders` e `sync_stock` agora precisam respeitar
  `reserved_qty` ao gravar `available_quantity` no ML — Fase 0 já garante
  que o cache `ProductListing.qty_full` ainda é gravado pelo sync, mas leitura
  na UI já passa pelo SSOT.

## Arquivos chave

- `BACKEND/services/stock_view.py` — SSOT central
- `BACKEND/services/stock_reservation_service.py` — reserva Local + FULL
- `BACKEND/services/full_stock_service.py` — apply_full_order_shipped libera reserved
- `BACKEND/routers/stock.py` — endpoints `/stock/card`, `/stock/snapshots`
- `BACKEND/tasks/daily_stock_reconcile.py` — job diário
- `BACKEND/models/full_stock.py` — `FullStock.reserved_qty` + property `available_qty`
- `BACKEND/models/stock_snapshot.py` — modelo da trilha contábil
- `Scripts SQL/81_full_stock_reserved.sql`
- `Scripts SQL/82_stock_snapshots.sql`

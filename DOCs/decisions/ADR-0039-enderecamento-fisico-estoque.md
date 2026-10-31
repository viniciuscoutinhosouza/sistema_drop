# ADR-0039 — Endereçamento Físico de Estoque como sub-ledger aditivo de localização

## Status
Aceita — Fase 1 em produção (2026-10-31, commit `01ac132`); Fase 2 (sugestão de picking) implementada (2026-10-31).

## Contexto
O galpão precisa organizar fisicamente onde cada produto fica. Há **vários modelos** de galpão:
salas com armários/estantes, estruturas de porta-pallet (estante → coluna → altura → pallet), e
galpões **mistos**. Existe uma **hierarquia do maior ao menor espaço**, e a identificação de cada
nível é **definida por ramo** (a Sala "Mickey" tem estantes 1..8; a "Pateta", 1..5; umas por letra
A..C, outras A..F). Produtos ficam em **caixas** homogêneas (5×12) ou heterogêneas (3×10 + 4×8 +
1×20), e podem ocupar **mais de um endereço** (com ordem de picking). Rastreáveis (lote/validade)
precisam ser agrupados/ordenados por FEFO no picking.

O estoque já é **escalar event-sourced** (ADR-0004) e os lotes são um **sub-ledger paralelo aditivo**
(ADR-0027). O risco de uma camada de localização é virar uma **segunda verdade** de saldo que diverge
do SSOT e quebrar estoque/fiscal.

## Decisão
Endereçamento como **camada ADITIVA de LOCALIZAÇÃO** — diz **ONDE** o estoque está, **reconcilia**
com o saldo escalar e **NUNCA grava saldo** (mesmo espírito do SEM-LOTE da ADR-0027).

### Modelo
- **Árvore de endereços** (`storage_locations`) por galpão: um só conceito cobre todos os modelos.
  `level_type` é **texto livre por nó** (Sala/Armário/Estante/Coluna/Altura/Pallet…), `code` é a
  identificação (nome/número/letra), `full_code` é derivado (caminho) e **recomputado na subárvore**
  quando um pai é renomeado. `is_storable` marca a folha que recebe produto. `area_kind`
  (pallet|cabinet|other) só na raiz da área → galpão misto = dois ramos. `pick_sequence` = rota.
  UNIQUE `(warehouse_id, full_code)`.
- **Alocação** (`product_allocations`): produto (±`lot_id`) num local, com `qty_units` e `pick_order`
  (ordem entre locais do mesmo produto). `product_type` = enum de stock_movements/traceability
  (`pg|cmig|variant_pg|variant_cmig`). UNIQUE `(location, product, NVL(lot,0))`.
- **Caixas** (`product_allocation_packs`): composição por alocação (N linhas = heterogênea); unidades
  soltas = `qty_units − Σ(box·upb)`. **Embalagem-padrão** reutilizável por produto
  (`product_pack_defaults`) sugere no modal, mas o endereço aceita composição livre.
- **Etiqueta/QR** (`storage_box_labels`): token no QR da caixa fechada → alocação (base da bipagem/
  contagem da Fase 2). Renderização de QR/código de barras no **frontend** (qrcode.js + jsbarcode via
  CDN) — **sem dependência nova no backend**.
- **Código interno** p/ produto sem EAN: `product_eans.source` (`ean|internal`); o interno é um
  **EAN-13 na faixa de uso interno (prefixo 2 + DV)**, reusa o matcher multi-EAN existente
  (ADR/migration 172). Único **só para `internal`** (índice funcional — UNIQUE global em `ean` seria
  regressão: dois galpões podem ter o mesmo EAN de fabricante). Gerar código interno **dispara
  recompute** do estoque (o replay passa a casar notas antigas por ele).

### Invariante
Σ `qty_units` ativas por produto **reconcilia** com `stock_quantity` LOCAL (ADR-0019; FULL fica de
fora — `full_stock` é outra tabela). Diferença = balde **"sem endereço"** (calculado na leitura).
**Kit** (ADR-0023, saldo derivado) é excluído do endereçamento e da reconciliação.

### Autorização (ADR-0036)
Capacidade = **permissão de ação editável por perfil** (`endereco_configurar` monta a árvore,
`endereco_movimentar` aloca/caixas/código/etiqueta; default `go`+`admin`, migration 174). **Escopo
por galpão** (ADR-0026) continua no `data_scope` (intocado): o galpão é **derivado do usuário**,
nunca confiado no path; toda resolução de id (location/allocation/produto/código) checa o galpão
(anti-IDOR cross-galpão). Leitura gateada por login+escopo, não por permissão de escrita.

## Faseamento
- **Fase 1 (esta):** estrutura (árvore) + alocação + caixas + mapa/consulta + reconciliação +
  etiqueta/QR + código interno. Migrations 173 (schema) / 174 (seed). Router `/api/v1/storage`.
- **Fase 2 (implementada):** SUGESTÃO de picking no `PickingCart` (ADR-0005) — **não debita** (débito
  é Fase 2.5). Ponto único `services/storage_picking.py::pick_plan_for` (ordenação em função PURA
  `order_allocations`, testável). **Precedência:** (1) FEFO rastreável — `expiry_date asc nulls_last,
  lot_id asc`, o MESMO ORDER BY do débito de lote (`traceability_service.allocate_fefo`), e alocação
  rastreável **sem lote identificado** vai para o fim (não finge validade); (2) `product_allocations.pick_order`
  (intenção manual por produto); (3) endereço com **unidade solta / caixa aberta primeiro** (preserva
  caixa fechada p/ contagem — pedido do dono); (4) `location.pick_sequence` (rota física); (5) `full_code`.
  Inclui alocações feitas no nível de **variante** do produto-base (senão apareceria "sem endereço"
  falso). `warehouse_id` derivado do próprio produto (`resolve_product_meta`), não do pedido. Rotas de
  LEITURA escopadas: `GET /storage/products/{pt}/{id}/pick-plan` e `GET /separation/carts/{id}/pick-plan`;
  coluna "Endereço (ordem)" no PDF da lista + painel "Rota de picking" na bipagem. Emenda a ADR-0005.
- **Fase 3:** inventário por endereço, transferência em massa, rastreio individual por caixa física.

## Consequências
- Zero regressão no motor de estoque/fiscal (nada grava saldo; tabelas nascem vazias).
- `services/product_scope.assert_pg_scope` extraído de `invoices.py` (ponto compartilhado).
- Código interno de **variante** não é suportado na Fase 1 (`product_eans` não tem FK p/ variante) —
  bloqueado com erro claro (fail-loud).
- Convive com ADR-0004 (escalar), ADR-0027 (lotes/FEFO), ADR-0005 (picking), ADR-0026 (escopo),
  ADR-0019 (FULL/local), ADR-0023 (kit derivado), ADR-0036 (capacidade por perfil).

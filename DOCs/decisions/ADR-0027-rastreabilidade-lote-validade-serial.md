# ADR-0027 — Produtos rastreáveis (lote/validade/serial/medicamento) como sub-ledger paralelo aditivo

**Data:** 2026-09-25
**Status:** Aceito (Fase 1 em implementação)
**Decisores:** Vinicius (proprietário)

## Contexto

O estoque do Sistema Drop é **event-sourced escalar** (ADR-0004): `stock_quantity` é cache
recomputado por replay de NF-e + pedidos + inventário; a saída de venda é **dirigida pelo pedido**
(a NF-e vinculada é regularização fiscal, não debita — ADR-0019). Não existia nenhuma noção de
lote/validade/serial: toda quantidade é escalar por SKU.

O dono pediu **produtos rastreáveis** por **lote**, **validade**, **número serial** e **medicamento**
(grupo fiscal `<med>`), combináveis (0, 1 ou vários por produto). A Fase 0 (fiscal + Mercado Livre)
estabeleceu:
- `<rastro>` (grupo I80 do MOC NF-e 4.00, NT 2016.002) carrega nLote/qLote/dFab/dVal/cAgreg; é
  **obrigatório por NCM** (lista versionada por NT — nunca hardcode). `<med>` (grupo K, NT 2018.005)
  carrega cProdANVISA/xMotivoIsencao/vPMC; medicamento leva **os dois** grupos. Serial de produto
  comum **não tem campo fiscal** → `infAdProd`.
- O **Faturador ML** e a **Shopee (Invoice Issuer)** **não** aceitam lote/validade na nota → o
  `<rastro>` só é possível nas **notas de emissão própria** (ADR-0015).

## Decisões travadas pelo dono

1. **Rastreável ⇒ NF-e SOMENTE por emissão própria** (nunca Faturador ML, nunca Shopee Invoice Issuer).
2. **Rastreável ⇒ NUNCA vai ao FULL.**
3. Saída: **FEFO sugere + operador confirma**; serial por bipagem.

## Decisão central

Rastreabilidade é um **sub-ledger paralelo e ADITIVO** por cima do estoque escalar SSOT.
O `stock_calculator` (motor de replay escalar) fica **intocado**. O escalar responde "**quantas**";
o sub-ledger de lotes/seriais responde "**quais**". Produto default = não rastreável ⇒ **zero regressão**.

**Invariante (por balde):** `Σ product_lots.<balde> == <produto>.<balde>` para cada um dos 5 baldes
(balance/reserved/awaiting_return/pending_validation/unfit). Reconciliável, com detecção de drift no
`daily_stock_reconcile` (mesmo padrão do snapshot).

## Regras de coerência (fruto da auditoria quality-guardian + consistency-auditor + adr-consistency-checker)

- **Baixa do lote é ORDER-DRIVEN/REPLAY**, nunca picking-driven. O picking só *escolhe* o lote
  (FEFO sugerido / serial bipado); a baixa ocorre no mesmo gatilho canônico do escalar (pedido
  shipped/delivered). Vendas sem picking (Shopee, ML Flex, webhook) recebem **FEFO automático
  server-side**, gravando `stock_lot_allocations` idempotente por order_item. Vale igual para
  **pedido de marketplace e pedido manual** (ambos são `Order`; a baixa é agnóstica de plataforma,
  exceto FULL que rastreável não usa).
- **`product_lots` é cache 100% derivado por replay** (`recompute_lots`), espelhando o
  `stock_calculator` **termo a termo** (entrada gated por `stock_updated` ADR-0009; retorno-apto por
  contador direto em `validate_return_items`, fora do replay fiscal; âncora de inventário). A emissão
  fiscal lê a **alocação imutável**, nunca o cache transitório.
- **5 baldes por lote** espelham o escalar; `balance` sobe só no APTO (nunca receive/unfit — ADR-0009).
  A alocação tem `status` no ciclo de vida para mover o lote certo entre baldes na devolução/cancelamento.
- **Devolução de rastreável EXIGE escolha de lote** antes de voltar ao vendável (falhar alto; crítico
  p/ validade — não revender vencido).
- **Guards em ponto único** (ADR-0024): "nunca FULL" dentro de `resolve_full_cmig_product` (cobre
  incremental E replay) + `available_to_push`; "só emissão própria" dentro de `ml_service.emit_nfe`
  (cobre os emits automáticos de etiqueta/bundle). Predicado único `traceability_guard.is_traceable`.
- **Bloquear flag em produto composto (kit)** — rastreabilidade vive nos COMPONENTES; consumo de lote
  do componente na montagem (FEFO + alocação) preserva o recall (emenda ADR-0023).
- **Bloquear rastreável em conta CPF** — DC-e modelo 99 (ADR-0017) não carrega `<rastro>`/`<med>`.
- **Ligar a flag com FULL>0** = bloquear (drenar o FULL antes).
- **Backfill legado:** produto com saldo > 0 e zero lotes ao ligar a flag recebe lote sintético
  "DESCONHECIDO" (sem validade) carregando o saldo, para o invariante fechar no dia 1.
- **Variante:** entrada resolve a variante por `InvoiceItem.sku → variant.sku`; crédito vai para
  `product_type='variant_*'` (mesma chave da saída).
- **LGPD:** recall reverso de medicamento (lote→comprador) é dado de saúde (Art. 11) → permissão
  nomeada (ADR-0025) + retorna o pedido, não os dados pessoais do comprador salvo recall comprovado.
- **Regra de ouro Shopee (ADR-0020):** guards agnósticos por `is_traceable`, nunca dentro de
  `if platform == "mercadolivre"`; eShip com lote entra por ramo/rota novos.

## Expansão de escopo (emenda a ADR-0008/0015/0021)

A emissão própria (ADR-0015, antes só manual) passa a cobrir **pedidos de marketplace rastreáveis**.
O Faturador ML (ADR-0008/0021 "captura completa") **exclui** pedidos rastreáveis — senão geraria nota
dupla. Registrado aqui; ajustar a captura do Faturador na Fase 4.

## Modelo de dados (migration 143)

- Flags em `catalog_products`/`cmig_products`: `track_lot`, `track_expiry`, `track_serial` + campos
  medicamento `med_anvisa_code`, `med_pmc`, `med_exempt_reason`.
- `product_lots` (5 baldes, lot_code/mfg_date/expiry_date, por product_type incl. variantes).
- `product_serials` (serial + status + lot_id + order_id).
- `invoice_item_lots` / `invoice_item_serials` (rastro capturado da nota de entrada).
- `stock_lot_allocations` (alocação de saída por order_item, com status; UNIQUE anti-duplicação).
- `nfe_ncm_rastreavel` (parâmetro: NCM×UF×vigência exige rastro/med — carregado da NT, não hardcode).

## Faseamento

- **F1** modelo + flags + guards (zero comportamento). **F2** captura na entrada. **F3** saída interna
  (FEFO + serial). **F4** fiscal (`<rastro>`/`<med>`/`infAdProd`) + validação homologação. **F5** eShip.
  **F6** relatórios (kardex por lote, recall, a vencer, por serial, por ANVISA). **FULL fora.**

## Consequências

- **Positivas:** rastreabilidade ponta a ponta (nota entrada → lote → pedido → nota própria saída);
  recall bidirecional; FEFO; alerta de vencimento; conformidade fiscal do `<rastro>`/`<med>` nas notas
  próprias. Motor escalar intocado ⇒ baixo risco de regressão.
- **Negativas / responsabilidades:** dois replays em lockstep (drift a monitorar); medicamento real
  aciona ANVISA/SNCM (fora do xml_builder; contador); vPMC pode alimentar base ST por UF (parametrizar);
  cobertura dos guards precisa auditoria contínua; validação do gate ML **em produção** (refresh
  token single-use não roda no DEV).

## Refinamentos pós-auditoria (Fase 1 — migração 144)

- **Medicamento é rastreável por definição:** `is_traceable` (guard + properties) inclui
  `med_anvisa_code`. Regra enforçada: medicamento (com código ANVISA) **exige `track_lot`** ligado
  (o `<med>` acompanha o `<rastro>` — NT 2018.005). Fecha o buraco de um medicamento escapar dos guards.
- **Mapeamento de baldes (lote ↔ escalar):** `product_lots` usa `balance/reserved/awaiting_return/
  pending_validation/unfit`; o escalar usa `stock_quantity/reserved_quantity/…_quantity`. O
  `recompute_lots` (F2) faz o de-para 1:1 (`balance ↔ stock_quantity`, etc.).
- **Idempotência da alocação:** por `(order_id, product_type, product_id, lot_id)` (lote) e
  `(order_id, serial_id)` (serial) — sempre preenchidos, robusto a `order_item_id` NULL (webhook/manual).
- **Serial revendível:** unicidade por `(order_id, serial_id)` permite revender um serial devolvido
  num novo pedido (o ciclo de vida vive no `status`).
- **Variante:** as flags vivem no produto-pai; o saldo por lote pode ser por variante
  (`product_type='variant_*'`). A entrada resolve a variante por `InvoiceItem.sku → variant.sku`.
- **Pendente de fechamento (session-closer):** listar ADR-0027 no índice do `CLAUDE.md` e anotar
  "emendada por ADR-0027" em ADR-0008/0015/0021.

## Pendências

- Snapshot histórico por lote (contábil) — decidir se cria trilha própria (separada do escalar).
- cStat reais de rejeição rastro/med → homologação (tpAmb=2).
- Lista vigente de NCMs rastreáveis → carregar do anexo da NT + acréscimos de UF (RICMS).

## Referências
- ADR-0004 (SSOT event-sourced), ADR-0008 (Faturador), ADR-0009 (devolução/gate stock_updated),
  ADR-0010/0019 (FULL sempre CMIG/replay), ADR-0015 (emissão própria SEFAZ), ADR-0017 (DC-e CPF),
  ADR-0020 (regra de ouro Shopee), ADR-0023 (kit derivado), ADR-0024 (guard ponto único),
  ADR-0025 (permissões de ação).
- Design detalhado + auditoria: `design_rastreabilidade.md` + `design_rastreabilidade_v2.md` (scratchpad).

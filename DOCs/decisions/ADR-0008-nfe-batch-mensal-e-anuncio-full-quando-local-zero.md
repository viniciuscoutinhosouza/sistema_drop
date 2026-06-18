# ADR-0008 — Sincronização mensal de NF-e (batch ML) + anúncio não-FULL anuncia FULL quando LOCAL=0

**Data:** 2026-06-17
**Status:** Aceito (implementado — Fase A)
**Decisores:** Vinicius (proprietário)

> **Nota (ADR-0010):** a partir do ADR-0010, o estoque FULL é keyed SEMPRE por produto CMIG
> (`product_type='cmig'`). A redação PG-cêntrica abaixo (`full_stock` por pg/cmig) descreve o
> estado legado pré-migração; `available_to_push`/`available_for_product` agora resolvem o
> CMIGProduto espelho. A regra "anúncio não-FULL anuncia FULL quando LOCAL=0" permanece válida.

## Contexto

Duas decisões surgiram ao corrigir o furo de sequência de NF-e e a pausa indevida
de anúncios, e ambas tocam/estendem o ADR-0004 (Estoque SSOT):

1. **Furo de sequência:** a "Sincronizar NF-e do ML" era dirigida por pedido, então
   notas SEM pedido (remessa para o FULL, retorno, retirada) nunca eram importadas —
   furo na numeração fiscal.
2. **Pausa indevida:** após a remessa LOCAL→FULL, o anúncio não-FULL ficava com LOCAL=0
   e o push de estoque enviava 0 ao ML, que pausava o anúncio — mesmo havendo estoque
   no FULL.

## Decisões

### 1. Sincronização mensal de todas as NF-e via batch do Faturador ML (aditivo)

- `ml_service.download_invoices_batch` usa `GET /users/{seller}/invoices/sites/MLB/
  batch_request/period/stream` (`sale/return/full/others=all`) e baixa o zip de XMLs do mês.
- `routers/invoices._sync_ml_fiscal_account` (chamado pelo endpoint manual e pelo job
  diário `tasks/ml_fiscal_sync.sync_ml_fiscal_current_month`): por nota, dedup por chave;
  classifica como FULL via `is_full_cnpj(dest/emit)` e a **direção pela CFOP** (1º dígito
  1/2/3 = entrada → retorno do FULL = LOCAL↑+FULL↓; 5/6/7 = saída → remessa = LOCAL↓+FULL↑).
- **Vendas são PULADAS** (a baixa LOCAL da venda já vem do fluxo de pedido — não recriar
  para não duplicar). Devolução = Fase B (módulo de Devoluções). CC-e/CT-e não movem estoque.
- O movimento de estoque usa o **caminho event-sourced canônico** do ADR-0004
  (`_apply_stock_movement` → recompute) para o LOCAL e `apply_nfe_saida_to_full`/
  `apply_nfe_entrada_from_full` para o FULL. Idempotente (dedup chave + `_already_has_full_movement`
  + flag `stock_updated`). HTTP do zip FORA da sessão Oracle; 1 transação curta por nota;
  sequencial por conta (o batch é sensível a 429).
- Furos de sequência são detectados (números faltantes por série no lote) e logados.

### 2. Anúncio NÃO-FULL anuncia o disponível do FULL quando o LOCAL = 0 (exceção ao ADR-0004)

- O ADR-0004 define que o anúncio não-FULL reflete o estoque LOCAL e o FULL é gerenciado
  à parte. **Exceção adotada a pedido do usuário:** um anúncio só deve ser pausado quando
  LOCAL **e** FULL estão ambos zerados.
- `full_stock_service.available_to_push(db, listing)` (consumido por `tasks/sync_stock.
  _compute_product_stock` e `services/stock_sync_service._read_stock`): LOCAL = `stock_quantity
  - reserved_quantity`; se 0, retorna o disponível do FULL (`available_for_product`) —
  **mas só quando NÃO existir um anúncio is_full ativo** para o mesmo produto+conta (guard
  contra anunciar o mesmo saldo FULL em dois anúncios → venda dupla).

## Consequências

- **Positivas:** sequência fiscal fechada (remessas entram); anúncios não pausam à toa quando
  há estoque no FULL; movimento de estoque das remessas é canônico e idempotente; rotina diária
  auto-corrige (idempotente).
- **Negativas / riscos aceitos:**
  - O anúncio não-FULL, ao anunciar o saldo FULL com LOCAL=0, pode receber um pedido
    flex/agência que o galpão não tem fisicamente (oversell logístico) — o vendedor repõe do
    FULL (retirada). Mitigado pelo guard de "existe anúncio FULL ativo? então não duplica".
  - O batch do Faturador ML é instável sob carga (429/500) — tratado com retorno vazio/retry;
    por isso o processamento é sequencial e o job é diário e idempotente.
- **Fora de escopo (Fase B):** estoque de devolução (módulo de Devoluções, com apto/não-apto
  e nota de descarte) — ver fluxo descrito pelo usuário.

## Referências
- `BACKEND/services/ml_service.download_invoices_batch`
- `BACKEND/routers/invoices.py` (`_sync_ml_fiscal_account`, `import_xml_saida`, dedup `/outbound`)
- `BACKEND/tasks/ml_fiscal_sync.py` (job diário `sync_ml_fiscal`)
- `BACKEND/services/full_stock_service.py` (`available_to_push`, `available_for_product`,
  `apply_nfe_saida_to_full`, `apply_nfe_entrada_from_full`)
- ADR-0004 (Estoque SSOT) — esta decisão estende a regra de leitura do anúncio não-FULL.

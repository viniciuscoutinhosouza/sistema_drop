# ADR-0010 — Estoque FULL é sempre do produto CMIG (auto-criação de espelho do PG)

**Data:** 2026-06-18
**Status:** Aceito (implementado)
**Decisores:** Vinicius (proprietário)

## Contexto

O estoque FULL (`full_stock`, chave `(product_type, product_id, marketplace_account_id)`)
era gravado com a chave do produto **PG** quando a remessa casava o item por SKU/EAN
(`apply_nfe_saida_to_full`: `if cmig_product_id … elif catalog_product_id → 'pg'`), mas as
**vendas** reservavam contra a chave **CMIG** (`resolve_full_product` prefere CMIG). Em
produção isso gerou 27 linhas `product_type='pg'` (entradas das remessas, 953 un) e 3 linhas
`'cmig'` (125 reservadas das vendas): entrada e reserva em chaves diferentes → "Reserva FULL
sem entrada", e o FULL não isolável por CMIG. Além disso, 18 dos 27 produtos no FULL nem
existiam como CMIGProduct.

Regra de negócio (dono): **o FULL pertence à CMIG**. Um produto pode estar no PG ou no CMIG
no galpão, mas ao ir para o FULL ele é, obrigatoriamente, estoque FULL do CMIG. **Não existe
estoque FULL para PG.**

## Decisão

**Todo estoque FULL é keyed pelo produto CMIG** (`product_type='cmig'`). Nenhuma escrita nova
de FULL grava `'pg'`.

- Resolvedor único `services.full_stock_service.resolve_full_cmig_product(...)`: cmig_product_id
  direto → `ProductListing(ml_item_id, conta)` → `pg_product_id` dentro do CMIG → EAN/SKU dentro
  do CMIG → **auto-cria** o CMIGProduct espelhando o PG (nome/EAN/SKU→sku_cmig/dimensões/NCM,
  `pg_product_id` vinculado, `stock_quantity=0`). Re-SELECT + `flush` antes do INSERT
  (idempotência — não há unique em `(cmig_id, pg_product_id)`).
- `qty` (físico FULL) é mantido como **saldo incremental idempotente** (delta por movimento,
  idempotência via `stock_movements`/`order_id`), equivalente a Σ remessas REAIS (NF-e saída p/
  CNPJ FULL) − vendas enviadas (pedido FULL `shipped`) − retornos REAIS (NF-e entrada de CNPJ
  FULL). **Não há recompute event-sourced do FULL** (diferente do LOCAL/ADR-0004). Notas
  **simbólicas** não movem
  nada (ADR-0009 / `fiscal_rules.is_simbolica`). Venda reserva ao baixar e baixa no `shipped`
  (mantém o comportamento de reserva existente).
- O `cmig_id` no contexto de venda é derivado da conta (`Order.cmig_id` costuma ser NULL →
  `MarketplaceAccount.cmig_id`).
- Leitura: o card de um produto **PG** segue `pg_product_id` e exibe o FULL dos CMIGProduct
  espelho (`stock_view.load_full_per_account_map`), para anúncios PG não mostrarem FULL=0.
- **Conferência** (`POST /stock/cmig/{id}/sync-full`): deixou de sobrescrever cegamente o
  `qty` com o `available_quantity` do ML. Agora COMPARA o disponível do sistema (qty − reserved,
  por produto CMIG/conta) com o do ML e reporta `drift`; havendo divergência, dispara em
  background a re-sincronização das NF-e do mês (que ajusta o `qty`).
- Detecção de furos de sequência de NF-e (`_sync_ml_fiscal_account`) passou a ser **cross-mês**:
  une os números do lote com os já persistidos por série/CMIG no banco e acha o que falta.

## Consequências

- Entrada (remessa) e reserva (venda) caem na MESMA chave CMIG → FULL correto e isolável por
  CMIG. Itens que só existiam no FULL aparecem na linha do CMIGProduct espelho (mudança de UX
  na tela de Controle de Estoque: o FULL migra da linha PG para a linha CMIG).
- Migração one-off idempotente `POST /stock/migrate-full-pg-to-cmig` (dry_run default): converte
  as linhas PG→CMIG (auto-criando os espelhos), agrega por `(cmig_product, conta)` preservando
  `reserved_qty`, e registra movimento `full_migrate`. Histórico de movimentos FULL legado
  permanece na chave PG (não reescrito).
- O ML deixa de ser fonte de verdade do FULL (passa a ser conferência), alinhado a "para Full,
  não atualize estoque manualmente; o estoque vem das notas". `available_for_product`/
  `available_to_push` resolvem o CMIG espelho para anúncios só-PG (sem criar) — preserva a regra
  do ADR-0008 (não pausar quando LOCAL=0 mas FULL>0).
- ADR-0004 (event-sourcing LOCAL) e ADR-0009 (simbólicas) preservados.
- **Leitura legada de chave `'pg'`**: até a migração `/migrate-full-pg-to-cmig` rodar com
  `dry_run=false`, `available_for_product` e os leitores ainda contemplam linhas
  `product_type='pg'` (rede de segurança pré-migração). Após a migração, essas linhas deixam
  de existir.
- **Retorno (`apply_nfe_entrada_from_full`) usa `create=False`**: se um retorno chegar para um
  produto cujo CMIGProduto espelho ainda não existe (nenhuma remessa/venda anterior o
  materializou), o débito é descartado com `warning` (não há saldo FULL a debitar). Caso de
  borda conhecido e aceitável.
- Índice único `uix_cmigprod_cmig_pg(cmig_id, pg_product_id)` (migração 100) garante 1 espelho
  por (cmig, pg) também sob concorrência (re-SELECT+flush sozinho não barra inserts paralelos).

## Referências
- `BACKEND/services/full_stock_service.py` (`resolve_full_cmig_product`, `_cmig_id_for_account`,
  `apply_nfe_saida_to_full`, `apply_nfe_entrada_from_full`, `resolve_full_product`, `available_*`)
- `BACKEND/services/stock_view.py` (`load_full_per_account_map` segue `pg_product_id`)
- `BACKEND/routers/stock.py` (`/sync-full` conferência, `/migrate-full-pg-to-cmig`)
- `BACKEND/routers/invoices.py` (`_sync_ml_fiscal_account` furos cross-mês)
- `Scripts SQL/100_full_cmig.sql`
- ADR-0004 (estoque SSOT), ADR-0008 (anúncio não-FULL anuncia FULL quando LOCAL=0), ADR-0009 (simbólicas)

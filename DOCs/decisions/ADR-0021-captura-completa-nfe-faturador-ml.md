# ADR-0021 — Captura completa de NF-e do Faturador ML (todas as notas viram `Invoice source='ml_faturador'`)

- **Status:** Aceito
- **Data:** 2026-07-31
- **Contexto ADR relacionadas:** revisa/atualiza [ADR-0008](ADR-0008-nfe-batch-mensal-e-anuncio-full-quando-local-zero.md) §"vendas são puladas"; nota cruzada com [ADR-0009](ADR-0009-devolucao-nfe-driven.md) e [ADR-0019](ADR-0019-full-recomputavel-replay.md).


> **EMENDADA em 2026-08-05 por [ADR-0022](ADR-0022-baixa-full-dirigida-pelo-retorno-simbolico.md):**
> na tabela de baldes, "venda casada → fiscal-only (o pedido já debitou o LOCAL)" vale só para
> pedido **NÃO-FULL**. O pedido FULL é excluído do débito local por `local_order_clause()`, então
> a **nota de venda de pedido FULL baixa o galpão** (fecha o par com o retorno simbólico).

## Contexto

O `_sync_ml_fiscal_account` baixava o **lote mensal (batch) de NF-e do Faturador do Mercado Livre**
e, por decisão da ADR-0008 §34, **persistia apenas as notas de FULL** (remessa/retorno) — "vendas são
puladas para não duplicar; devolução = Fase B". Consequência prática relatada pelo dono: a tela
**Fiscal › Saídas** da conta CMIG MIG mostrava a numeração com **furos** — porque as **vendas nunca
eram gravadas** como documento fiscal (só existiam no cache do pedido, `orders.nfe_invoices_json`),
então a sequência de numeração emitida pela CMIG ficava impossível de reconciliar.

A skill `mercado-livre-api` confirmou: o batch (`GET /users/{id}/invoices/sites/MLB/batch_request/
period/stream`) é a **única** fonte que devolve todas as NF-e emitidas no período, sem paginação, num
zip. Não há endpoint de "listar por número". Portanto, para fechar a sequência, é preciso **guardar
TODAS as notas do lote** — não só as FULL.

## Decisão

**Toda NF-e do lote do Faturador ML (modelo 55/65) é persistida como `Invoice` com
`source='ml_faturador'`**, classificada em **baldes**, sendo que **somente o balde FULL movimenta
estoque**:

| Balde | Detecção | Grava | Estoque |
|---|---|---|---|
| **FULL** | dest OU emit = CNPJ FULL da CMIG | `purpose=remessa/retorno` | **MOVE** LOCAL⇄FULL (comportamento anterior, inalterado) |
| **Venda casada** | saída, chave == `Order.nfe_key` | `purpose=venda`, `order_id` setado | fiscal-only (`stock_updated=False`) — o pedido já debitou o LOCAL ([ADR-0019](ADR-0019-full-recomputavel-replay.md)) |
| **Saída sem pedido** | saída, sem pedido casado | `purpose=venda`, `order_id=NULL` + `fiscal_info` | fiscal-only + **SINALIZADA** (não debita; revisar) |
| **Devolução** | entrada (CFOP 1/2/3 ou `tpNF=0`) | `purpose=devolucao` | fiscal-only ([ADR-0009](ADR-0009-devolucao-nfe-driven.md) — contadores de inspeção são canônicos) |
| **Descartada** | modelo ≠ 55/65 (CT-e 57 / MDF-e 58) | — | — |

Regras de suporte:

1. **Direção** por `ide/tpNF` (canônico — MOC B11: 0=entrada, 1=saída), com CFOP do 1º item como
   reforço. Sem nenhum dos dois → **pula e loga** (falhar alto, nunca assumir saída em silêncio).
2. **Dedup por chave de acesso** antes do split (idempotente: re-sync/backfill não duplicam nem
   re-movem estoque). Re-sync **religa** venda órfã (`order_id` NULL) ao pedido cujo `nfe_key` já foi
   preenchido depois.
3. **Reconciliação de sequência** (`_compute_sequence_report`, read-only): base = notas **numeradas
   pela CMIG** (exclui só a devolução de **entrada de terceiro** capturada do ML — o número é da série
   do cliente). Furo = número ausente em [min,max] **não coberto** por `nfe_inutilizacoes`. Cancelada/
   denegada **consome** número (fica presente). Furo é **ALERTA**, não erro (pode ser inutilização
   feita no próprio ML, que a API não expõe).
4. **`nfe_inutilizacoes`** é populada pelo `/inutilize` (SEFAZ próprio, `source='sefaz_own'`) e por
   `/outbound/inutilizacao-manual` (`source='manual'`, p/ inutilização feita no ML).
5. **`/outbound` paginado no BD** (fonte fiscal limitada em SQL ao `page*page_size`; fonte ML só o que
   ainda não virou Invoice via `NOT EXISTS`), para o volume gerado não materializar milhares de linhas.
6. **Backfill** de K meses (`/outbound/backfill-ml-fiscal`) roda **depois** da paginação estar no ar.

## Consequências

**Positivas:**
- A sequência de numeração fica **completa** e reconciliável; o dono vê venda + FULL + devolução + os
  furos reais por série.
- Estoque **inalterado** (invariante provada: só o balde FULL chama `_apply_stock_movement`; os demais
  ficam `stock_updated=False`, invisíveis ao replay). Backfill tem delta de estoque zero.
- Escrita fiscal + movimento de estoque restritos a `ac`/`admin` (como `/inutilize`).

**Limitações conhecidas (exigem evolução + validação do contador):**
- **Cancelamento não ingerido:** o lote entrega só o XML autorizado — a nota cancelada fica
  `status='authorized'`. Não gera furo falso (o número continua presente/consumido), MAS **os totais
  derivados dessas `Invoice` não são base de apuração** sem cruzar o evento 110111. Evolução: cruzar
  a **Distribuição de DFe própria** ([ADR-0016](ADR-0016-distribuicao-dfe-propria.md)) e rebaixar
  `status='cancelled'`.
- **CC-e não persistida:** eventos (`procEventoNFe`) caem no `except` do parser. Baixo risco fiscal
  direto; evolução futura ingere por ramo dedicado.
- **XML não arquivado:** as notas `ml_faturador` não guardam XML local (download vem do ML pelo
  pedido vinculado). Notas de saída sem pedido (remessa FULL simbólica) ficam sem botão de download.

## Alternativas descartadas

- **Manter só FULL (ADR-0008 original):** não fecha a sequência — foi o problema relatado.
- **Reconstruir a sequência só do cache do pedido:** o cache não cobre remessa/devolução e não é
  fonte fiscal persistente; a numeração continuaria "furada" na tela.
- **Mover estoque também na venda do lote:** dobraria o débito (o pedido já debita — ADR-0019).

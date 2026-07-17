# ADR-0019 — Estoque FULL recomputável (replay) + débito de venda dirigido pelo pedido + reconciliação por inventário

**Data:** 2026-07-17
**Status:** ✅ Aceito (em implementação faseada)
**Decisores:** Vinicius (proprietário)

## Contexto

O estoque FULL (`FullStock.qty`, por produto **CMIG** × conta ML — ADR-0010) era mantido **apenas
de forma incremental**, sem replay: eventos ajustavam o saldo na hora, com idempotência via
`stock_movements` (`field_affected='full_stock'`):

- **`full_in`** — NF-e de **saída** (remessa) cujo destino é um **CNPJ FULL** cadastrado
  (`is_full_cnpj` → resolve a conta por `FullCnpj.marketplace_account_id`) → **credita** o FULL.
- **`full_return_out`** — NF-e de **entrada** vinda de um CNPJ FULL (retorno ao galpão) → **debita**.
- **`full_out`** — pedido **FULL enviado** (shipped/delivered) → **debita** (e libera a reserva).

Problemas que motivam esta decisão:

1. **Sem recompute:** ao contrário do estoque local (`recompute_all_stock`, replay a partir de 0), o
   FULL não era reconstruível. Correções (nota cancelada/editada) e o botão "Recalcular Estoque"
   não recompunham o FULL.
2. **NF-e de retorno do CNPJ FULL é frequentemente NÃO identificada/emitida.** Logo, o débito de
   retorno (`full_return_out`) falha muitas vezes → o FULL fica **superestimado** e o galpão
   subestimado.
3. **O débito de venda precisa ser dirigido pelo PEDIDO** (não pela NF-e): saber que a unidade saiu
   do FULL por venda, debitar **uma única vez**, e **só do FULL** (nunca do galpão).

## Decisão

O FULL passa a ser **recomputável por replay de eventos**, preservando a SSOT fiscal do
ADR-0010/0008. O saldo por (produto CMIG, conta) é reconstruído acumulando:

```
FullStock.qty = âncora de inventário FULL (baseline/ajuste)          # ADR-0004 estendido ao FULL (Fase 2)
              + Σ full_in         (NF-e remessa → CNPJ FULL)          # crédito
              − Σ full_out        (pedidos FULL enviados)             # débito por VENDA — dirigido pelo pedido
              − Σ full_return_out (NF-e entrada ← CNPJ FULL, quando houver)   # débito por RETORNO
```

Princípios (endereçando os problemas acima):

- **Débito de venda = dirigido pelo pedido, uma vez, só o FULL.** A saída por venda é contada pelo
  **pedido FULL** (`shipping_mode='full'` em `shipped`/`delivered`), não pela NF-e. No replay, cada
  pedido é contado **uma única vez** (sem duplicação por construção); o débito atinge **apenas** o
  `FullStock`, nunca o `stock_quantity` do galpão. (Cancelamento/devolução que reabastece o Full deve
  reverter o débito — ver Pendências.)
- **Retorno do CNPJ FULL → galpão.** Quando a NF-e de entrada do CNPJ FULL é identificada, ela
  **debita o FULL** (`full_return_out`) e **credita o galpão** (evento `nfe_in` no replay local, já
  existente). Como essa NF-e **falha com frequência**, o FULL fica superestimado; a **âncora de
  inventário (Fase 2)** reconcilia a diferença (a contagem do ML corrige o FULL na data). O crédito
  do galpão por retorno **sem** NF-e permanece dependente de documento/contagem (ver Pendências).
- **Reconciliação por inventário (Fase 2).** A contagem física do ML entra como **âncora** no replay
  (Baseline = a contagem vira a verdade na data; Ajuste = soma a diferença — mesma semântica do
  ADR-0004/inventário local). É o mecanismo que absorve retornos não documentados e drifts.
- **Incremental permanece** para a atualização ao vivo (webhook/sync); o replay é a fonte de
  reconstrução/correção. Ambos convergem para o mesmo saldo.

## Faseamento (entrega)

- **Fase 1 — FULL recomputável:** `recompute_full_stock` (replay das 3 fontes acima, âncora ainda
  ausente) integrado ao `recompute_all_stock` e ao botão "Recalcular Estoque (todos)". Sem tocar
  `reserved_qty` (reserva é assunto à parte).
- **Fase 2 — Âncora de inventário do FULL:** ao importar anúncio(s) FULL novo(s), o sistema cria um
  **inventário FULL em rascunho** com a contagem do ML; o usuário revisa e finaliza em lote como
  **Baseline** ou **Ajuste** (revisão em lote — decisão do dono). O evento entra no replay da Fase 1.
- **Fase 3 — Sincronizar/Ler anúncio:** essas funções, além do snapshot `qty_full`, disparam o
  recompute do FULL (Fase 1) para os produtos/contas envolvidos. A conferência `sync-full` continua.

## Consequências

- **Positivas:** FULL reconstruível e auditável; "Recalcular Estoque" passa a incluir o FULL; venda
  debita de forma confiável (pedido) e única; retornos não documentados deixam de "travar" o número
  (a contagem reconcilia).
- **Riscos:** replay de código fiscal é sensível — exige testes de cenário (remessa, venda,
  retorno, idempotência, nota cancelada) e auditoria (quality-guardian + adr-consistency-checker).
  Performance: o replay varre invoices/pedidos FULL — escopar por CMIG/conta e rodar em background
  (como o recompute-all já faz).

## Limitações conhecidas (Fase 1)

- **Concorrência replay × incremental:** o replay grava `FullStock.qty` **absoluto**; um evento
  incremental (webhook shipped, NF-e) aplicado **durante** o replay em background pode ter o delta
  sobrescrito → FULL transitoriamente alto, **auto-cura** no próximo recompute. Mitigação Fase 1:
  rodar o "Recalcular Estoque (todos)" em janela de baixo tráfego. Follow-up: cutoff por timestamp +
  reconciliação dos movimentos posteriores.
- **`purpose='devolucao'` é EXCLUÍDO** do replay do FULL (paridade com o recompute local + ADR-0009);
  o retorno legítimo do FULL é `purpose='retorno'` (`direction='in'`), que é contado.
- **Gate do replay FULL = critério de relevância do FULL, não `stock_updated`.** O replay filtra NF-e
  por `status ∈ (finalized, authorized)` + **CNPJ FULL** (`is_full_cnpj`) + direção + `purpose ≠ devolucao`
  + não-simbólica — o MESMO critério do incremental do FULL (`apply_nfe_*`). Ele **não** usa o gate
  `stock_updated` do recompute **local** (que é flag do estoque do galpão): FULL e galpão são estoques
  distintos com gates distintos. Logo o replay-FULL reproduz o incremental-FULL, não o recompute local.
- **Auto-criação de espelho durante o replay:** ao creditar remessa e ao debitar venda, o replay usa
  `resolve_full_cmig_product(create=True)` — pode **auto-criar o CMIGProduct espelho** (`is_full_mirror`)
  do PG quando faltar (ADR-0010). É o mesmo efeito colateral do fluxo incremental, intencional.

## Pendências / follow-up

- **Reverter débito de venda FULL cancelada/devolvida** que reabastece o Full no ML (o replay deve
  reconhecer o cancelamento/devolução e não debitar — ou re-creditar). Validar o sinal do ML.
- **Sinal de retirada/retorno de inventário do Fulfillment via API do ML** (para debitar FULL +
  creditar galpão sem depender da NF-e). Pesquisar a API de inventário/movimentação do Full; se não
  existir sinal confiável, a reconciliação por inventário (Fase 2) é a rede de segurança.
- **`reserved_qty` do FULL** (reservas de pedidos baixados) — recompute próprio, fora da Fase 1.

## Relação com outras ADRs

- **ADR-0010** (FULL sempre do CMIG) e **ADR-0008** (NF-e batch + FULL) — mantidos; esta ADR adiciona
  a capacidade de **recompute** e formaliza o débito-por-pedido e a reconciliação por inventário.
- **ADR-0004** (Estoque SSOT + inventário baseline/ajuste) — estendido ao FULL na Fase 2.

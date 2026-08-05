# ADR-0022 — Baixa do estoque FULL dirigida pelo **retorno simbólico**, não pelo pedido

**Data:** 2026-08-05
**Status:** ✅ Aceita
**Decisores:** Vinicius (proprietário) — modelo fiscal confirmado por ele

**Supersede parcialmente:** [ADR-0019](ADR-0019-full-recomputavel-replay.md), no ponto "débito de venda **dirigido pelo pedido** (não pela NF-e)". O restante da ADR-0019 (FULL recomputável por replay a partir de 0, reconciliação por inventário) permanece válido.

## Contexto

A ADR-0019 definiu que a venda FULL debita o `FullStock` **pelo pedido** (`apply_full_order_shipped`), não pela NF-e. Ao investigar por que o FULL da MIG calculava 339 contra 305 reais, três fatos mudaram o quadro:

1. **O ML emite duas notas por venda FULL.** O `nfe_invoices_json` do pedido (cache do Faturador) traz, para pedido FULL, exatamente `transaction_type: "sale"` **e** `transaction_type: "symbolic_inbound_return"`. Pedido de agência/flex traz **só** `sale`. Medido na conta #2: 697 vendas FULL ↔ 696 retornos simbólicos.

2. **O dono confirmou a semântica** (fonte de verdade do negócio):
   > "A baixa no estoque FULL, só o retorno simbólico. Mas perceba que a venda FULL tem uma nota retorno simbólico (que retorna o produto para o galpão simbolicamente) e uma outra nota de Venda, que é referente ao pedido, que dá baixa física do estoque. As duas notas representam a baixa da venda. Quando só houver um retorno e não houver a venda, significa que o produto voltou fisicamente para o Estoque do Galpão."

3. **O débito por pedido nunca funcionou.** `recompute_full_stock` filtrava com `func.coalesce(Order.return_status, "") != "returned"` e, em Oracle, `''` **é NULL** → o `!=` avalia NULL e descarta a linha. Medição: 693 pedidos FULL → **0** processados. Ou seja, a ADR-0019 estava escrita mas inerte, e o sistema já operava — por acidente — no modelo do retorno simbólico.

## Decisão

**O retorno simbólico é o evento canônico de baixa do FULL.** O pedido **não** debita o `FullStock`.

Contabilização de uma venda FULL:

| Nota | Galpão | FULL |
|---|---|---|
| Remessa para Depósito Temporário (saída) | **−** | **+** |
| Retorno Simbólico de Depósito (entrada) | **+** | **−** |
| Venda de mercadorias (saída, vinculada ao pedido) | **−** | — |

O par retorno+venda é **neutro no galpão** e resulta em **FULL −1**. Retorno **sem** venda pareada = mercadoria voltou fisicamente ao galpão (galpão +1, FULL −1).

Consequências diretas no código:

- A nota de venda de pedido **FULL** move estoque local (`_apply_stock_movement`), porque o pedido FULL é excluído do débito local por `local_order_clause()`. A nota de venda de pedido **não-FULL** continua fiscal-only (o pedido já debitou) — sob pena de dupla baixa.
- `full_stock_service.recompute_full_stock` mantém o bloco de débito por pedido **inerte por causa do bug do `coalesce`**. Há um alerta explícito no código: **corrigir aquele `coalesce` isoladamente cria dupla baixa** (retorno −2262 *e* vendas −693 na MIG) e derruba o FULL de +339 para ≈ −730. A remoção do bloco deve vir acompanhada da revisão da semântica de `reserved_qty` (ver Pendências).
- A classificação (`Invoice.purpose`) das notas do ciclo depende de haver `FullCnpj` cadastrado **no momento da importação**. Sem ele, o retorno é importado como `devolucao` (que o replay exclui) e a remessa como `venda`. Foi o que ocorreu na CMIG 21 (LPS) e exigiu reclassificação.

## Alternativas consideradas

- **Manter o débito pelo pedido (ADR-0019) e tornar o retorno simbólico inerte no FULL.** Rejeitada: contradiz o modelo fiscal confirmado pelo dono e não bate com os números reais (o modelo remessa−retorno dá 339 contra 305 reais; remessa−vendas daria ≈1530).
- **Debitar por ambos.** Rejeitada: dupla baixa, comprovada numericamente.

## Pendências que esta ADR deixa abertas

1. **`reserved_qty` do FULL.** Hoje `apply_full_order_shipped` debita `qty` e libera a reserva juntas. Ao remover o débito por pedido, a liberação precisa migrar para o retorno simbólico (que chega no job **diário** de NF-e — `scheduler.py` CronTrigger 06:00, cobre o mês corrente) — senão `qty − reserved` sobre-declara disponível enquanto a nota não chega (latência de emissão do ML), e o **anúncio não-FULL que anuncia saldo do FULL** (exceção da ADR-0008 §2) deixa de pausar (ADR-0014). Casamento reserva↔nota exige FIFO por quantidade em (produto, conta): o `InvoiceItem` não carrega `order_id`.
2. **Idempotência.** `reconcile_full_dispatched` chaveia pelo movimento `full_out`. Se o pedido deixar de emitir `full_out`, o guard nunca fecha e a função reprocessa os mesmos pedidos a cada sync. Exige um marcador novo antes de mexer.
3. **Movimentos `full_out` históricos** ficam na trilha como modelo anterior — não apagar (auditoria); reetiquetar no extrato.

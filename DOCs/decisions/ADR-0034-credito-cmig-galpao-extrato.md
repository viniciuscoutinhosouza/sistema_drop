# ADR-0034 — Razão de crédito CMIG × Galpão + Extrato de Crédito (Fase 4)

## Status
Aceita (2026-10-21). Fase 4 (última) do subsistema de recebimento/checkout (ADR-0031 Fase 1, ADR-0032 Fase 2, ADR-0033 Fase 3).

## Contexto
A Fase 1 criou a flag `warehouses.pg_requires_prepaid`: "venda de PG tem de estar paga **ou creditada** antes da entrega". O crédito é um saldo que a **CMIG** (dropshipper) mantém **com o Galpão** — a CMIG deposita antecipado e as vendas de PG consomem. O dono quer ver isso em **Financeiro > Extrato de Crédito**. Não existia nenhum razão desse tipo (o saldo interno `ACProfile.balance` é outro conceito — liquidação do AC, não crédito por Galpão).

## Decisão
1. **Razão append-only `cmig_warehouse_credits`** (migration 155): cada linha é um movimento `credit` (depósito da CMIG) ou `debit` (consumo por venda PG), por `(cmig_id, warehouse_id)`, opcionalmente ligado a um `order_id`. **Saldo = Σcréditos − Σdébitos** (nunca materializado — derivado em toda leitura, como o estoque da ADR-0004). Ponto único `services/credit_service.py` (`get_balance`/`add_entry`/`list_entries`).
2. **Extrato de Crédito** em Financeiro: endpoints `/api/v1/credits` (saldo + lançamentos por par CMIG×Galpão) + tela. Escopo por acesso (ADR-0026): operador do Galpão vê os pares do seu galpão; admin da CMIG vê os da sua CMIG; admin global. Lançar crédito manual (registrar que a CMIG depositou) é ação de operador do Galpão/admin.
3. **Enforcement = ponto único `assert_pg_prepaid` no gate de entrega** (quando o Galpão tem `pg_requires_prepaid` e o pedido tem itens PG não pagos): exige `saldo_credito ≥ valor_PG` OU `payment_status=paid`; senão **bloqueia** ("falhar alto"). O **débito** do crédito é dirigido pela **entrega** (não pela venda), uma única vez — espelhando o princípio order-driven da ADR-0019/0022 (débito no evento certo, não na nota).
4. **Escopo adiado (como o dono adiou os estados 3-5 da Fase 3):** o ponto físico de entrega/separação do pedido manual ainda não existe (Separação/Enviado/Entregue adiados). Então nesta fase entregam-se **o razão (SSOT), o serviço, os endpoints e o Extrato**, e a função de guarda fica **pronta para plugar** no gate de entrega quando os estados 3-5 forem construídos. **Não** há débito automático na venda ainda (evita débito dobrado antes do ponto de entrega existir). Isso é deliberado e está documentado para o dono decidir.

## Consequências
- O dono passa a ver e lançar crédito por CMIG×Galpão. O bloqueio de entrega PG entra junto com os estados 3-5 (a guarda já existe).
- Saldo derivado (sem coluna de saldo) evita drift; o preço é recomputar na leitura (volume baixo).

## Follow-ups
- Wire do `assert_pg_prepaid` no gate de separação/entrega (com os estados 3-5).
- Débito automático do crédito na entrega da venda PG (order-driven, idempotente).
- Conciliação/relatório do Extrato com o financeiro geral.

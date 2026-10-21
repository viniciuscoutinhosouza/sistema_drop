# ADR-0031 — Recebimento por Galpão: cadastro de Banco (gateway) + flags de checkout (Fase 1)

## Status
Aceita (2026-10-21). Fase 1 de um subsistema maior (recebimento/checkout de venda manual + crédito CMIG×Galpão). Fases 2-4 (integração ASAAS, checkout público por token, crédito CMIG×Galpão) virão em ADRs próprias.

## Contexto
O dono quer, por **Galpão**: (a) cadastrar contas de **recebimento** (ex.: ASAAS) com credencial de API; (b) configurar que venda de **PG** exige a CMIG pagar/ter crédito antes da entrega; (c) configurar que **venda manual** exige pagamento do cliente para prosseguir (com checkout, link público, etc.). Hoje o Galpão só tem `pix_key`/`pix_key_type`; **não existe** modelo de Banco, Plano de Contas, crédito CMIG×Galpão, integração de gateway, nem página pública/token (ver mapeamento). Isto é uma epopeia — faseada.

## Decisão (Fase 1 — só config, sem enforcement)
1. **Cadastro de Banco por Galpão** — nova tabela `warehouse_bank_accounts` (N por galpão; "cada conta tem a sua"), migration 152. Campos no estilo ASAAS: `provider` (hoje só `asaas`, fail-loud), `bank_code`, `name` (rótulo), `wallet_id`, `chart_account_label` (texto livre — não há Plano de Contas), flags `is_sandbox`/`is_active`/`is_primary`, dados bancários (agência/conta/Pix/titular), `opening_balance`/`opening_balance_date` (capturados p/ Livro-Caixa futuro), `notes`.
   - **Credencial cifrada (padrão novo):** a API Key do gateway é guardada **cifrada** em `api_key_encrypted` via **Fernet** (`services/crypto.py`, que reexporta `services/fiscal/cert_crypto` — mesma master key `NFE_CERT_MASTER_KEY`). **Nunca** retornada ao front (só `api_key_set: bool`), nunca logada; "em branco mantém, remover = excluir". Eleva o padrão do Bling (que guardava `api_key` em claro).
   - **CRUD** sob `/api/v1/warehouse/{id}/bank-accounts[/{bank_id}]`, gated por `require_menu_permission("go_empresa")` + `_can_access_warehouse` (isolamento por galpão, ADR-0026). **Anti-IDOR:** PUT/DELETE filtram pelo PAR `(id, warehouse_id)`, não só pelo galpão do path. `is_primary` garante no máx. 1 principal por galpão **em aplicação** (`_demote_other_primaries`, não constraint de banco — há janela de corrida concorrente, aceita nesta fase pois `is_primary` só prepara a Fase 2).
2. **2 flags no Warehouse** (migration 152): `pg_requires_prepaid` e `manual_sale_requires_payment` (NUMBER(1)). **INERTES na Fase 1** — nada consome ainda. A UI **avisa explicitamente** que a regra passa a valer na fase do checkout/crédito (honra "falhar alto, nunca em silêncio" — o toggle não finge estar ativo).
3. **UI**: componente reutilizável `WarehouseBankAccountsCard.vue` embutido nas 2 telas de galpão (admin + a do próprio GO), só quando o galpão já existe; + os 2 switches com a nota de fase.

## Consequências
- Perder a `NFE_CERT_MASTER_KEY` passa a inutilizar **senhas de cert fiscal E chaves de banco** — backup obrigatório no runbook.
- PIX em dois lugares (`Warehouse.pix_key` legado × `warehouse_bank_accounts.pix_key`): o do galpão fica como está; o recebimento "de verdade" passa a ser por banco nas fases seguintes. UI sinaliza.
- `chart_account_label`, `opening_balance*` são **dados** capturados, não ações — ligados ao Livro-Caixa/Plano de Contas numa fase futura.

## Fases futuras (não nesta ADR)
- **Fase 2** — Integração ASAAS: cliente da API (cobrança/link, Pix dinâmico, boleto) usando a `is_primary`/credencial cifrada; webhook público de confirmação de pagamento.
- **Fase 3** — Checkout da venda manual: máquina de estados (Pedido→Pagamento→Separação→Enviado→Entregue), página pública por **token no pedido** (cliente vê/edita itens/paga), re-análise de desconto ao reduzir/remover item (o desconto hoje é override de `unit_price` — pode exigir um campo de desconto explícito).
- **Fase 4** — Crédito CMIG×Galpão: ledger novo (credit/debit por `cmig_id`+`warehouse_id`, no padrão de `financial_service`) ligado ao Extrato de Crédito; bloqueio de entrega do PG até pago.

# ADR-0032 — Integração ASAAS: cobrança da venda manual + webhook de pagamento (Fase 2)

## Status
Aceita (2026-10-21). Fase 2 do subsistema de recebimento/checkout (ADR-0031 = Fase 1). Fase 3 (checkout público por token + editar itens) e Fase 4 (crédito CMIG×Galpão) virão depois.

## Contexto
Fase 1 (ADR-0031) deu ao Galpão contas de recebimento (`warehouse_bank_accounts`, ASAAS, API Key cifrada). Falta **cobrar** o cliente de uma venda manual e **confirmar** o pagamento. Não havia gateway nem webhook de pagamento no sistema (só depósito PIX manual + débito de saldo interno `pay_order`).

ASAAS (verificado na doc oficial): base sandbox `https://api-sandbox.asaas.com/v3` / prod `https://api.asaas.com/v3`; auth header `access_token`; `POST /payments` {customer, billingType (PIX|BOLETO|CREDIT_CARD|UNDEFINED), value, dueDate, externalReference} → {id, invoiceUrl, bankSlipUrl, status}; `GET /payments/{id}/pixQrCode`; webhook valida header `asaas-access-token` (authToken obrigatório, 32–255), entrega **at-least-once** (idempotência por id do evento), exige **2xx em <10s**.

## Decisão
1. **Cliente ASAAS** (`services/asaas_service.py`): resolve a conta `is_primary`/ativa/`provider='asaas'` do galpão (`resolve_primary_bank`, falha alto se não houver), decifra a API Key (services/crypto), base por `is_sandbox`. Funções: `test_connection`, `ensure_webhook`, `upsert_customer`, `create_payment`, `get_pix_qr`, `get_payment`. Erros → `AsaasError` → HTTP 400/409 (nunca 500 silencioso).
2. **Modelo `PaymentCharge`** (migration 153): liga cobrança↔pedido↔galpão. `asaas_payment_id` **UNIQUE** é a âncora. + coluna `webhook_token_hash` (SHA-256) em `warehouse_bank_accounts`.
3. **Webhook por conta, 1 URL só, auto-registro**: cada conta ASAAS precisa de um webhook (requisito ASAAS, por conta). O sistema expõe **uma** URL (`POST /api/v1/webhooks/asaas`) e **auto-registra** o webhook de cada conta via `POST /v3/webhooks` com um `authToken` gerado por nós (`ensure_webhook`, ação "Configurar webhook"). Guardamos só o **SHA-256** do token.
4. **Webhook seguro por construção** (endpoint público, sem JWT):
   - âncora = `PaymentCharge.asaas_payment_id` (que NÓS criamos) — **nunca** `order_id`/`externalReference` do corpo (evita forjar "pedido pago");
   - autentica o header `asaas-access-token` por **hash constant-time** (`hmac.compare_digest`) contra a conta **daquela** cobrança; sem token/hash → 401;
   - **idempotência** reusando `webhook_events` (platform=`'asaas'`, event_id);
   - responde **2xx** rápido (sem chamar o ASAAS de volta; confia no payload autenticado);
   - no `PAYMENT_CONFIRMED|RECEIVED` marca **apenas `order.payment_status='paid'`** (+ `paid_at`) — **NÃO** toca `order.status` nem debita saldo (isso é a liquidação interna do `pay_order`, ortogonal a "cliente pagou no gateway").
5. **Endpoints**: `POST /warehouse/{id}/bank-accounts/{bank_id}/test-connection` e `/configure-webhook` (gated `go_empresa` + anti-IDOR por par); `POST /manual-orders/{id}/create-charge` (gated `pedido_manual` + CMIGAdmin; resolve o galpão **estritamente** por `order.cmig_id→CMIG.warehouse_id`; **reentrante**: reusa cobrança viva; `externalReference=order.id`); `GET /manual-orders/{id}/charges`; `POST .../charges/{id}/refresh` (reconcilia status — o webhook é at-least-once e pode se perder).
6. **UI**: na config do banco, "Testar conexão" + "Configurar webhook"; no pedido manual (OrderDetailView), "Gerar link de pagamento (ASAAS)" + lista de cobranças (link/boleto/Pix/refresh).

## Consequências
- **Verificação real** só pelo dono: `test_connection` com key válida, `create-charge` gerando `invoiceUrl`, e um `PAYMENT_CONFIRMED` chegando e flipando `payment_status`. DEV não valida credencial real do ASAAS.
- Operacional: o dono gera o webhook por conta (1 clique); a URL pública tem que estar acessível ao ASAAS. IPs do ASAAS podem ser liberados no firewall (recomendação da doc).
- `payment_status` ganha o uso "cliente pagou" para pedido manual; `status` segue o fluxo de separação/envio (não colidir).

## Fases futuras
- **Fase 3** — checkout público por token no pedido (ver/editar itens, re-análise de desconto), estados Pedido→Pagamento→Separação→Enviado→Entregue.
- **Fase 4** — crédito CMIG×Galpão (PG pré-pago) ligado ao Extrato de Crédito.

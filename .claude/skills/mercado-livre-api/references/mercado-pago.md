# Mercado Pago — Pagamentos

Integração com a API do Mercado Pago (`api.mercadopago.com`). Esta referência cobre o uso pelo **vendedor** (consultar pagamentos das próprias vendas, processar refunds, integrar checkouts em sites próprios).

⚠️ **Vendedores ML não precisam integrar checkout do MP para vender no marketplace** — o ML cuida disso. Você só precisa do MP se: (a) for vender em site próprio (Mercado Shops, e-commerce), (b) for integrador de outros vendedores, (c) precisar de detalhes financeiros que `/orders` não traz.

## Sumário

1. [Quando usar a API do MP](#quando-usar-a-api-do-mp)
2. [Autenticação](#autenticação)
3. [Consultar pagamento](#consultar-pagamento)
4. [Status de pagamento](#status-de-pagamento)
5. [Buscar pagamentos](#buscar-pagamentos)
6. [Refunds (estornos)](#refunds-estornos)
7. [Checkout Pro / Checkout Transparente](#checkout-pro--checkout-transparente)
8. [Webhooks do MP](#webhooks-do-mp)
9. [OAuth para integrar contas de outros vendedores](#oauth-para-integrar-contas-de-outros-vendedores)
10. [PIX](#pix)
11. [Sandbox e cartões de teste](#sandbox-e-cartões-de-teste)

## Quando usar a API do MP

Casos típicos:
- Buscar `payment_id` que veio em `order.payments[].id` para ver detalhes (taxa, forma de pagamento, antifraude).
- Processar reembolsos parciais ou totais.
- Vender em site próprio (Checkout Pro, Checkout Transparente, PIX).
- Webhooks de pagamento (`topic: payment` em `notifications.url`).

## Autenticação

⚠️ **Mercado Pago tem credenciais SEPARADAS do Mercado Livre** — não use o mesmo APP_ID. No painel do MP (`https://www.mercadopago.com.br/developers/panel`), você cria uma aplicação MP que tem seu próprio `client_id`, `client_secret`, `access_token` e `public_key`.

**Dois tipos de credencial:**

- **Production**: `APP_USR-...` (uso real).
- **Test**: `TEST-...` (sandbox).

Para integrar **sua própria conta** (vender em site próprio):

```bash
curl -H 'Authorization: Bearer SEU_ACCESS_TOKEN_MP' \
  https://api.mercadopago.com/v1/payments/PAYMENT_ID
```

Para integrar **conta de terceiros** (você é integrador), use OAuth (ver seção dedicada abaixo).

## Consultar pagamento

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  https://api.mercadopago.com/v1/payments/PAYMENT_ID
```

Resposta inclui:
- `id`, `status`, `status_detail`
- `transaction_amount`, `currency_id`
- `payment_method_id` (ex: `master`, `pix`, `bolbradesco`)
- `payment_type_id` (ex: `credit_card`, `bank_transfer`, `ticket`)
- `installments`
- `payer` (dados do pagador, com restrições de LGPD)
- `card` (dados mascarados)
- `fee_details` (taxa do MP)
- `transaction_details` (líquido recebido)
- `date_approved`, `date_created`
- `external_reference` (se enviado na criação — útil para correlacionar com seu sistema)

## Status de pagamento

| Status | Significado |
|---|---|
| `pending` | Aguardando ação do pagador |
| `approved` | Aprovado |
| `authorized` | Autorizado, aguardando captura |
| `in_process` | Em análise |
| `in_mediation` | Em disputa |
| `rejected` | Rejeitado |
| `cancelled` | Cancelado |
| `refunded` | Estornado totalmente |
| `charged_back` | Chargeback |

`status_detail` traz motivo específico (ex: `accredited`, `cc_rejected_insufficient_amount`, `cc_rejected_call_for_authorize`). Sempre logar para suporte ao cliente.

## Buscar pagamentos

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  'https://api.mercadopago.com/v1/payments/search?sort=date_created&criteria=desc&range=date_created&begin_date=2026-01-01T00:00:00.000-03:00&end_date=2026-01-31T23:59:59.999-03:00'
```

Filtros úteis: `external_reference`, `status`, `payment_method_id`, `payer.id`, `range=date_created` ou `range=date_approved`.

## Refunds (estornos)

### Total

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  https://api.mercadopago.com/v1/payments/PAYMENT_ID/refunds
```

### Parcial

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  -H 'Content-Type: application/json' \
  -d '{ "amount": 50.00 }' \
  https://api.mercadopago.com/v1/payments/PAYMENT_ID/refunds
```

⚠️ **Refunds são irreversíveis.** Confirmar antes.

⚠️ Pode falhar se o pagamento já estiver fora do prazo (varia por método).

## Checkout Pro / Checkout Transparente

### Checkout Pro (redirecionamento)

Cria preferência de pagamento, redireciona usuário para checkout do MP:

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "title": "Produto X",
        "quantity": 1,
        "currency_id": "BRL",
        "unit_price": 100.00
      }
    ],
    "back_urls": {
      "success": "https://meusite.com/sucesso",
      "failure": "https://meusite.com/falha",
      "pending": "https://meusite.com/pendente"
    },
    "auto_return": "approved",
    "notification_url": "https://meusite.com/webhooks/mp",
    "external_reference": "PEDIDO-123"
  }' \
  https://api.mercadopago.com/checkout/preferences
```

Resposta retorna `init_point` (URL para redirecionar) e `sandbox_init_point` (URL de teste).

### Checkout Transparente

Usuário não sai do seu site. Você recebe os dados do cartão via SDK frontend (que tokeniza), envia o token + dados do pagamento para sua API, e sua API chama:

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  -H 'Content-Type: application/json' \
  -d '{
    "transaction_amount": 100.00,
    "token": "CARD_TOKEN_DO_FRONTEND",
    "description": "Produto X",
    "installments": 3,
    "payment_method_id": "master",
    "payer": { "email": "comprador@example.com" }
  }' \
  https://api.mercadopago.com/v1/payments
```

⚠️ **Nunca receba dados de cartão crus no seu backend** — sempre via SDK frontend que tokeniza. Receber `card.number` em texto puro é violação de PCI-DSS.

## Webhooks do MP

Diferente do ML — configurados no painel MP. Tópicos principais:

- `payment` — criado ou status mudou.
- `merchant_order` — ordem do checkout (combina pagamentos parciais).
- `chargebacks`.
- `point_integration_wh` (Mercado Pago Point — maquininha).

Formato:

```json
{
  "id": 123456,
  "live_mode": true,
  "type": "payment",
  "date_created": "2026-04-30T10:00:00.000-03:00",
  "user_id": 12345,
  "api_version": "v1",
  "action": "payment.created",
  "data": { "id": "PAYMENT_ID" }
}
```

Mesmo padrão: GET no recurso para dados frescos, idempotência por `id` da notificação, fila assíncrona.

⚠️ **MP envia notificações duplicadas com frequência** — idempotência aqui é ainda mais crítica.

## OAuth para integrar contas de outros vendedores

Idêntico ao OAuth do ML, mas no MP:

```
https://auth.mercadopago.com.br/authorization?client_id=APP_ID&response_type=code&platform_id=mp&redirect_uri=REDIRECT_URI&state=CSRF
```

Trocar code por token:

```bash
curl -X POST \
  -H 'accept: application/json' \
  -H 'content-type: application/x-www-form-urlencoded' \
  https://api.mercadopago.com/oauth/token \
  -d 'grant_type=authorization_code' \
  -d 'client_id=APP_ID' \
  -d 'client_secret=CLIENT_SECRET' \
  -d 'code=AUTHORIZATION_CODE' \
  -d 'redirect_uri=REDIRECT_URI'
```

Refresh igual ao ML. Tokens MP duram **180 dias** (mais longos que ML).

## PIX

PIX é um `payment_method_id`. Cria-se assim:

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN_MP' \
  -H 'Content-Type: application/json' \
  -d '{
    "transaction_amount": 100.00,
    "description": "Produto X",
    "payment_method_id": "pix",
    "payer": { "email": "comprador@example.com", "first_name": "João", "last_name": "Silva", "identification": { "type": "CPF", "number": "12345678909" } }
  }' \
  https://api.mercadopago.com/v1/payments
```

Resposta inclui `point_of_interaction.transaction_data` com:
- `qr_code` — código copia-e-cola (texto).
- `qr_code_base64` — imagem QR em base64.
- `ticket_url` — URL com QR e instruções.

PIX expira em 30 minutos por padrão. Configurável via `date_of_expiration`.

## Sandbox e cartões de teste

MP **tem ambiente de teste** (ao contrário do ML). Use `TEST-` access token e:

**Cartões de teste (Brasil):**

| Bandeira | Número | Aprovado |
|---|---|---|
| Mastercard | `5031 4332 1540 6351` | sim |
| Visa | `4235 6477 2802 5682` | sim |
| Elo | `5067 7667 8388 8311` | sim |
| Mastercard | `5031 7557 3453 0604` | rejeitado |

CVV: qualquer 3 dígitos. Validade: qualquer data futura.

Para forçar status específicos no nome do titular do cartão:
- `APRO` — aprovado
- `OTHE` — rejeitado por erro geral
- `CONT` — pendente
- `CALL` — rejeitado, ligar para banco
- `FUND` — rejeitado, sem fundos

Ex: `payer.first_name = "APRO"` força aprovação.

Documentação completa: `https://www.mercadopago.com.br/developers/pt/docs/checkout-api/integration-test/test-cards`

## Reconciliação financeira

Para conciliar o que o vendedor recebeu (líquido após taxas, frete, etc.) use **Billing Reports**:

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/billing/integration/periods/key/KEY/group/MP/details?document_type=BILL'
```

Group `ML` para cobranças do Mercado Livre, `MP` para cobranças do Mercado Pago. **Use só para reconciliação fiscal/relatórios**, nunca como fonte primária de gestão de vendas.

## Boas práticas

1. **Nunca commite access token MP no Git** — use vault/env vars.
2. **Sempre valide assinatura HMAC** dos webhooks MP quando disponível (header `x-signature`).
3. **Em refunds parciais**, verifique sempre o saldo restante antes — refunds em sequência podem dar erro de "valor maior que saldo".
4. **Use `external_reference`** ao criar pagamentos para correlacionar com seu sistema sem depender só do `payment_id`.
5. **Para vendedores que vendem no ML E em site próprio**, separe os fluxos: ML usa API ML, site próprio usa API MP. Não tente unificar.

# Webhooks e Notificações

Como receber notificações em tempo real de eventos na conta do vendedor.

## Sumário

1. [Por que webhooks](#por-que-webhooks)
2. [Configuração](#configuração)
3. [Formato do payload](#formato-do-payload)
4. [Tópicos disponíveis](#tópicos-disponíveis)
5. [Padrão de processamento (queue + worker)](#padrão-de-processamento-queue--worker)
6. [Validação de origem (IPs)](#validação-de-origem-ips)
7. [Idempotência](#idempotência)
8. [Missed feeds (recuperar perdidos)](#missed-feeds-recuperar-perdidos)
9. [Template completo (Node/TypeScript)](#template-completo-nodetypescript)

## Por que webhooks

Eventos como nova venda, pergunta, pagamento, mudança de status de envio só podem ser conhecidos via notificação. **Pollar a API constantemente é proibido pelo ML** (gera rate limit e pode ser considerado abuso).

Webhooks são chamadas HTTP POST que o ML faz no seu endpoint sempre que algo relevante acontece nas contas dos vendedores autorizados.

## Configuração

No DevCenter, ao criar/editar a aplicação:

- **URL de callback de notificações**: endpoint público HTTPS. Em desenvolvimento, use `ngrok`, `cloudflared` ou similar.
- **Tópicos**: marque os que vai consumir. Não marque o que não vai usar — gera ruído.

⚠️ **Bug conhecido**: se ao salvar tópicos eles não persistirem, abra a seção "Outros", marque qualquer tópico, salve, depois ajuste — força o re-render.

**Requisitos do endpoint:**

- HTTPS válido (sem self-signed em produção).
- Responder **HTTP 200** em **menos de 500ms**. Acima disso o ML retenta e marca a aplicação como instável.
- Não exigir autenticação básica/header customizado (o ML não envia).

## Formato do payload

Todo webhook chega como POST com JSON neste formato:

```json
{
  "_id": "8f4b9c2a-1234-5678-90ab-cdef01234567",
  "resource": "/orders/2195160686",
  "user_id": 468424240,
  "topic": "orders_v2",
  "application_id": 5503910054141466,
  "attempts": 1,
  "sent": "2026-04-30T16:19:20.129Z",
  "received": "2026-04-30T16:19:20.106Z",
  "actions": ["created", "updated"]
}
```

**Campos importantes:**

| Campo | Uso |
|---|---|
| `_id` | ID único da notificação. Use para idempotência. |
| `resource` | Caminho do recurso afetado. Faça GET aqui para dados frescos. |
| `user_id` | Vendedor afetado. Use para buscar tokens corretos. |
| `topic` | Tópico (orders_v2, items, etc.) |
| `attempts` | Tentativa atual (>= 1). Se cresce, seu endpoint está falhando. |
| `actions` | Eventos específicos (`created`, `updated`, etc.) |

⚠️ **O payload não contém os dados do recurso.** Apenas indica "algo mudou aqui". Você **deve fazer GET** no `resource` para pegar o estado atual.

## Tópicos disponíveis

### Mais usados em integrações de vendedor

| Tópico | Quando dispara | Recurso a consultar |
|---|---|---|
| `orders_v2` | Nova venda ou mudança em venda confirmada (recomendado) | `/orders/{id}` |
| `items` | Item criado, pausado, encerrado, atualizado | `/items/{id}` |
| `messages` | Nova mensagem do comprador | `/messages/packs/{pack_id}/sellers/{seller_id}` |
| `questions` | Pergunta no anúncio | `/questions/{id}` |
| `shipments` | Mudança em envio de venda | `/shipments/{id}` |
| `payments` | Pagamento criado ou status mudou | `/v1/payments/{id}` (api.mercadopago.com) |

### Outros tópicos

| Tópico | Quando dispara |
|---|---|
| `orders_feedback` | Feedback de venda criado/alterado |
| `claims` | Reclamação de venda |
| `invoices` | Notas fiscais (apenas Mercado Envios Full Biller, BR) |
| `item_competition` | Mudança no status de competição em catálogo |
| `public_offers` | Oferta criada ou status mudou |
| `public_candidates` | Item convidado para promoção |
| `stock_locations` | Mudança em locais de estoque |
| `stock_fulfillment` | Operação no estoque Full |
| `items_prices` | Preço criado/atualizado/removido |
| `user_products_families` | Modificação de família de UP |
| `best_price_eligible` | Mudança em status de promoção catalog |
| `quotations` | Cotações de listing (real estate Chile) |
| `leads_credits` | Créditos aprovados/rejeitados (veículos, imóveis) |

## Padrão de processamento (queue + worker)

⚠️ **Nunca processe a notificação no handler HTTP.** A regra é:

```
[Webhook recebido] → enfileirar (Redis/SQS/etc.) → responder 200 → worker processa
```

Por quê:
- Você precisa responder em < 500ms.
- Processamento (GET no recurso, atualização no banco, etc.) pode demorar.
- Permite retry no worker sem o ML retentar.
- Permite escalar workers separadamente do endpoint HTTP.

**Pseudocódigo:**

```typescript
// HTTP handler
app.post('/webhooks/ml', async (req, res) => {
  // Validação rápida do schema
  if (!isValidNotification(req.body)) return res.sendStatus(400);

  // Enfileirar e responder imediatamente
  await queue.add('ml-notification', req.body, {
    jobId: req.body._id, // idempotência via BullMQ
    attempts: 5,
    backoff: { type: 'exponential', delay: 1000 },
  });

  res.sendStatus(200);
});

// Worker (processo separado)
worker.process('ml-notification', async (job) => {
  const { topic, resource, user_id } = job.data;

  // Já processei essa notificação?
  if (await wasProcessed(job.data._id)) return;

  // Buscar token do vendedor
  const client = await getMlClient(user_id);

  // Roteamento por tópico
  switch (topic) {
    case 'orders_v2':
      await processOrder(client, resource);
      break;
    case 'items':
      await processItem(client, resource);
      break;
    // ...
  }

  await markProcessed(job.data._id);
});
```

## Validação de origem (IPs)

O ML envia notificações dos IPs (lista oficial divulgada na documentação):

- `54.88.218.97`
- `18.215.140.160`
- `18.213.114.129`
- `18.206.34.84`

⚠️ **A lista pode mudar**. Verifique periodicamente em `https://developers.mercadolivre.com.br/pt_br/produto-receba-notificacoes`.

Se você usa firewall/WAF, libere esses IPs. Se quer validar origem na aplicação, use whitelist com cuidado — há outros mecanismos mais robustos:

- **HMAC**: o ML está implementando assinatura HMAC em alguns casos. Verificar header `x-signature` se presente.
- **Validação por token na URL**: incluir um token secreto no path do webhook (`/webhooks/ml/SECRET_TOKEN`). Mais simples, funciona bem.

## Idempotência

Webhooks chegam mais de uma vez:
- ML retenta se você não respondeu 200.
- Eventos similares disparam múltiplas notificações (ex: order paid + order status changed).
- Falhas internas do ML podem gerar duplicatas.

**Estratégias:**

1. **Por `_id` da notificação**: tabela `processed_notifications(notification_id PK, processed_at)`. Se já existe, pular.
2. **Por estado do recurso**: comparar `last_updated` do recurso com o último que você processou. Se igual ou anterior, pular.
3. **Operações idempotentes**: estruturar o processamento para que rodar 2x não cause efeito colateral. Ex: `UPDATE orders SET status=$1 WHERE id=$2 AND last_updated < $3`.

## Missed feeds (recuperar perdidos)

Se seu endpoint ficou fora do ar, o ML guarda notificações perdidas por algum tempo:

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/missed_feeds?app_id=APP_ID'
```

Use isso ao reiniciar o serviço após uma janela de indisponibilidade.

**Recomendação:** rodar `missed_feeds` a cada deploy / madrugada como rede de segurança.

## Template completo (Node/TypeScript)

### Endpoint HTTP (Express)

```typescript
import express from 'express';
import { Queue } from 'bullmq';

const app = express();
const queue = new Queue('ml-notifications', {
  connection: { host: 'localhost', port: 6379 },
});

app.use(express.json({ limit: '1mb' }));

interface MlNotification {
  _id: string;
  resource: string;
  user_id: number;
  topic: string;
  application_id: number;
  attempts: number;
  sent: string;
  received: string;
  actions?: string[];
}

function isValidNotification(body: unknown): body is MlNotification {
  if (typeof body !== 'object' || body === null) return false;
  const b = body as Record<string, unknown>;
  return (
    typeof b._id === 'string' &&
    typeof b.resource === 'string' &&
    typeof b.user_id === 'number' &&
    typeof b.topic === 'string'
  );
}

app.post('/webhooks/ml/:secret', async (req, res) => {
  // Validação simples por secret na URL
  if (req.params.secret !== process.env.ML_WEBHOOK_SECRET) {
    return res.sendStatus(404);
  }

  if (!isValidNotification(req.body)) {
    console.warn('Notificação inválida', req.body);
    return res.sendStatus(400);
  }

  await queue.add('process', req.body, {
    jobId: req.body._id, // BullMQ ignora duplicatas com mesmo jobId
    attempts: 5,
    backoff: { type: 'exponential', delay: 2000 },
    removeOnComplete: { age: 86400, count: 10000 },
    removeOnFail: false,
  });

  return res.sendStatus(200);
});

app.listen(3000);
```

### Worker

```typescript
import { Worker } from 'bullmq';
import { MercadoLivreClient } from './ml-client';
import { db } from './db';

const worker = new Worker(
  'ml-notifications',
  async (job) => {
    const { _id, topic, resource, user_id } = job.data;

    // Idempotência via banco (defesa adicional ao jobId do BullMQ)
    const exists = await db.query(
      'SELECT 1 FROM processed_notifications WHERE notification_id = $1',
      [_id],
    );
    if (exists.rowCount) return;

    const client = await MercadoLivreClient.forUser(user_id);

    switch (topic) {
      case 'orders_v2':
        await syncOrder(client, resource);
        break;
      case 'items':
        await syncItem(client, resource);
        break;
      case 'messages':
        await syncMessages(client, resource);
        break;
      case 'shipments':
        await syncShipment(client, resource);
        break;
      case 'questions':
        await syncQuestion(client, resource);
        break;
      default:
        console.log(`Tópico não tratado: ${topic}`);
    }

    await db.query(
      'INSERT INTO processed_notifications (notification_id, processed_at) VALUES ($1, NOW())',
      [_id],
    );
  },
  {
    connection: { host: 'localhost', port: 6379 },
    concurrency: 10,
  },
);

worker.on('failed', (job, err) => {
  console.error(`Job ${job?.id} falhou:`, err);
});

async function syncOrder(client: MercadoLivreClient, resource: string) {
  const order = await client.get<any>(resource, undefined, {
    headers: { 'x-format-new': 'true' },
  });

  // Lock otimista por last_updated
  await db.query(
    `INSERT INTO orders (id, status, total_amount, last_updated, raw)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (id) DO UPDATE
       SET status = EXCLUDED.status,
           total_amount = EXCLUDED.total_amount,
           last_updated = EXCLUDED.last_updated,
           raw = EXCLUDED.raw
       WHERE orders.last_updated < EXCLUDED.last_updated`,
    [order.id, order.status, order.total_amount, order.last_updated, order],
  );

  // Detectar fraude
  if (order.tags?.includes('fraud_risk_detected')) {
    await alertFraud(order.id);
  }
}

// Outros sync... análogo
```

### Schema do banco

```sql
CREATE TABLE processed_notifications (
  notification_id VARCHAR(64) PRIMARY KEY,
  processed_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_processed_notifications_at ON processed_notifications(processed_at);

-- Limpar registros antigos periodicamente (job de manutenção)
-- DELETE FROM processed_notifications WHERE processed_at < NOW() - INTERVAL '30 days';
```

## Boas práticas finais

1. **Endpoint sempre responde 200** mesmo se o tópico for desconhecido (registre e ignore). 4xx/5xx fazem o ML retentar.
2. **Logue cada notificação recebida** com `_id`, `topic`, `user_id`, antes de enfileirar. Facilita debug.
3. **Não confie no `actions[]` para decidir lógica crítica** — sempre busque o recurso fresco.
4. **Configure alertas** para crescimento anormal de `attempts > 1` (sinal de endpoint instável).
5. **Use `missed_feeds` no deploy** para não perder eventos do downtime.
6. **Pra desenvolvimento local**: ngrok com domínio fixo (plano pago) evita ter que reconfigurar URL toda vez. Ou cloudflared tunnel grátis.

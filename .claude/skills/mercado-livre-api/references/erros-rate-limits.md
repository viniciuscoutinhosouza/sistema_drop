# Erros, Rate Limits e Boas Práticas

Como tratar respostas de erro, respeitar limites e evitar comportamentos que levam a sanções.

## Sumário

1. [Códigos HTTP](#códigos-http)
2. [Formato de erro](#formato-de-erro)
3. [Rate limits](#rate-limits)
4. [Estratégia de retry](#estratégia-de-retry)
5. [Antipadrões que geram banimento](#antipadrões-que-geram-banimento)
6. [Mensagens ao comprador — regras estritas](#mensagens-ao-comprador--regras-estritas)
7. [Logging e observabilidade](#logging-e-observabilidade)
8. [Checklist pré-produção](#checklist-pré-produção)

## Códigos HTTP

| Código | Significado | Ação |
|---|---|---|
| 200 | OK | Processar resposta |
| 201 | Created (POST de item, etc.) | Persistir ID retornado |
| 400 | Bad Request — payload inválido | Logar, **NÃO retentar** (vai falhar de novo). Corrigir no cliente. |
| 401 | Unauthorized — token inválido/expirado | Refresh; se refresh falhar, reautorizar |
| 403 | Forbidden — sem permissão para o recurso | Verificar scopes; talvez vendedor não autorizou |
| 404 | Not Found — recurso não existe | Logar; pode ser ID errado ou recurso deletado |
| 409 | Conflict — operação conflita com estado atual | Buscar estado fresco e reavaliar |
| 422 | Unprocessable Entity — validação de negócio falhou | Inspecionar `cause[]` na resposta |
| 429 | Too Many Requests | Backoff exponencial obrigatório |
| 500 | Internal Server Error (do ML) | Retentar com backoff |
| 502 / 503 / 504 | Indisponível temporariamente | Retentar com backoff |

## Formato de erro

```json
{
  "message": "Validation error",
  "error": "validation_error",
  "status": 400,
  "cause": [
    {
      "department": "items",
      "cause_id": 7810,
      "type": "error",
      "code": "item.attribute.missing_conditional_required",
      "references": ["GTIN"],
      "message": "The attribute 'GTIN' is required for this category and brand."
    }
  ]
}
```

**Sempre logar `cause[]`** — é onde está o motivo real.

### Códigos de erro comuns por área

**Items:**
- `item.attribute.missing` — atributo obrigatório faltando.
- `item.attribute.missing_conditional_required` — atributo obrigatório condicional (ex: GTIN).
- `item.category.invalid` — categoria inválida ou descontinuada.
- `item.title.invalid` — título com palavras proibidas.
- `item.pictures.invalid` — imagem rejeitada (tamanho/formato/URL).
- `item.listing_type.invalid` — tipo de anúncio não permitido para a categoria.

**Orders:**
- `order.cancellation.not_allowed` — não pode cancelar nesse status.
- `order.invalid_reason` — `reason_id` não válido para o contexto.

**Auth:**
- `invalid_token` — token expirado/inválido.
- `invalid_grant` — refresh token revogado.
- `invalid_client` — APP_ID ou client_secret errado.
- `invalid_operator_user_id` — usuário é operador, não admin.

## Rate limits

ML aplica rate limit por **vendedor** (seller_id), não por aplicação:

- **~1500 requisições/minuto por vendedor** (valor de referência da documentação pública; pode variar).
- Excedeu → 429 com response vazio.

⚠️ **Não há header `Retry-After` confiável.** Use backoff exponencial.

**Estratégias para ficar dentro do limite:**

1. **Cache local** de dados que mudam pouco:
   - Categorias e atributos (TTL 24h).
   - Detalhes de items que você já tem (atualizar via webhook em vez de GET periódico).
   - User info (TTL 1h).

2. **Multiget** para itens (até 20 por chamada):
   ```
   GET /items?ids=MLB1,MLB2,MLB3,...,MLB20
   ```

3. **Não pollar webhooks**. Configure tópicos e use `missed_feeds` como fallback, não como fonte primária.

4. **Espaçar operações em lote**. Ex: ao publicar 1000 itens, use fila com 5-10 workers concorrentes, não 1000 requisições paralelas.

5. **Token bucket por seller_id** no seu cliente HTTP — limite local antes de bater no ML.

## Estratégia de retry

```typescript
async function withRetry<T>(
  fn: () => Promise<T>,
  options: { maxAttempts?: number; baseDelayMs?: number } = {},
): Promise<T> {
  const maxAttempts = options.maxAttempts ?? 5;
  const baseDelayMs = options.baseDelayMs ?? 1000;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      const status = (err as any).response?.status;

      // Não retentar erros do cliente (4xx exceto 429 e 408)
      if (status && status >= 400 && status < 500 && status !== 429 && status !== 408) {
        throw err;
      }

      // Última tentativa? Lançar.
      if (attempt === maxAttempts) throw err;

      // Backoff exponencial com jitter
      const delay = baseDelayMs * Math.pow(2, attempt - 1) + Math.random() * 500;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw new Error('unreachable');
}
```

**O que retentar:**
- ✅ 429 (rate limit)
- ✅ 408 (request timeout)
- ✅ 500, 502, 503, 504
- ✅ Erros de rede (ECONNRESET, ETIMEDOUT)

**O que NÃO retentar:**
- ❌ 400, 401, 403, 404, 422 — vão falhar de novo. Corrigir no cliente.
- ❌ 409 sem reler o estado primeiro (pode causar loop).

## Antipadrões que geram banimento

Estes comportamentos podem **suspender a conta do vendedor** ou bloquear sua aplicação:

### 1. Mensagens automáticas/templates

🚫 **PROIBIDO**:
- "Olá! Recebemos seu pedido e está sendo processado!"
- "Seu produto foi enviado, código de rastreio XXX"
- "Obrigado pela compra!"
- Qualquer mensagem repetitiva ou template enviada por API.

✅ **PERMITIDO** (apenas em cenários específicos com motivo declarado):
- Tirar dúvida real do comprador respondendo pergunta dele.
- Solicitar dados específicos para envio em casos não logísticos.
- Resolver problema concreto.

**Para ME2/Full/Flex, o ML envia automaticamente atualizações ao comprador. Sua mensagem é redundante e penalizada.**

### 2. Web crawling

🚫 Fazer scraping das páginas do `mercadolivre.com.br`. Use só `api.mercadolibre.com`.

### 3. Múltiplas aplicações para a mesma conta

🚫 Criar várias apps para tentar contornar rate limit ou autorização. ML detecta e bloqueia.

### 4. Não consumir webhooks (fila de notificações entupida)

🚫 Configurar webhooks e não consumir → ML guarda fila → eventualmente desabilita os webhooks → você fica cego.

### 5. Atualizações massivas em segundos

🚫 Atualizar preço/estoque de 10.000 itens em paralelo. **Espace** (1-2 itens/segundo é seguro).

### 6. Polling agressivo de orders

🚫 Buscar `/orders/search` a cada 10 segundos. Use webhooks.

### 7. Usar credenciais de teste em produção (e vice-versa)

🚫 Vai gerar 401/403 incompreensíveis. Sempre validar `live_mode` em webhooks MP.

### 8. Ignorar tag `fraud_risk_detected`

🚫 Enviar mercadoria de pedido marcado como fraude. Prejuízo financeiro garantido.

### 9. Não fazer reauth quando refresh falha

🚫 Loop infinito de tentativa de refresh com token revogado. Detecte e marque para reautorizar.

## Mensagens ao comprador — regras estritas

Se sua aplicação **realmente precisa** enviar mensagens (responder dúvida, etc.), siga estritamente:

### Tipos permitidos (com `motivo` declarado)

```
GET https://api.mercadolibre.com/messages/action_guide/packs/PACK_ID/sellers/SELLER_ID/options
```

Retorna lista de motivos válidos (`SHIPPING_INFO`, `PAYMENT`, `RECEIVE_QUESTION`, `OTHER`, etc.).

### Enviar mensagem

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "from": { "user_id": "SELLER_ID" },
    "to": { "user_id": "BUYER_ID" },
    "text": "Sua mensagem específica aqui",
    "moderation": { "reason_id": "SHIPPING_INFO" }
  }' \
  'https://api.mercadolibre.com/messages/packs/PACK_ID/sellers/SELLER_ID?tag=post_sale'
```

⚠️ Mensagens são moderadas. Mensagens automáticas, com links externos, números de telefone, ou dados pessoais → bloqueadas + penalidade.

### Para perguntas (pré-venda)

```bash
# Listar perguntas
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/questions/search?status=UNANSWERED&seller_id=SELLER_ID'

# Responder
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{ "question_id": 123456, "text": "Sim, temos disponível em estoque." }' \
  https://api.mercadolibre.com/answers
```

⚠️ **Resposta a pergunta é pública**, vai aparecer na página do anúncio. Cuidado com dados pessoais.

## Logging e observabilidade

**O que logar (em produção):**

- Toda requisição saída: método, URL (sem query strings sensíveis), status, latência, `seller_id`.
- Toda notificação recebida: `_id`, `topic`, `resource`, `user_id`.
- Toda operação de OAuth: tipo (authorize/refresh), `seller_id`, sucesso/falha (sem token!).
- `cause[]` completo de erros 4xx do ML.

**O que NUNCA logar:**

- `access_token` ou `refresh_token` em texto puro.
- `client_secret`.
- Dados pessoais de comprador (CPF, email, endereço completo).
- Dados de cartão (mesmo mascarados).

**Métricas úteis:**

- Taxa de erro 4xx/5xx por endpoint.
- Latência p50/p95/p99 das chamadas ao ML.
- Backlog da fila de webhooks.
- Tempo entre webhook recebido e processado.
- Quantidade de refreshes / hora.

**Alertas:**

- Spike em 401 → algum vendedor com token problemático.
- Spike em 429 → você está estourando rate limit.
- `attempts > 1` em webhooks → seu endpoint está demorando.
- Refresh tokens falhando → vendedores precisando reautorizar.

## Checklist pré-produção

Antes de subir uma integração ML:

- [ ] OAuth completo (authorize + refresh) com lock distribuído no refresh.
- [ ] Tokens persistidos com criptografia em repouso.
- [ ] Webhook endpoint público, HTTPS, < 500ms response.
- [ ] Fila + worker para processar webhooks.
- [ ] Idempotência por `_id` da notificação.
- [ ] Retry com backoff em 429/5xx.
- [ ] Cliente HTTP com timeout (5-10s).
- [ ] Cache de categorias/atributos (24h TTL).
- [ ] Multiget para buscas em lote.
- [ ] Logging estruturado sem dados sensíveis.
- [ ] Alertas em métricas críticas.
- [ ] Plano de reauth para tokens revogados.
- [ ] `missed_feeds` no startup pós-deploy.
- [ ] Tratamento explícito de `fraud_risk_detected`.
- [ ] Sem mensagens automáticas/template.
- [ ] Sem polling de orders.
- [ ] Variáveis de ambiente para credenciais (não hardcoded).
- [ ] Testes de integração com usuários de teste.
- [ ] Documentação interna do fluxo OAuth e mapeamento de tópicos.
- [ ] Monitoramento de saúde dos itens publicados (`health=unhealthy`).

## Mais detalhes

Para casos não cobertos aqui (relatórios de faturamento, claims, promoções, Mercado Shops), consulte:

- `https://developers.mercadolivre.com.br/pt_br/api-docs-pt-br` — documentação completa por endpoint.
- `https://developers.mercadolivre.com.br/devcenter` — gerenciar aplicações.
- `https://global-selling.mercadolibre.com/devsite/introduction-globalselling` — venda internacional (Global Selling).
- `https://developers.mercadoenvios.com/` — Mercado Envios em profundidade.
- `https://www.mercadopago.com.br/developers/pt` — Mercado Pago.

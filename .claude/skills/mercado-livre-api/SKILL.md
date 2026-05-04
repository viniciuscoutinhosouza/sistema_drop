---
name: mercado-livre-api
description: Auxilia no desenvolvimento de integrações com a API do Mercado Livre, Mercado Envios e Mercado Pago. Use SEMPRE que o usuário mencionar Mercado Livre, MercadoLibre, MELI, ML, integração com marketplace brasileiro/latam, anúncios, publicações, vendas/pedidos do ML, Mercado Envios, Mercado Pago, MP, OAuth do ML, webhooks do ML, ou qualquer endpoint começando com api.mercadolibre.com. Cobre autenticação OAuth 2.0, publicação e gerenciamento de itens, pedidos e envios, recebimento de notificações (webhooks), integração com Mercado Pago, tratamento de erros e rate limits. Use também quando o usuário estiver desenvolvendo um sistema de gerenciamento de conta de vendedor, ERP integrado, ou qualquer software que leia/escreva dados na conta ML do usuário.
---

# Mercado Livre API — Skill de integração

Esta skill orienta o desenvolvimento de integrações com as APIs do **Mercado Livre** (`api.mercadolibre.com`), **Mercado Envios** e **Mercado Pago** (`api.mercadopago.com`). Ela prioriza implementação correta, segurança e aderência às boas práticas oficiais, evitando os problemas mais comuns que levam a sanções na conta do vendedor.

## Como usar esta skill

A skill segue **progressive disclosure**: este arquivo dá a visão geral e aponta qual referência detalhada consultar. **Sempre leia o arquivo de referência relevante antes de gerar código** — os detalhes que evitam bugs estão lá.

| Tarefa do usuário | Leia primeiro |
|---|---|
| Login/OAuth, refresh token, primeira integração | `references/autenticacao.md` |
| Publicar produto, atualizar preço/estoque, pausar anúncio, busca de itens, categorias, GTIN, variações | `references/itens-publicacao.md` |
| Listar/processar vendas, packs, envios (ME1/ME2/Full/Flex), tracking | `references/pedidos-envios.md` |
| Receber notificações em tempo real, tópicos, validar IPs, missed feeds | `references/webhooks-notificacoes.md` |
| Pagamentos, checkout, OAuth do MP, splits, repasses | `references/mercado-pago.md` |
| Códigos de erro, 401/403/429, retry, rate limits, antipadrões que geram banimento | `references/erros-rate-limits.md` |

Quando a tarefa envolver mais de uma área (ex: receber webhook de venda → consultar pedido → atualizar estoque), leia múltiplas referências.

## Conceitos fundamentais que valem repetir aqui

**Site IDs por país** — toda chamada de busca pública usa um destes:

- `MLB` — Brasil
- `MLA` — Argentina
- `MLM` — México
- `MLC` — Chile
- `MCO` — Colômbia
- `MLU` — Uruguai
- `MPE` — Peru
- `MEC` — Equador

**IDs de itens** seguem o padrão `<SITE_ID><número>`. Ex: `MLB1374737433` (item brasileiro).

**Base URLs principais:**

- `https://api.mercadolibre.com` — API REST principal (Mercado Livre, Envios)
- `https://api.mercadopago.com` — API do Mercado Pago (pagamentos)
- `https://auth.mercadolivre.com.br` — autorização OAuth (Brasil; existe equivalente por país: `auth.mercadolibre.com.ar`, `.com.mx` etc.)

**Autenticação:** quase todo endpoint requer header `Authorization: Bearer <ACCESS_TOKEN>`. Tokens expiram em **6 horas**. Refresh tokens são **single-use** (cada refresh gera um novo, e o anterior fica inválido). Detalhes em `autenticacao.md`.

**Não há ambiente de sandbox.** Todas as publicações e operações rodam contra a conta real. Para testes, use **usuários de teste** criados pela API (ver `autenticacao.md`). Itens publicados em conta real ficam visíveis no marketplace — use títulos como `"Item de Teste - Não Comprar"` e categorias de baixo volume.

## Fluxo de desenvolvimento recomendado

Para um sistema novo de gerenciamento de conta ML, recomende ao usuário esta ordem:

1. **Criar aplicação** no DevCenter (`https://developers.mercadolivre.com.br/devcenter`) e guardar `APP_ID` (client_id) e `Secret Key` (client_secret) em variáveis de ambiente — **nunca no código fonte**.
2. **Implementar OAuth completo** (authorization code + refresh) com persistência segura dos tokens em banco. Sem isso pronto e testado, nada mais funciona. → `autenticacao.md`
3. **Configurar webhooks** com endpoint público (use `ngrok` em dev). Marcar tópicos `orders_v2`, `items`, `messages`, `shipments`, `questions` conforme necessidade. → `webhooks-notificacoes.md`
4. **Implementar leitura de itens e pedidos** (GET) antes de qualquer escrita. Validar que o sistema enxerga os dados corretamente.
5. **Adicionar escrita** (publicar, pausar, atualizar preço/estoque) com cuidado especial em validações e idempotência. → `itens-publicacao.md`
6. **Tratar erros e rate limits** desde o começo: implementar retry com backoff exponencial e respeitar o limite. → `erros-rate-limits.md`

## Princípios não-negociáveis

Seguir estes princípios é mais importante que velocidade de entrega — violá-los pode resultar em **suspensão da conta do vendedor**:

- **Nunca enviar mensagens automáticas/templates** ao comprador via API de mensagens. O ML bloqueia e penaliza. Mensagens só em cenários específicos, com motivo declarado. → `erros-rate-limits.md`
- **Nunca fazer web crawling** das páginas do site. Sempre usar a API.
- **Nunca expor `client_secret`, `access_token` ou `refresh_token`** em código, frontend, logs públicos ou URLs.
- **Sempre validar `redirect_uri` exatamente** como cadastrado no DevCenter (sem parâmetros variáveis na URL base).
- **Sempre persistir e renovar tokens proativamente** antes de expirar — não esperar a chamada falhar com 401.
- **Sempre tratar webhook como "evento → buscar dado fresco"**, nunca confiar no payload do webhook como fonte de verdade. Sempre fazer GET no recurso indicado.
- **Sempre responder 200 em < 500ms** ao webhook (processar em fila assíncrona), senão o ML retenta e marca a aplicação como instável.

## Stack e padrões sugeridos (quando o usuário não definiu)

Pergunte ao usuário antes de assumir, mas se ele pedir sugestão:

- **Linguagem**: Node.js/TypeScript, Python ou Go funcionam bem — todas têm SDKs comunitários (oficial do ML está descontinuado em várias linguagens; verificar antes de recomendar).
- **Persistência de tokens**: tabela dedicada com `user_id`, `access_token`, `refresh_token`, `expires_at`, `updated_at`. Criptografar em repouso se possível.
- **Fila para webhooks**: Redis/BullMQ (Node), Celery (Python), ou similar. O endpoint HTTP só enfileira e responde 200; um worker processa.
- **HTTP client com retry**: configurar timeout (5-10s), retry com backoff exponencial em 429/5xx, cap de tentativas.
- **Logs estruturados** com correlação por `notification._id` (ID do webhook) para debugar fluxos.

## Estrutura típica de um projeto

```
projeto/
├── src/
│   ├── auth/          # OAuth, refresh, persistência de tokens
│   ├── ml-client/     # cliente HTTP com retry, autorização automática
│   ├── webhooks/      # endpoint + fila + workers por tópico
│   ├── items/         # publicação, atualização, busca
│   ├── orders/        # leitura, processamento, atualização de status
│   ├── shipments/     # tracking, etiquetas, ME2
│   └── messages/      # respostas a perguntas (com cuidado!)
└── tests/
```

## Quando NÃO usar a API e usar o painel do vendedor

Algumas operações são **mais seguras manualmente** no site do ML, especialmente em desenvolvimento inicial:

- Criar a aplicação no DevCenter (só pelo site).
- Cancelar ordens com mercadoria já enviada (envolve comprovação).
- Responder reclamações sensíveis.
- Configurar campanhas de Product Ads.

Foque a integração no que é **repetitivo** e **alto volume**.

---

Sempre que iniciar uma tarefa de desenvolvimento ML, declare brevemente qual referência está consultando ("vou olhar `autenticacao.md` antes de escrever o middleware") para que o usuário entenda o raciocínio.

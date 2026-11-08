# Bling v3 — Webhooks, Rate limit, Erros, Paginação

> Itens **[confirmar]** na doc oficial — webhooks e formato de erro variam e não foram validados ao vivo
> nesta base.

## Rate limit

- **~3 requisições/segundo por conta** e um teto diário (**~120.000/dia**) — reportado por SDKs da
  comunidade; **[confirmar]** na doc.
- Excesso → **HTTP 429**. O Bling **não** necessariamente expõe o limite em header → o **integrador**
  controla o ritmo.
- **Implementação recomendada:** um **throttle por conta** (token bucket a 3/s) + **retry com backoff
  exponencial** em 429 e 5xx, com teto de tentativas. Sincronização em lote → **fila** (processa N por
  segundo), nunca um burst.

## Webhooks (callbacks)

O Bling v3 oferece **notificações (webhooks)** configuradas **no aplicativo** (painel), por evento
(ex.: pedido criado/alterado, NF-e autorizada, estoque alterado) **[confirmar]** a lista exata de
eventos e o formato do payload.

**Regras de ouro ao consumir webhook:**
1. **Responda rápido (200 em < alguns segundos)**: só **enfileire** e processe async. Timeout/erro faz
   o Bling **reenviar** e marca a app como instável.
2. **Evento → buscar dado fresco:** trate o corpo como "algo mudou no recurso X id Y" e faça um **GET**
   para pegar o estado atual. Não confie no payload como fonte de verdade.
3. **Idempotência:** o mesmo evento pode chegar **mais de uma vez** → dedupe por id do evento/recurso
   (padrão `webhook_events` já usado no Sistema Drop para ASAAS/ML).
4. **Validação de origem:** **[confirmar]** se o Bling assina o webhook (assinatura/segredo) e valide
   antes de processar; se não houver assinatura, use um caminho/segredo não-adivinhável na URL.

## Formato de erro

Respostas de erro vêm em JSON com um objeto `error` **[confirmar]** a forma exata, algo como:

```json
{
  "error": {
    "type": "VALIDATION_ERROR",
    "message": "Mensagem legível",
    "description": "Detalhe",
    "fields": [ { "element": "nome", "msg": "obrigatório" } ]
  }
}
```

- **Sempre logar** `type` + `message` + `fields` (sem vazar PII em log público).
- Mapeie: **400/422** = payload inválido (corrija campos); **401** = token (refresh + replay);
  **403** = escopo/permência; **404** = recurso inexistente; **429** = rate limit (backoff);
  **5xx** = Bling fora (retry).

## Paginação

- `GET` de listas usa `pagina` (1-based) + `limite` (**máx ~100** **[confirmar]**).
- Resposta traz `data: [...]`. Pagine até vir menos que `limite` (ou até um campo de total, se houver).
- **Sem furo:** ao varrer tudo (ex.: catálogo), itere `pagina` sequencial respeitando o throttle;
  guarde um cursor/última página processada para retomar.

## Diagnóstico rápido

| Sintoma | Primeiro a checar |
|---|---|
| 401 em toda chamada | access_token expirado → refresh; ou token do ambiente/host errado |
| 403 em um recurso | escopo do app não cobre aquela área (mudar escopo = reautorizar todos) |
| 429 frequente | falta throttle 3/s; burst de sincronização → enfileirar |
| 400/422 em POST | nomes/estrutura de campo errados → **ler a referência oficial** daquele recurso |
| Webhook reenviado em loop | você não respondeu 200 rápido (processe async) |
| `invalid_grant` no OAuth | code expirou (30s) / redirect_uri divergente |

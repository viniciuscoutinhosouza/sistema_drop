---
name: bling-api
description: Auxilia no desenvolvimento de integrações com a API do Bling ERP (Bling API v3, `api.bling.com.br/Api/v3`). Use SEMPRE que o usuário mencionar Bling, Bling ERP, API do Bling, OAuth do Bling, client_id/client_secret do Bling, token do Bling, sincronizar produto/estoque/pedido/NF-e com o Bling, webhooks do Bling, ou qualquer endpoint em `api.bling.com.br` / `www.bling.com.br/Api/v3`. Cobre autenticação OAuth 2.0 (authorization code + refresh), produtos, estoque/depósitos, pedidos de venda, notas fiscais (NF-e/NFC-e), contatos, categorias, webhooks e tratamento de erros/rate limit. Use também ao criar/estender o módulo de integração Bling do Sistema Drop (`BACKEND/services/bling_service.py` + conexão por CMIG).
---

# Bling ERP (API v3) — Skill de integração

Esta skill orienta o desenvolvimento de integrações com a **API v3 do Bling** (`api.bling.com.br/Api/v3`),
o ERP brasileiro que o lojista usa para **produtos, estoque, pedidos, financeiro e emissão fiscal
(NF-e/NFC-e)**. No contexto do Sistema Drop, cada **CMIG** (empresa vendedora) conecta a **sua própria**
conta Bling por OAuth — é uma integração **por-CMIG**, não uma conta única do sistema.

> **⚠️ Esta skill é um GUIA, não a fonte da verdade.** A fonte é (1) a **documentação oficial**
> em `developer.bling.com.br` e (2) o **comportamento da API ao vivo**. O Bling muda regras e está
> **migrando o token opaco para JWT**. Itens marcados com **[confirmar]** não foram validados contra a
> doc oficial/API nesta base — valide antes de depender deles. Vale a mesma regra anti-erro das skills
> de ML/Shopee: **nunca afirme "não dá" sem verificar na doc oficial e/ou testar.**

## Como usar esta skill

Progressive disclosure: este arquivo dá a visão geral e aponta a referência detalhada. **Leia a
referência relevante antes de gerar código** — os detalhes que evitam bug estão lá.

| Tarefa | Leia primeiro |
|---|---|
| OAuth 2.0 (autorizar, trocar code, refresh, revogar, escopos, JWT) | `references/autenticacao-oauth.md` |
| Produto, variação, estoque/saldo, depósito, categoria, imagem | `references/produtos-estoque.md` |
| Pedido de venda, NF-e/NFC-e, contato (cliente/fornecedor), situação | `references/pedidos-nfe-contatos.md` |
| Webhooks (callbacks), rate limit, formato de erro, paginação, retry | `references/webhooks-erros-limites.md` |
| Como a conexão CMIG ⇄ Bling é (ou será) feita no Sistema Drop | `references/integracao-sistema-drop.md` |

Quando a tarefa cruzar áreas (ex.: receber webhook de pedido → consultar pedido → baixar estoque),
leia mais de uma referência.

## Conceitos fundamentais (valem repetir aqui)

**Base URL (v3):** `https://api.bling.com.br/Api/v3` para as chamadas de recurso. O **host de
autorização** (tela de consentimento) é `https://www.bling.com.br`. (O `bling_service.py` legado usava
`https://www.bling.com.br/Api/v3` como base da API — host histórico; para v3 prefira `api.bling.com.br`.
**[confirmar]** qual host o app do dono responde melhor; ambos aparecem na doc/SDKs.)

**Autenticação = OAuth 2.0 (Authorization Code), NÃO "API key".** O Bling v3 **não** usa chave estática.
O `Authorization: Bearer <access_token>` carrega um **access token OAuth** que **expira** (~6 h,
`expires_in=21600` **[confirmar]**) e é renovado pelo **refresh token** (validade **30 dias**). O
`authorization_code` da etapa 1 expira em **30 segundos** — troque imediatamente no servidor. Detalhes
e nomes exatos em `autenticacao-oauth.md`.

**Não há sandbox.** Toda chamada roda contra a conta **real** do lojista. Teste com cuidado (produtos de
teste, pedidos rascunho) — ver `produtos-estoque.md`.

**Rate limit:** ~**3 requisições/segundo por conta** (e um teto diário, ~120.000/dia) — reportado por
SDKs da comunidade, **[confirmar]** na doc. Excesso → HTTP **429**. Implemente throttle + backoff desde
o início (`webhooks-erros-limites.md`).

**Um app, N contas.** Você registra **um** aplicativo (client_id/client_secret) no Bling e cada CMIG
**autoriza** esse app na conta Bling dela, gerando um par de tokens **por CMIG**. Os escopos são
definidos **no cadastro do app** — e **alterar escopo revoga todos os usuários** ao salvar (replanilhe
escopos antes de ir a produção).

## Fluxo de desenvolvimento recomendado

1. **Registrar o aplicativo** no painel do Bling (developer.bling.com.br → Aplicativos): guardar
   `client_id`/`client_secret` em variável de ambiente (**nunca** no código), definir o **Link de
   redirecionamento** (= `redirect_uri`, tem de bater exato) e marcar os **escopos** necessários.
2. **Implementar o OAuth completo** (authorize → callback → troca do code → persistir tokens
   **cifrados** → refresh proativo). Sem isso pronto e testado, nada mais funciona.
   → `autenticacao-oauth.md`
3. **Ler antes de escrever:** validar a conexão com um `GET` leve (ex.: `/Api/v3/empresas` ou
   `/produtos?limite=1`) antes de qualquer POST/PUT.
4. **Adicionar escrita** (produto, estoque, pedido, NF-e) com idempotência e validação.
   → `produtos-estoque.md`, `pedidos-nfe-contatos.md`
5. **Webhooks + rate limit + erros** desde o começo: fila assíncrona no webhook, throttle 3 req/s,
   retry com backoff em 429/5xx. → `webhooks-erros-limites.md`

## Princípios não-negociáveis

- **Nunca expor `client_secret`, `access_token` ou `refresh_token`** em código, frontend, log ou URL.
  No Sistema Drop os tokens ficam **cifrados em repouso** (Fernet, `services/crypto`).
- **Sempre renovar o token proativamente** (antes de expirar) e tratar **401** com um refresh + replay
  da chamada. O refresh **rotaciona** o refresh_token — **persista o novo** ou você perde a conexão.
- **`redirect_uri` tem de bater exatamente** com o cadastrado no app (o Bling usa o valor do cadastro,
  ignorando o enviado). Valide isso primeiro quando a autorização falhar.
- **Sempre tratar webhook como "evento → buscar o dado fresco"** (GET no recurso), nunca confiar no
  corpo do webhook como verdade.
- **Respeitar o rate limit** (3 req/s/conta): sincronizações em lote precisam de fila + throttle, senão
  o Bling devolve 429 e a conta fica instável.
- **OAuth no servidor:** a troca do code e o refresh **nunca** no frontend (o `client_secret` vaza).

## ⛔ Regra anti-erro: NUNCA afirme "não dá" sem verificar

Antes de concluir que algo é "impossível / não suportado / só pelo painel", **leia a doc oficial**
(`developer.bling.com.br`, cite a URL) e, se o ambiente permitir, **teste** contra a API com um token
real (via `bling_service` ou um one-off). Trate as afirmações desta skill — e tudo marcado
**[confirmar]** — como **hipóteses**. Se um teste real contradiz a skill, **o teste vence** e corrija a
skill. Prefira responder com evidência ("testei `POST /produtos` e o Bling aceitou / recusou com erro
`X`") em vez de memória.

## Quando usar o painel do Bling em vez da API

- Criar o aplicativo e definir escopos/redirect (só pelo painel).
- Configuração fiscal inicial da empresa (certificado, séries, naturezas de operação).
- Resolver rejeições fiscais sensíveis da SEFAZ.

---

Ao iniciar uma tarefa de Bling, declare qual referência está consultando ("vou ler
`autenticacao-oauth.md` antes de escrever o fluxo OAuth") para o usuário acompanhar o raciocínio.

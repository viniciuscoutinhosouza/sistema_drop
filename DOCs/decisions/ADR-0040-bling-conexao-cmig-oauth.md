# ADR-0040 — Integração Bling (ERP) por CMIG via OAuth2 (Fase 1: conexão)

**Status:** Aceita (Fase 1 implementada — 2026-11-08; **pendente credencial do app Bling do dono** para prova ponta-a-ponta)
**Relaciona:** [ADR-0038](ADR-0038-google-drive-armazenamento-imagens.md) (molde OAuth: tokens cifrados + tabela dedicada + callback público), [ADR-0036](ADR-0036-capacidade-nunca-se-amarra-em-escopo.md) (capacidade = permissão AND escopo), [ADR-0026](ADR-0026-papel-galpao-unificado.md) (escopo por CMIG), [ADR-0023](ADR-0023-estoque-composto-derivado.md) (kit = estoque derivado — relevante ao import futuro)

## Contexto

O dono quer conectar cada **CMIG** (empresa vendedora) à conta **Bling** (ERP) dela, para — numa fase
seguinte — **importar categorias, produtos e kits** cadastrados no Bling. O Bling API **v3 é OAuth2**
(o `bling_service.py` legado tratava como "API key" estática, host errado `www.bling.com.br`, sem
refresh — desatualizado). Havia também um endpoint legado `POST /accounts/{id}/bling/connect` que
gravava a API key **em texto plano** num `MarketplaceAccount(platform='bling')`.

Decisão de onde guardar a credencial: o Bling é o **ERP da empresa**, não um canal de venda. Reusar
`MarketplaceAccount(platform='bling')` (a) polui os seletores de conta de venda (conta inativa já é
escondida de todo seletor — regra do dono) e (b) lá os tokens **não** são cifrados.

## Decisão

Integração **OAuth2 (Authorization Code) POR CMIG**, espelhando o padrão do Google Drive (ADR-0038),
com as diferenças que o escopo por-CMIG exige.

- **Tabela dedicada `cmig_bling_accounts`** (migration 179), **UMA conexão por CMIG** (`UNIQUE
  cmig_id`). `access_token_enc`/`refresh_token_enc` **CIFRADOS em repouso** (Fernet, `services/crypto`,
  master `NFE_CERT_MASTER_KEY`). Colunas **CLOB** (o Bling migra token opaco → JWT, que pode passar de
  VARCHAR2(4000)). Reconexão faz **UPSERT in-place** (nunca 2ª linha — respeita o UNIQUE).
- **Rotas autenticadas montadas por-CMIG** em `/api/v1/cmigs/{cmig_id}/bling` (`status`/`authorize`/
  `test`/`connection`), espelhando `fiscal_config` (NÃO `?cmig_id`, NÃO o modelo admin-global do Drive).
- **Autorização = permissão AND escopo** (ADR-0036): `require_permission("bling_gerenciar")` **AND**
  `assert_cmig_access(cmig, user)`. Nova chave de ação `bling_gerenciar` (menu `cmig`, default
  `ac`/`admin`, seed migration 180 idempotente padrão 162). A capacidade **não** se amarra em helper de
  escopo.
- **Callback público** (única rota sem JWT — quem chama é o Bling): `/api/v1/integrations/bling/
  callback`. O `cmig_id` vem de um **`state` CIFRADO** (`crypto.encrypt` de `{cmig_id, user_id, nonce,
  ts}`), validado por frescor (TTL 15 min) e integridade — **nunca** do path (anti-IDOR). **Padrão novo
  no codebase** (o Drive usa `state` plano por ser conta única); fica como base para futuras
  integrações OAuth por-CMIG.
- **Credenciais do app configuráveis POR CMIG** (migration 181): cada CMIG pode ter o **próprio**
  `client_id` + `client_secret` (secret **CIFRADO** Fernet em `cmig_bling_accounts.client_secret_enc`;
  `client_id` em claro — não é segredo), editáveis no card. Resolução em `_creds_from(conta)`: usa as da
  CMIG se cadastradas, senão o **app padrão do `.env`** (`BLING_CLIENT_ID/SECRET`) como fallback. Endpoint
  `PATCH /credentials` (secret vazio = manter o atual; nunca devolve o secret). Permite tanto um app
  compartilhado (só `.env`) quanto um app por CMIG, sem acoplar.
- **OAuth server-side:** troca do `code` e refresh com **Basic auth** (base64 `client_id:client_secret`)
  — o secret nunca vai ao frontend. O **refresh ROTACIONA** o refresh_token (persistimos o novo par) e
  roda **sob lock por-CMIG** (não global — não serializa CMIGs distintas). `code` do Bling expira em
  **30s**; refresh em **~30 dias** (sem uso → `requires_reauth`-equivalente: reconectar).
- **Rate limit:** throttle conservador por-processo (~3 req/s) + retry em 429/5xx + `401→refresh→replay`.
- **Legado preservado, deprecado:** `validate_api_key`/`sync_product` ficam em `bling_service.py`
  marcados **DEPRECADO** (o endpoint antigo `/accounts/{id}/bling/connect` não quebra). `MarketplaceAccount.
  api_key 'Para Bling'` é legado **ignorado** pelo fluxo novo — candidato a remoção numa limpeza futura.
- **Front:** card **`CmigBlingConfigCard`** dentro do `CmigDetailView` (onde a config por-CMIG já vive),
  gated por `hasAction('bling_gerenciar')` — conectar (popup) / status / testar / desconectar.

## Consequências

- **Fase 1 = só conexão.** Não sincroniza nada ainda (como o Drive foi entregue antes de ter
  consumidor). O `/status` é só leitura do banco (não toca a API → não pode ser derrubado por rede).
- Um **app Bling** (client_id/secret) serve **todas** as CMIGs; cada CMIG autoriza esse app na conta
  dela. Config no `.env`: `BLING_CLIENT_ID/SECRET/REDIRECT_URI`. **Sem credencial real, o OAuth não é
  testável no DEV** (igual ML/Shopee) — a prova ponta-a-ponta é no ambiente do dono.
- **Tokens nunca em claro;** perder a `NFE_CERT_MASTER_KEY` inutiliza as conexões Bling (como já vale
  p/ cert fiscal/ASAAS/Drive).

## Roadmap (fases futuras — cada uma com sua ADR)

- **Fase 2+ (direção Bling → Sistema Drop, LEITURA):** importar **categorias, produtos e kits** do
  Bling. Mapear para o modelo (CMIGProduct / catálogo / kit = estoque derivado dos componentes,
  ADR-0023). **Não** importar saldo (estoque segue SSOT local event-sourced, ADR-0004/0019) — importar
  catálogo ≠ importar estoque.
- Confirmar os `[confirmar]` da skill `bling-api` contra a API real (host v3, validade do access_token,
  nomes de campo, webhooks) quando houver credencial.
- Limpeza: aposentar o endpoint legado `/accounts/{id}/bling/connect` + coluna `api_key`.

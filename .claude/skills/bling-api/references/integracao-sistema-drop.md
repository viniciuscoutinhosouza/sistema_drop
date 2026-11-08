# Bling no Sistema Drop — como a conexão CMIG ⇄ Bling se encaixa

Esta referência descreve **o padrão** da integração no codebase (não a API em si). É a ponte entre a
skill e a implementação.

## Princípio: Bling é por-CMIG, não uma "conta de marketplace"

- O Bling é o **ERP da empresa** (a CMIG), não um canal de venda. Cada **CMIG** conecta a **sua**
  conta Bling. → a credencial pertence à **CMIG**, não a uma `MarketplaceAccount`.
- **Não reutilizar** `MarketplaceAccount(platform='bling')` para guardar o OAuth: (a) polui os seletores
  de conta de venda (acabamos de esconder conta inativa de todo seletor — ver
  `[[feedback_conta_desativada_escondida]]`); (b) os tokens lá **não** são cifrados. O Bling exige
  cifragem (dado fiscal/financeiro).
- **Molde a seguir:** a integração **Google Drive (ADR-0038)** — OAuth2, tokens **cifrados** (Fernet,
  `services/crypto`), **tabela dedicada**, router com `/status` `/authorize` `/callback` `/connection`
  `/test`, exceções tipadas. A diferença é o **escopo**: Drive é conta única admin-global; **Bling é por
  CMIG** (escopo por `assert_cmig_access` + permissão de ação, ADR-0036).

## Peças (o que existe × o que falta)

| Peça | Estado |
|---|---|
| `MarketplaceAccount.platform` aceita `'bling'` + coluna legada `api_key` | existe (do design antigo de API key — **não** usar p/ v3) |
| `BACKEND/services/bling_service.py` | existe, **desatualizado** (trata como API key estática; host `www.bling.com.br`; sem OAuth/refresh) → **reescrever** |
| `services/crypto.encrypt/decrypt` (Fernet, `NFE_CERT_MASTER_KEY`) | existe — usar p/ cifrar os tokens |
| Config `BLING_CLIENT_ID/SECRET/REDIRECT_URI` | **falta** em `config.py` (só citado no `.env.example`) → adicionar |
| Tabela por-CMIG de conexão Bling | **falta** → nova (migration numerada em `Scripts SQL/`) |
| Router `/api/v1/integrations/bling` | **falta** → novo (espelha `routers/google_drive.py`) |
| Permissão de ação `bling_gerenciar` (ADR-0036) | **falta** → nova chave + seed |
| Card de Bling no front (por CMIG) | **falta** → novo (espelha o card do Google Drive em IntegrationsView) |

## Fluxo da conexão (alvo)

```
Tela (CMIG X) → GET /integrations/bling/authorize?cmig_id=X
   ↳ valida assert_cmig_access + permissão bling_gerenciar
   ↳ monta state ASSINADO/CIFRADO {cmig_id:X, nonce, ts}  (crypto)
   ↳ devolve a URL de consentimento do Bling
Usuário autoriza no Bling
Bling → GET /integrations/bling/callback?code=...&state=...   (SEM JWT — quem chama é o Bling)
   ↳ valida/decifra o state → extrai cmig_id; troca o code (server-side, Basic auth)
   ↳ cifra access/refresh (crypto) e faz upsert na tabela por-CMIG
Uso: bling_service.get_valid_token(db, cmig_id)
   ↳ decifra; se perto de expirar/401 → refresh SOB LOCK; persiste o novo par (rotaciona)
```

## Pontos que já têm solução pronta no codebase (reusar, não reinventar)

- **Cifragem de segredo:** `services/crypto` (mesmo usado por ASAAS, banco do galpão, Google Drive).
- **Callback sem login + página que fecha sozinha:** `routers/google_drive.py::callback` + `_pagina`.
- **Escopo por CMIG:** `assert_cmig_access` / `_check_cmig_access` (como nos routers fiscais).
- **Permissão de ação editável por perfil:** `services/action_permissions.py` + `require_permission`
  (ADR-0036) — criar a chave `bling_gerenciar`.
- **Absolutizar URL de imagem** antes de mandar ao Bling: `PUBLIC_BASE_URL` (como ML/Shopee).
- **Achatamento de endereço do comprador** (ML manda `{id,name}`): `services/address_parser`.
- **Dedupe de webhook:** tabela/padrão `webhook_events` (ASAAS/ML).

## Decisões de arquitetura a registrar (ADR) antes de ir além da conexão

1. **Papel do Bling por CMIG:** espelho de catálogo/estoque? emissor fiscal? origem de pedidos? Isso
   muda tudo que vem depois da conexão.
2. **Direção do estoque** (quem é a verdade — SSOT local event-sourced × Bling) para **não** dupla-contar
   (ADR-0004/0019).
3. **Fiscal:** se o Bling emitir NF-e, **série própria** separada (não colidir com própria/ML/Shopee);
   se a emissão própria SEFAZ continua a verdade, o Bling **não** re-emite (anexa/espelha).

## Escopo da 1ª entrega (recomendado)

**Só a CONEXÃO** (connect / status / disconnect / test), sem sincronizar nada ainda — igual ao Google
Drive foi entregue antes de ter consumidor. Sincronização é **fase seguinte**, com sua ADR e auditoria.

## Roadmap confirmado pelo dono (2026-11-08)

- **Fase 1 (atual):** só conectar a CMIG ao Bling (OAuth).
- **Fase 2+ (direção = Bling → Sistema Drop, LEITURA):** **importar** do Bling as **categorias**, os
  **produtos** e os **kits** já cadastrados na conta Bling da CMIG. Ou seja, o Bling é **origem de
  catálogo**; o endpoint-chave será `GET /categorias/produtos`, `GET /produtos` (com variações) e a
  montagem de **kit** (produto composto). Mapear para o modelo do Sistema Drop (CMIGProduct / catálogo
  PG / kits — ver ADR-0023 para kit = estoque derivado dos componentes). **Não** empurrar nada ao Bling
  nesta direção; estoque segue SSOT local (ADR-0004/0019) — importar catálogo ≠ importar saldo.

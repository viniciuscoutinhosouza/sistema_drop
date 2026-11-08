# Bling v3 — Autenticação OAuth 2.0

> Fonte: `developer.bling.com.br` (seção Aplicativos/Autorização). Itens **[confirmar]** não foram
> validados ao vivo nesta base. O Bling **migra o token opaco → JWT**: a estrutura do token muda, mas o
> **fluxo** OAuth abaixo permanece.

## Visão geral do fluxo (Authorization Code)

```
1. App manda o usuário para a URL de AUTORIZAÇÃO (tela de consentimento do Bling)
2. Usuário autoriza na conta Bling dele
3. Bling redireciona para o seu redirect_uri?code=XXXX&state=YYYY   (code expira em 30s!)
4. Backend troca o code por {access_token, refresh_token} no endpoint de TOKEN
5. Guarda os tokens CIFRADOS; usa o access_token no header Bearer
6. Antes de expirar (ou em 401), renova com grant_type=refresh_token
```

É o **único** grant suportado (não há client_credentials/implicit). A troca e o refresh são
**server-side** (o `client_secret` nunca vai ao frontend).

## 1. URL de autorização

```
GET https://www.bling.com.br/Api/v3/oauth/authorize
      ?response_type=code
      &client_id=<CLIENT_ID>
      &state=<aleatório/assinado>        # anti-CSRF; no Sistema Drop carrega o cmig_id
      &redirect_uri=<opcional>           # Bling usa o cadastrado no app, ignora o enviado
      &scope=<opcional>                  # idem: usa o do cadastro
```

- `redirect_uri` e `scope` são **opcionais** e, na prática, **ignorados** — o Bling usa os valores do
  **cadastro do aplicativo**. Configure-os no painel.
- `state` é **essencial**: valide no callback para prevenir CSRF. No Sistema Drop ele carrega **qual
  CMIG** está conectando (o callback é sem login — quem chama é o Bling).
- **[confirmar]** o host exato (`www.bling.com.br` para a tela de consentimento; alguns SDKs usam
  `bling.com.br/b/Api/v3/oauth/authorize`).

## 2. Troca do code por tokens

```
POST https://www.bling.com.br/Api/v3/oauth/token          # [confirmar] host (api.bling.com.br também aparece)
Headers:
  Authorization: Basic base64("<CLIENT_ID>:<CLIENT_SECRET>")
  Content-Type: application/x-www-form-urlencoded
  Accept: 1.0                                             # [confirmar] alguns exigem o header de versão
Body (form-urlencoded):
  grant_type=authorization_code
  code=<code recebido>
```

- **Credenciais vão no header Basic** (base64 de `client_id:client_secret`), **nunca no body** — a doc
  proíbe o par no corpo.
- O `code` **expira em 30 segundos** → troque imediatamente, no servidor, logo no callback.

### Resposta (exemplo)
```json
{
  "access_token": "eyJ...",          // Bearer (opaco hoje; JWT na migração)
  "token_type": "Bearer",
  "expires_in": 21600,               // ~6h  [confirmar]
  "scope": "...",
  "refresh_token": "def502..."       // validade ~30 dias
}
```

## 3. Renovação (refresh)

```
POST https://www.bling.com.br/Api/v3/oauth/token
Headers: Authorization: Basic base64(client_id:client_secret); Content-Type: application/x-www-form-urlencoded
Body:
  grant_type=refresh_token
  refresh_token=<refresh atual>
```

- Devolve um **novo** `access_token` **e um novo** `refresh_token`. **Persista os dois** — o refresh
  **rotaciona**; se você guardar só o access, perde a conexão quando ele expirar.
- O **refresh_token expira em ~30 dias**. Se a CMIG ficar >30 dias sem uso/refresh, a conexão **morre** e
  exige **reautorizar** (igual ao `requires_reauth` do ML/Shopee). Agende um refresh proativo (ex.: job
  semanal) para manter vivo, ou renove sempre antes de expirar.
- Trate **401** nas chamadas de recurso como gatilho de refresh + **replay** da chamada original.

## 4. Revogação

```
POST https://www.bling.com.br/Api/v3/oauth/revoke          # [confirmar] parâmetros exatos
Headers: Authorization: Basic base64(client_id:client_secret)
Body:  (indica qual token revogar — access ou refresh)
```

Use ao **desconectar** a conta no sistema (limpeza do lado do Bling). Mesmo sem revogar, apagar os
tokens locais já desconecta do lado do sistema.

## 5. Escopos (scopes)

- Definidos **no cadastro do app** (painel), não por requisição.
- **Alterar os escopos revoga TODOS os usuários** do app ao salvar → todos precisam reautorizar.
  Planeje o conjunto de escopos **antes** de produção.
- Escopos cobrem áreas (produtos, estoques, pedidos de venda, NF-e, contatos, etc.). **[confirmar]** os
  nomes exatos no painel do app do dono e marque só o necessário (princípio do menor privilégio).

## 6. Migração token opaco → JWT

O Bling anunciou a **descontinuação do token opaco** em favor de **JWT**. Impacto prático:
- O **fluxo OAuth não muda** (authorize/token/refresh iguais).
- O **formato** do `access_token` passa a ser um JWT (decodificável). **Não** faça parse assumindo opaco
  nem assuma tamanho fixo de coluna curto — guarde o token como texto amplo.
- **[confirmar]** prazos/obrigatoriedade da migração na doc antes de ir a produção.

## Erros comuns de OAuth

| Sintoma | Causa provável |
|---|---|
| `invalid_grant` na troca | code expirou (>30s) ou já foi usado; `redirect_uri` divergente |
| `invalid_client` | Basic header mal montado (base64 errado) ou secret redefinido no painel |
| 401 nas chamadas | access_token expirado → refresh; ou escopo faltando (reautorizar após mudar escopo) |
| Conexão "morre" sozinha | refresh_token passou de 30 dias sem renovar → reautorizar |

## Checklist de segurança (Sistema Drop)

- Tokens **cifrados** em repouso (Fernet, `services/crypto.encrypt/decrypt`).
- Troca/refresh **server-side**; callback é a **única** rota sem JWT (quem chama é o Bling) e só aceita
  um `code` de uso único + valida o `state`.
- Refresh **sob lock** por CMIG (evita corrida que invalida o refresh rotacionado).

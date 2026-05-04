# Autenticação e autorização — OAuth 2.0

Referência completa para o fluxo de autenticação do Mercado Livre. Leia este documento por inteiro antes de implementar OAuth — pular detalhes aqui leva a 90% dos bugs em integrações novas.

## Sumário

1. [Conceitos](#conceitos)
2. [Cadastro da aplicação](#cadastro-da-aplicação)
3. [Fluxo completo (Server-side)](#fluxo-completo-server-side)
4. [Refresh token](#refresh-token)
5. [Quando o token fica inválido](#quando-o-token-fica-inválido)
6. [Usuários de teste](#usuários-de-teste)
7. [Erros comuns e soluções](#erros-comuns-e-soluções)
8. [Template de código (Node/TypeScript)](#template-de-código-nodetypescript)

## Conceitos

- **APP_ID** (client_id): identificador público da aplicação. Pode ficar no front se precisar.
- **Secret Key** (client_secret): segredo da aplicação. **Jamais expor.** Só usar no backend.
- **Authorization code**: código temporário (~10 min de vida) recebido após o usuário autorizar.
- **Access token**: token Bearer usado em todas as chamadas. Vida útil: **6 horas (21600s)**.
- **Refresh token**: token de longa duração (6 meses) usado para gerar novo access token. **Single-use**: cada refresh emite um novo refresh_token e invalida o anterior.
- **Scopes**: `read`, `write`, `offline_access`. Para aplicações que rodam em background (cron, workers), `offline_access` é obrigatório.

## Cadastro da aplicação

Acesse `https://developers.mercadolivre.com.br/devcenter` → "Criar nova aplicação".

**Campos críticos:**

- **URI de redirect**: deve ser exatamente igual à URL que receberá o `code`. Não pode conter parâmetros variáveis. Ex: `https://meusistema.com.br/auth/ml/callback`. Em desenvolvimento, registre a URL do `ngrok` (ex: `https://abc123.ngrok.io/auth/ml/callback`).
- **Scopes**: marque `read`, `write` e `offline_access`. Sem `offline_access` o refresh não funciona em scripts de background.
- **Tópicos**: marque os webhooks que vai consumir (recomendo começar com `orders_v2`, `items`, `messages`, `shipments`, `questions`).
- **URL de callback de notificações**: endpoint público que receberá os webhooks via POST.

**Observação:** se ao salvar os tópicos não persistirem, abra a seção "Outros", marque qualquer tópico, salve, depois volte e ajuste — é um bug conhecido do DevCenter.

## Fluxo completo (Server-side)

### Passo 1 — Redirecionar usuário para a página de autorização

Monte a URL de autorização usando o domínio do **país** do vendedor:

| País | Domínio |
|---|---|
| Brasil | `auth.mercadolivre.com.br` |
| Argentina | `auth.mercadolibre.com.ar` |
| México | `auth.mercadolibre.com.mx` |
| Chile | `auth.mercadolibre.cl` |
| Colômbia | `auth.mercadolibre.com.co` |

```
https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=APP_ID&redirect_uri=REDIRECT_URI&state=CSRF_TOKEN_ALEATORIO
```

**`state`** é obrigatório por segurança: gere um valor aleatório por sessão, salve no servidor, e valide no callback. O ML repassa o valor de volta sem alterar — se não bater, o callback foi forjado.

### Passo 2 — Receber o code no callback

O ML redireciona o navegador para:

```
https://meusistema.com.br/auth/ml/callback?code=TG-65d65b17d124c20001f0c119-1694513136&state=CSRF_TOKEN
```

**Obrigatório fazer:**
1. Validar `state` contra o salvo no servidor.
2. Verificar que o usuário logado é **administrador da conta**, não operador/colaborador. Se for operador, retorna erro `invalid_operator_user_id`.
3. Trocar o `code` por tokens **imediatamente** (vida curta).

### Passo 3 — Trocar code por access_token

```bash
curl -X POST \
  -H 'accept: application/json' \
  -H 'content-type: application/x-www-form-urlencoded' \
  'https://api.mercadolibre.com/oauth/token' \
  -d 'grant_type=authorization_code' \
  -d 'client_id=APP_ID' \
  -d 'client_secret=CLIENT_SECRET' \
  -d 'code=AUTHORIZATION_CODE' \
  -d 'redirect_uri=REDIRECT_URI'
```

Resposta:

```json
{
  "access_token": "APP_USR-123456-090515-...",
  "token_type": "bearer",
  "expires_in": 21600,
  "scope": "offline_access read write",
  "user_id": 8035443,
  "refresh_token": "TG-5b9032b4e4b0714aed1f959f-8035443"
}
```

**Persistir imediatamente** (ver schema em "Template de código"):
- `user_id` (PK)
- `access_token`
- `refresh_token`
- `expires_at` = `now() + expires_in`
- `scope`
- `updated_at`

### Passo 4 — Usar o access_token

Toda chamada à API:

```bash
curl -H 'Authorization: Bearer APP_USR-123456-090515-...' \
  https://api.mercadolibre.com/users/me
```

`/users/me` é o endpoint padrão para validar que o token funciona.

## Refresh token

**Quando renovar:** antes de expirar. Recomendado: renovar quando faltarem menos de 30 minutos para `expires_at`. Não esperar o 401.

```bash
curl -X POST \
  -H 'accept: application/json' \
  -H 'content-type: application/x-www-form-urlencoded' \
  'https://api.mercadolibre.com/oauth/token' \
  -d 'grant_type=refresh_token' \
  -d 'client_id=APP_ID' \
  -d 'client_secret=CLIENT_SECRET' \
  -d 'refresh_token=REFRESH_TOKEN'
```

A resposta tem o **mesmo formato** do passo 3, com **novo** `access_token` E **novo** `refresh_token`. Atualize ambos no banco.

⚠️ **Crítico — race condition:** se duas requisições paralelas tentarem refresh ao mesmo tempo, uma vai usar o refresh_token e invalidar para a outra. Solução: implementar **lock distribuído** (Redis lock, advisory lock no Postgres, etc.) na operação de refresh, ou **fila única** que serializa refreshes por `user_id`.

⚠️ **Refresh tokens são single-use.** Se você ainda tiver o refresh_token antigo salvo em algum lugar (cache, log, backup), descarte. Apenas o último emitido funciona.

## Quando o token fica inválido

Eventos que invalidam um access_token antes da expiração natural:

1. Usuário trocou senha no Mercado Livre.
2. Aplicação fez refresh do `Secret Key` (no DevCenter).
3. Usuário revogou permissões da aplicação.
4. Aplicação não fez nenhuma chamada por **4 meses** (o ML "esquece" a integração).
5. Eventos internos do ML (fraude, exclusão de seção do usuário).

Detecção: chamada retorna `401 Unauthorized` com algum dos erros:

- `invalid_token` → tentar refresh.
- `invalid_grant` no refresh → token revogado, **necessário refazer o fluxo OAuth do zero** com o usuário.

Implemente um fluxo de "reautorização": detectar `invalid_grant`, marcar o usuário como `requires_reauth=true`, e exibir botão de reconectar quando ele acessar o sistema.

## Usuários de teste

Como o ML não tem sandbox, use usuários de teste para experimentar sem afetar conta real.

### Criar usuário de teste

```bash
curl -X POST \
  -H 'Authorization: Bearer SEU_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"site_id":"MLB"}' \
  https://api.mercadolibre.com/users/test_user
```

Resposta:

```json
{
  "id": 123456789,
  "nickname": "TESTUSER123456",
  "password": "abc123def456",
  "site_status": "active",
  "email": "test_user_123456@testuser.com"
}
```

**Limitações dos usuários de teste:**

- Só podem operar dentro do `site_id` para o qual foram criados.
- Não recebem dinheiro real.
- Têm reputação simulada.
- Você pode logar como eles em `https://www.mercadolivre.com.br/jms/mlb/lgz/login` com o nickname/senha retornados.
- Cada conta real pode criar até 10 usuários de teste por site.

## Erros comuns e soluções

| Sintoma | Causa | Solução |
|---|---|---|
| `Sorry, the application cannot connect to your account.` | `redirect_uri` não bate com o cadastrado | Conferir caractere por caractere no DevCenter, sem barra no final se cadastrou sem |
| `invalid_operator_user_id` | Usuário logado é operador/colaborador, não admin | Pedir para o admin da conta fazer o login no fluxo OAuth |
| `invalid_grant` ao trocar code | Code já foi usado, expirou (>10min), ou redirect_uri diferente | Reiniciar o fluxo do passo 1 |
| `invalid_grant` ao refresh | refresh_token revogado ou já usado | Reautorizar do zero |
| Token funciona em alguns endpoints e não em outros | Scope insuficiente | Refazer autorização com `read write offline_access` |
| Webhook não chega após autorização | `offline_access` não foi solicitado, app não foi usada por 4 meses | Validar scopes; chamar `/users/me` periodicamente em apps inativas |

## Template de código (Node/TypeScript)

Schema sugerido para persistência (Postgres):

```sql
CREATE TABLE ml_tokens (
  user_id BIGINT PRIMARY KEY,
  access_token TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  scope TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Middleware de cliente HTTP que injeta token e renova se necessário:

```typescript
// ml-client.ts
import axios, { AxiosInstance } from 'axios';

interface TokenRecord {
  user_id: number;
  access_token: string;
  refresh_token: string;
  expires_at: Date;
}

const REFRESH_THRESHOLD_MS = 30 * 60 * 1000; // 30 min

export class MercadoLivreClient {
  private http: AxiosInstance;

  constructor(
    private userId: number,
    private repo: TokenRepository, // sua camada de persistência
    private appId: string,
    private clientSecret: string,
  ) {
    this.http = axios.create({
      baseURL: 'https://api.mercadolibre.com',
      timeout: 10000,
    });

    this.http.interceptors.request.use(async (config) => {
      const token = await this.getValidAccessToken();
      config.headers.Authorization = `Bearer ${token}`;
      return config;
    });
  }

  private async getValidAccessToken(): Promise<string> {
    const record = await this.repo.findByUserId(this.userId);
    if (!record) throw new Error('Usuário não autorizado');

    const msUntilExpiry = record.expires_at.getTime() - Date.now();
    if (msUntilExpiry > REFRESH_THRESHOLD_MS) {
      return record.access_token;
    }

    // Lock distribuído antes de refresh para evitar race condition
    return await this.repo.withLock(this.userId, async () => {
      // Recheck após pegar o lock
      const fresh = await this.repo.findByUserId(this.userId);
      if (fresh.expires_at.getTime() - Date.now() > REFRESH_THRESHOLD_MS) {
        return fresh.access_token;
      }
      return await this.refreshToken(fresh.refresh_token);
    });
  }

  private async refreshToken(refreshToken: string): Promise<string> {
    const params = new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: this.appId,
      client_secret: this.clientSecret,
      refresh_token: refreshToken,
    });

    const { data } = await axios.post(
      'https://api.mercadolibre.com/oauth/token',
      params.toString(),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    );

    await this.repo.upsert({
      user_id: data.user_id,
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at: new Date(Date.now() + data.expires_in * 1000),
    });

    return data.access_token;
  }

  // Métodos públicos: get, post, put, delete...
  async get<T>(path: string, params?: object): Promise<T> {
    const { data } = await this.http.get<T>(path, { params });
    return data;
  }
}
```

**Pontos a destacar para o usuário:**

1. O lock distribuído na operação de refresh é o que mais quebra em produção quando esquecido.
2. O `recheck após pegar o lock` evita refreshes desnecessários quando outra requisição já renovou.
3. Sempre logar tentativas de refresh (sem expor o token!) para debugar problemas de autorização.
4. Implementar circuit breaker se o ML estiver indisponível, para não martelar a API.

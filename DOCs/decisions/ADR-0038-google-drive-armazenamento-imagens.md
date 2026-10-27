# ADR-0038 — Armazenamento de imagens no Google Drive (OAuth2 drive.file)

**Status:** Aceita (implementada — 2026-10-27; conectada em produção)
**Relaciona:** [ADR-0003](ADR-0003-jwt-localstorage.md) (segredos), [ADR-0026](ADR-0026-papel-galpao-unificado.md) (escopo por galpão), [ADR-0005](ADR-0005-separacao-picking-cart.md) (1º consumidor: fotos da separação)

## Contexto

As imagens do sistema (fotos de produto, anúncios, uploads) iam para o **disco local** do servidor
em `static/uploads/<area>/`, servidas publicamente em `/static`. Dois problemas: (1) disco local da
VM micro não tem durabilidade/backup; (2) URL `/static` é **pública** — quem tem o link vê a imagem
sem login. Para a foto de **separação** (que pode mostrar a etiqueta com **nome/endereço do
cliente** — dado pessoal, LGPD) isso não serve. O dono pediu para guardar as imagens na conta
**Google Drive** dele, organizadas em pastas (padrão já usado no projeto MIG).

## Decisão

Integração **OAuth2 de usuário** com o Google Drive (replica o padrão do MIG), escopo **`drive.file`**.

- **Escopo `drive.file`** (acesso só aos arquivos que o SISTEMA cria): classificado como **não
  sensível** → o Google **não exige verificação do app** (semanas de espera). **Proibido** trocar
  por `drive`/`drive.readonly` (caem em verificação e dão acesso a todo o Drive do usuário).
- **Conta de serviço NÃO serve** (grava só em Shared Drive, que não existe fora do Workspace) →
  OAuth de usuário com `access_type=offline` + `prompt=consent` para obter o **refresh_token**.
- **App PUBLICADO** no Console (modo Testing expira o refresh em 7 dias).
- **Tokens:** `refresh_token` e `access_token` **CIFRADOS em repouso** (Fernet, `services/crypto`,
  master `NFE_CERT_MASTER_KEY`). Uma conexão ativa por vez (`google_drive_accounts.is_active`,
  migration 167), admin-only.
- **Topologia:** pasta raiz **`Ecommerce_Imagens`** (criada via API ao conectar) + **subpastas por
  área** criadas sob demanda (`Separacao`, e as próximas). `ensure_folder` idempotente por (nome,pai).
- **Download servido PELO sistema, NUNCA por link público** (LGPD): o `webViewLink` não é exposto;
  o arquivo é baixado por um endpoint autenticado **e escopado por galpão** — o id do Drive **não é
  credencial**. (Ver a regra de escopo abaixo — é o ponto que a auditoria barrou e que foi corrigido.)
- **Callback público** (`/integrations/google-drive/callback`): única rota sem JWT (quem chama é o
  Google); só aceita o `code` de uso único, troca server-side, não vaza nada.
- **Config admin-only** (`is_global`); credenciais (`GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`) só no
  `.env` do servidor, nunca no git.
- **Falha-alto quando não configurado/conectado:** o consumidor **bloqueia** (503/409), não degrada
  em silêncio — ex.: a separação não deixa marcar "Separado" sem o Drive conectado.

### Regra de escopo do acesso à imagem (obrigatória para todo consumidor)
O endpoint que serve a imagem **resolve o `drive_file_id` a partir do registro de domínio ESCOPADO**
(ex.: `picking_cart_orders.separation_photos_json` da gaiola do galpão do usuário), **nunca** aceita
o id cru do Drive como parâmetro de busca — senão qualquer usuário com a permissão baixaria a imagem
de outro galpão (IDOR/vazamento de PII, ADR-0026). Ex. implementado:
`GET /separation/carts/{cart_id}/orders/{order_id}/photo/{idx}` → `_get_cart_scoped` → resolve o id
pelo índice dentro do JSON daquele pedido.

## Consequências
- **Positivas:** durabilidade (conta Google do dono, 15 GB grátis + Google One), imagem de cliente
  protegida (servida só autenticada e escopada), organização por pastas, custo zero de dependências
  (REST via httpx, sem as libs Google).
- **Custos/limites:** depende de o dono criar e **publicar** o app OAuth; 15 GB são compartilhados
  com Gmail/Fotos (a tela avisa aos 80%); uploads validados (magic byte jpg/png/webp, ≤5 MB, ≤10 por
  pedido) para não estourar memória/cota.
- **Convivência com `static/uploads/`:** o Drive entra primeiro para as fotos NOVAS de separação; as
  demais imagens (produto/anúncio) seguem em `static/uploads` por ora. Migrar o resto para o Drive é
  follow-up (manter os dois backends até lá).

## Follow-ups
- Migrar os demais uploads de imagem (produto/anúncio) para o Drive.
- `state` aleatório por sessão no OAuth (anti-CSRF) no lugar do fixo.
- Tela de histórico das fotos de separação (consumindo o endpoint escopado).

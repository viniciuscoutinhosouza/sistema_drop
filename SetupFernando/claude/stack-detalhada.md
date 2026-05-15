# Stack Detalhada — Implicações Práticas

> Detalhamento de cada item da stack padrão: estrutura esperada,
> gerenciadores, variáveis de ambiente, cuidados específicos de cada
> serviço.
>
> Localização: `~/.claude/stack-detalhada.md`
> Referenciado pelo CLAUDE.md global. Consultado sob demanda — pode ser
> denso, não é lido toda sessão.
>
> Estes são defaults globais. O CLAUDE.md de cada projeto pode
> sobrescrever; mudança de qualquer item da stack de um projeto exige ADR.

---

## Python

- Gerenciador de dependências: `uv` (preferencial) ou `poetry`.
- Linter / formatter: `ruff`.
- Type checker: `mypy` ou `pyright`.
- Testes: `pytest`.
- Estrutura padrão: `src/<package>/` + `tests/`.
- Versão: Python 3.11+ por padrão.

---

## Supabase

- **Auth:** Supabase Auth. Não rolar autenticação manual sem ADR justificando.
- **Storage:** Supabase Storage para arquivos do usuário.
- **Realtime:** via SDK oficial, quando fizer sentido.
- **Migrações:** Supabase CLI, arquivos versionados em `supabase/migrations/`.
- **RLS (Row Level Security):** sempre ativada em tabelas com dados de usuário. O guardião de qualidade valida isso.
- **Chaves:** `SUPABASE_URL` e `SUPABASE_ANON_KEY` no `.env` (nunca commitar). A `service_role` key apenas no backend, nunca exposta ao cliente.
- **Verificação de JWT:** o Supabase assina tokens com ECC P-256. Verificação local com HS256 (`python-jose`, `jwt.decode()` com `SUPABASE_JWT_SECRET`) falha para tokens novos. Verificar autenticação via `supabase.auth.get_user(token)`, não localmente. *(Quirk de origem do Hard Solution — vale como cuidado geral para qualquer projeto Supabase.)*

---

## Oracle Cloud (OCI)

- **Autenticação:** OCI CLI configurada localmente (`~/.oci/config`).
- **Compute:** instâncias Always Free quando o caso permitir (Ampere ARM A1).
- **Networking:** VCN dedicada por projeto, subnets públicas/privadas separadas.
- **Storage:** Object Storage para arquivos, Block Volume para persistência de VMs.
- **Secrets:** OCI Vault — nunca hardcoded.
- **Custos:** estimar custo antes de provisionar.
- **Backup:** snapshots automáticos configurados desde o provisionamento.

---

## Firebase Hosting

Firebase Hosting é usado para **conteúdo estático** (sites institucionais, landing pages). Aplicação dinâmica (login, cadastro, área logada, sistema) roda no servidor Oracle.

O padrão comum é uma **arquitetura split sob o mesmo domínio**:
- Site estático → Firebase Hosting (ex: `cliente.com.br`)
- Sistema / aplicação → subdomínio apontando para o servidor Oracle (ex: `sistema.cliente.com.br`)

Configuração de domínio pode ser feita tanto no Firebase (para a parte estática) quanto no Oracle (para o subdomínio do sistema) — não é exclusivo de um lado.

- Deploy do estático via `firebase deploy` ou GitHub Actions.
- Configuração em `firebase.json` versionada.
- Environments: usar Firebase Hosting Channels para staging/preview.
- Uso restrito a **hosting**. Outros serviços Firebase (Firestore, Functions) só com ADR explícito autorizando.

---

## BotConversa (WhatsApp)

O BotConversa, neste setup, é usado como **destino de webhook** — não como plataforma integrada via API ou SDK.

- O sistema dispara webhooks para o BotConversa quando um evento de negócio ocorre.
- Toda a configuração do lado do BotConversa (fluxos, automações, o que acontece ao receber o webhook) é feita **manualmente por Fernando, no portal do BotConversa**. Não é responsabilidade do código.
- O código precisa apenas: conhecer a URL de webhook de destino e disparar o POST no momento certo.
- A URL do webhook é configuração — fica no `.env`, nunca hardcoded.
- Não há SDK oficial nem API REST a integrar. Não inventar camada de integração além do disparo de webhook.
- Documentar em `docs/whatsapp-flows.md` *quais eventos disparam webhook e para quê* — não a configuração interna do BotConversa, que é manual e externa.

---

## GitHub

- Repositórios privados por default.
- Branch principal: `main`.
- Branches de feature: `feat/<descrição-curta>`.
- Pull requests obrigatórios para mudanças em `main` em projetos de produção.
- `.gitignore` deve excluir: `.env`, `__pycache__`, `node_modules`, `.venv`, `dist/`, `build/`.
- Tags semânticas para releases (`v0.1.0`, `v1.0.0`).

---

## GitHub Actions

- Workflows em `.github/workflows/`.
- Secrets configurados no painel do GitHub (nunca no código).
- CI mínimo: lint + testes em todo PR.
- Deploy condicional: só após PR aprovado em `main`.

---

## Resend (email transacional)

- API key no `.env`: `RESEND_API_KEY` (nunca commitar).
- Domínio remetente configurado e verificado no painel Resend antes de qualquer envio em produção.
- Para Python: SDK oficial `resend` (`uv add resend`).
- Templates de email versionados em `src/<package>/emails/templates/`.
- Em produção, `from` sempre de domínio próprio verificado (nunca `onboarding@resend.dev`).
- Respeitar rate limits do Resend — retry com backoff exponencial em falhas transientes.
- Registrar logs de envio (sucesso/falha), sem incluir o conteúdo do email (PII).
- Em desenvolvimento: usar email de teste do Resend ou Mailtrap; nunca enviar para emails reais.

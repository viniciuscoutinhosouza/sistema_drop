# Setup Claude Code — Guia de Instalação Completo

> Setup de engenharia com Claude Code: agentes especializados, regras de trabalho,
> processos de discovery, auditoria automática e integração com Stitch (design via IA).
> Baseado no setup de Fernando Almeida — adaptado para uso geral.

---

## O que você vai ter ao final

- **15 agentes especializados** (backend, frontend, debug, segurança, discovery, deploy, migração, etc.)
- **Processo de trabalho estruturado** com regras invioláveis, procedimentos e verificações automáticas
- **Auditoria tripla** antes de fechar qualquer fase (qualidade técnica + consistência funcional + ADRs)
- **Discovery profissional** para projetos de sistema e websites com roteiro de entrevista automático
- **Integração com Stitch** (Google) para geração de UI via IA diretamente no Claude Code
- **Stack padrão**: Python/FastAPI + Next.js + Supabase + OCI + Firebase Hosting

---

## Pré-requisitos

Instale antes de começar:

| Ferramenta | Download | Observação |
|---|---|---|
| **Claude Code** | `npm install -g @anthropic-ai/claude-code` | Requer Node.js 18+ |
| **Node.js 18+** | https://nodejs.org | LTS recomendado |
| **Git** | https://git-scm.com | Com Git Bash no Windows |
| **Python 3.11+** | https://python.org | Adicionar ao PATH |
| **uv** (gerenciador Python) | `pip install uv` | Alternativa ao pip |
| **Docker Desktop** | https://docker.com | Para deploy local |
| **VS Code** | https://code.visualstudio.com | Com extensão Claude Code |

---

## Passo 1 — Instalar e autenticar o Claude Code

```bash
# Instalar globalmente
npm install -g @anthropic-ai/claude-code

# Autenticar (abre browser)
claude

# Verificar
claude --version
```

---

## Passo 2 — Criar a pasta de projetos

Escolha onde vai guardar seus projetos. O setup usa `C:\_SeusProjetos` como padrão.
Pode ser qualquer pasta — só precisa ser consistente.

```powershell
# Exemplo:
New-Item -ItemType Directory -Force -Path "C:\_SeusProjetos"
```

---

## Passo 3 — Copiar os arquivos do setup para ~/.claude

```powershell
# Copiar agentes
Copy-Item "claude\agents\*" -Destination "$env:USERPROFILE\.claude\agents\" -Force -Recurse

# Copiar arquivos globais
Copy-Item "claude\CLAUDE.md" -Destination "$env:USERPROFILE\.claude\" -Force
Copy-Item "claude\stack-detalhada.md" -Destination "$env:USERPROFILE\.claude\" -Force
Copy-Item "claude\ferramentas-conhecidas.md" -Destination "$env:USERPROFILE\.claude\" -Force

# Copiar lições aprendidas
Copy-Item "claude\licoes-aprendidas.md" -Destination "C:\_SeusProjetos\" -Force
```

Se usar uma pasta diferente de `C:\_SeusProjetos`, ajuste o path acima e depois
edite `~/.claude/CLAUDE.md` — procure `_SeusProjetos` e substitua pelo seu path.

---

## Passo 4 — Configurar o settings.json

```powershell
Copy-Item "claude\settings.json" -Destination "$env:USERPROFILE\.claude\" -Force
```

Depois edite `~/.claude/settings.json` e substitua:
- `SEU_TOKEN_GITHUB_AQUI` → seu Personal Access Token do GitHub
  (github.com → Settings → Developer Settings → Personal access tokens → Tokens classic → repo, workflow)
- `SEU_TOKEN_SUPABASE_AQUI` → seu Access Token do Supabase
  (supabase.com → Account → Access Tokens)

Se não usar GitHub ou Supabase ainda, pode deixar como está ou remover as linhas.

---

## Passo 5 — Configurar o Stitch MCP (design via IA)

O Stitch é uma ferramenta do Google que gera interfaces visuais a partir de texto.
Integra diretamente com o Claude Code via MCP.

### 5.1 — Rodar o setup
```bash
npx @_davideast/stitch-mcp init
```

No wizard interativo:
1. **MCP client:** selecione `claude-code`
2. **Authentication Mode:** selecione `API Key`
3. **Store API Key:** selecione `MCP config`

### 5.2 — Obter a API Key
- Acesse [stitch.withgoogle.com](https://stitch.withgoogle.com)
- Faça login com conta Google
- Vá em **Settings** → **API Keys** → gere uma nova chave
- Cole no wizard quando solicitado

### 5.3 — Adicionar ao Claude Code
Com a chave em mãos, rode no terminal:
```bash
claude mcp add stitch \
  --transport http \
  --header "X-Goog-Api-Key: SUA_CHAVE_AQUI" \
  https://stitch.googleapis.com/mcp
```

---

## Passo 6 — Reiniciar o Claude Code

Feche e reabra o Claude Code (ou VS Code com a extensão Claude Code).
Os agentes e o Stitch MCP serão carregados automaticamente.

---

## Passo 7 — Verificar a instalação

Abra o Claude Code e teste:

```
Me lista os agentes que você tem disponíveis
```

Você deve ver os 15 agentes listados.

```
Qual é a Regra 0 do nosso processo de trabalho?
```

Claude deve responder com a regra de proporcionalidade (nível leve vs completo).

---

## Estrutura de pastas após instalação

```
~/.claude/
├── CLAUDE.md                    ← regras e procedimentos globais
├── settings.json                ← permissões e tokens
├── stack-detalhada.md           ← stack padrão com detalhes técnicos
├── ferramentas-conhecidas.md    ← quirks de ferramentas descobertos
└── agents/                      ← 25 agentes especializados
    ├── backend-specialist.md
    ├── frontend-specialist.md
    ├── quality-guardian.md
    ├── debug-specialist.md
    ├── discovery-guide.md
    ├── tech-lead.md
    ├── deploy-operator.md
    ├── security-hardening.md
    ├── supabase-auditor.md
    ├── consistency-auditor.md
    ├── adr-consistency-checker.md
    ├── session-closer.md
    ├── migration-specialist.md
    ├── design-bridge.md
    ├── cloud-architect.md
    └── ... (outros)

C:\_SeusProjetos\
└── licoes-aprendidas.md         ← lições aprendidas globais
```

---

## Como funciona no dia a dia

### Novo projeto
Diga "novo projeto" — o agente de discovery detecta automaticamente se é um sistema ou website e conduz o processo correto.

### Fechar uma fase
Diga "fechar esta fase" — Claude roda automaticamente:
1. `quality-guardian` — bugs e segurança
2. `consistency-auditor` — UX e CRUDs incompletos
3. `adr-consistency-checker` — código vs decisões arquiteturais

### Deploy
Diga "fazer o deploy" — `deploy-operator` executa o checklist R9 e bloqueia se algo falhar.

### Website com design via IA
Para projetos de site, após o discovery, Claude usa o Stitch MCP para gerar telas
a partir do texto, você aprova com o cliente e só então implementa. Zero retrabalho.

---

## Instalar ferramentas de segurança (opcional — para quem tem servidor Linux)

No servidor de produção (Ubuntu/Debian):
```bash
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin
pip3 install pip-audit semgrep --break-system-packages
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.profile
sudo apt install -y nmap
```

---

## Dúvidas

Qualquer comportamento estranho do Claude, verifique:
1. `~/.claude/CLAUDE.md` foi copiado corretamente?
2. `~/.claude/agents/` tem os 25 arquivos `.md`?
3. O path `_SeusProjetos` foi ajustado para o seu sistema?
4. O `settings.json` tem os tokens corretos?

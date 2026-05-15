# Setup Claude Code — Skills & Configuração

Cole este arquivo no Claude Code do novo desktop e diga:
**"Siga este guia para configurar meu ambiente Claude Code"**

---

## 1. Login

Entre com a conta: **vinicius.interessante@gmail.com**

> As skills do marketplace oficial sincronizam automaticamente com sua conta após o login.

---

## 2. Skills do Marketplace Oficial

No Claude Code, acesse **Skills** (ícone de puzzle na barra lateral) e instale:

### Desenvolvimento
| Skill | Para que serve |
|---|---|
| `commit-commands` | `/commit`, `/push`, `/pr` — git workflow simplificado |
| `code-review` | `/review` — revisão automática de PR com múltiplos agentes |
| `code-simplifier` | `/simplify` — simplifica código complexo |
| `feature-dev` | `/feature` — fluxo completo de desenvolvimento de feature |
| `hookify` | `/hook` — cria git hooks automaticamente |
| `pr-review-toolkit` | `/pr-review` — toolkit de revisão de PR |
| `security-guidance` | `/security` — análise de segurança |
| `code-modernization` | `/modernize` — atualiza código legado |

### Agentes & Plugins
| Skill | Para que serve |
|---|---|
| `agent-sdk-dev` | `/agent` — cria agentes customizados |
| `skill-creator` | `/skill` — cria novas skills |
| `plugin-dev` | `/plugin` — desenvolve plugins |
| `mcp-server-dev` | `/mcp` — cria servidores MCP |

### Gestão de Projeto
| Skill | Para que serve |
|---|---|
| `claude-code-setup` | `/setup` — configura projetos novos |
| `claude-md-management` | `/claudemd` — gerencia CLAUDE.md |
| `session-report` | `/report` — resumo da sessão de trabalho |
| `ralph-loop` | `/loop` — loop de melhoria iterativa |

### Estilo de Output
| Skill | Para que serve |
|---|---|
| `explanatory-output-style` | `/explain` — respostas mais detalhadas |
| `learning-output-style` | `/learn` — modo pedagógico |

### LSPs (Language Servers)
| Skill | Para que serve |
|---|---|
| `pyright-lsp` | Python — análise de tipos |
| `typescript-lsp` | TypeScript/JavaScript |
| `rust-analyzer-lsp` | Rust |
| `gopls-lsp` | Go |
| `ruby-lsp` | Ruby |
| `php-lsp` | PHP |
| `lua-lsp` | Lua |
| `clangd-lsp` | C/C++ |
| `kotlin-lsp` | Kotlin |
| `jdtls-lsp` | Java |
| `csharp-lsp` | C# |
| `swift-lsp` | Swift |

### Outros
| Skill | Para que serve |
|---|---|
| `playground` | `/play` — ambiente de testes |
| `frontend-design` | `/design` — sugestões de UI/UX |
| `math-olympiad` | `/math` — resolução de problemas matemáticos |

---

## 3. Plugins MCP (requerem configuração manual)

Estes plugins precisam de tokens/chaves próprias:

### Discord
```
No menu Skills > External Plugins > discord
Necessário: Bot Token do Discord
```

### Telegram
```
No menu Skills > External Plugins > telegram
Necessário: Bot Token do Telegram (@BotFather)
```

---

## 4. Permissões de projeto (settings.json)

Crie o arquivo `%USERPROFILE%\.claude\settings.json` com:

```json
{
  "permissions": {
    "allow": [
      "Bash(ssh -i /c/sistema_drop/ssh-key-2026-05-08.key -o StrictHostKeyChecking=no ubuntu@163.176.165.201 ' *)",
      "Bash(scp -i /c/sistema_drop/ssh-key-2026-05-08.key -r /c/sistema_drop/Wallet_MIGECOMMERCE ubuntu@163.176.165.201:/home/ubuntu/Wallet_MIGECOMMERCE)"
    ]
  },
  "autoUpdatesChannel": "latest",
  "theme": "light"
}
```

> Ajuste o caminho da chave SSH conforme o novo desktop.

---

## 5. Projeto Sistema Drop

```bash
git clone https://github.com/viniciuscoutinhosouza/sistema_drop.git c:\sistema_drop
```

Depois copie os arquivos que NÃO estão no git:
- `BACKEND/.env` (credenciais Oracle, JWT, ML, Shopee)
- `BACKEND/Wallet_MIGECOMMERCE/` (wallet Oracle ATP)
- `ssh-key-2026-05-08.key` (chave SSH do servidor Oracle Cloud)

---

## 6. Verificação final

Abra o projeto `c:\sistema_drop` no Claude Code e verifique:
- [ ] Skills instaladas aparecem no menu `/`
- [ ] `CLAUDE.md` carregado (aparece no contexto)
- [ ] Backend inicia: `cd BACKEND && uvicorn main:socket_app --reload --port 8000`
- [ ] Frontend inicia: `cd FRONTEND && npm run dev`

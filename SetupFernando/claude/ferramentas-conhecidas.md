# Ferramentas — Comportamento Conhecido

> Base de conhecimento operacional. Registra ferramentas, comandos e
> bibliotecas que têm comportamento especial neste setup.
>
> Localização: `~/.claude/ferramentas-conhecidas.md`
> Governada pela regra P-7 do CLAUDE.md global.

---

## Como usar este arquivo

**Ao descobrir um quirk:** registrar aqui imediatamente, na hora da descoberta, sem esperar pedir (P-7).
**Ao executar uma ferramenta:** se ela aparece aqui, usar o comando correto registrado — não redescobrir o problema.

---

## Entradas

### Docker — build obrigatório antes de deploy
- **Status:** regra de verificação (ver Regra 8 do global)
- **Sintoma:** Dockerfiles escritos sem teste local acumulam erros que só aparecem em produção.
- **Comando correto:** `docker compose build && docker compose up -d && curl localhost:{porta}/health`
- **Motivo:** Todo Dockerfile novo ou alterado deve ser buildado e o container deve responder antes de a etapa ser considerada pronta.
- **Escopo:** global
- **Descoberto em:** 2026-05-14

### Docker — dependências de sistema para WeasyPrint
- **Status:** funciona com ajuste
- **Sintoma:** o container inicia normalmente, mas falha ao gerar qualquer PDF.
- **Comando correto:** adicionar ao Dockerfile baseado em `python:3.11-slim`:
  `RUN apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1 libgdk-pixbuf-2.0-0 libcairo2 shared-mime-info`
- **Motivo:** `python:3.11-slim` não inclui as bibliotecas de sistema que o WeasyPrint precisa em runtime.
- **Escopo:** global (todos os projetos que usam WeasyPrint)
- **Descoberto em:** 2026-05-14

### Next.js — Dockerfile precisa de todas as dependências no estágio de build
- **Status:** funciona com ajuste
- **Sintoma:** o build falha com `Cannot find module 'tailwindcss'` (ou outra devDependency).
- **Comando correto:** usar `npm ci` (sem `--only=production`) no estágio de build do Dockerfile.
- **Motivo:** `--only=production` pula as devDependencies (tailwindcss, typescript, etc.) que o `next build` precisa para rodar.
- **Escopo:** global (todos os projetos que usam Next.js + Docker)
- **Descoberto em:** 2026-05-14

### Ferramentas de segurança — instalação no servidor Linux (OCI/Ubuntu)
- **Status:** instalar uma vez no servidor de produção
- **Comandos de instalação:**
  ```bash
  # trivy (scanner de containers)
  curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sudo sh -s -- -b /usr/local/bin
  # pip-audit e semgrep
  pip3 install pip-audit semgrep --break-system-packages
  # adicionar ao PATH (sessões SSH não-interativas)
  echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.profile
  # nmap
  sudo apt install -y nmap
  ```
- **Quirk semgrep:** requer `PATH=$HOME/.local/bin:$PATH` no início do comando SSH — sessões não-interativas não carregam `.bashrc`.
- **Escopo:** servidor Linux de produção

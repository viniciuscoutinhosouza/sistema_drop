# Setup da 2ª máquina do Coletor ML (failover)

Runbook para configurar a **segunda máquina** do coletor (Camoufox) que serve a
Análise de Concorrência do Sistema Drop. A Máquina 1 já está no ar com o túnel fixo
`https://coletor1.madeingroup.api.br`. Esta máquina será a `coletor2`.

> **Como usar:** abra o Claude Code nesta máquina, na pasta do projeto, e cole:
> *"Siga o runbook em tools/collector/SETUP_MAQUINA2.md e prepare esta máquina como
> a 2ª do coletor (coletor-ml-2 / coletor2.madeingroup.api.br). Me peça o token quando
> precisar."* — ou execute os passos manualmente no PowerShell.

Parâmetros desta máquina (diferentes da Máquina 1):
- Nome do túnel: **`coletor-ml-2`**
- Hostname: **`coletor2.madeingroup.api.br`**
- Porta local da API: **8777** (igual)
- Token: **o MESMO** `COLLECTOR_API_TOKEN` da Máquina 1 (está em `tools/collector/.env` dela)

Pré-requisitos: Windows, **Python 3.11**, Git. Caminho do projeto sugerido: `C:\Sistema_Drop`.

---

## 1. Clonar o projeto
```powershell
git clone https://github.com/viniciuscoutinhosouza/sistema_drop.git C:\Sistema_Drop
cd C:\Sistema_Drop
```

## 2. Criar a venv dedicada (Python 3.11) e instalar deps
```powershell
py -3.11 -m venv C:\Sistema_Drop\.venv-camoufox
C:\Sistema_Drop\.venv-camoufox\Scripts\python.exe -m pip install --upgrade pip
C:\Sistema_Drop\.venv-camoufox\Scripts\python.exe -m pip install -r requirements-camoufox.txt
C:\Sistema_Drop\.venv-camoufox\Scripts\python.exe -m pip install -r tools\collector\requirements.txt
C:\Sistema_Drop\.venv-camoufox\Scripts\python.exe -m camoufox fetch
```

## 3. Configurar o `.env` do coletor (NÃO commitar)
Crie `C:\Sistema_Drop\tools\collector\.env` a partir do `.env.example`:
```powershell
Copy-Item tools\collector\.env.example tools\collector\.env
```
Edite e preencha **`COLLECTOR_API_TOKEN`** com o MESMO token da Máquina 1
(`tools/collector/.env` dela). Os demais valores podem ficar no default
(`COLLECTOR_HOST=127.0.0.1`, `COLLECTOR_PORT=8777`, `COLLECTOR_DEFAULT_LIMIT=120`).

## 4. Baixar o cloudflared
```powershell
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile "C:\Sistema_Drop\tools\collector\cloudflared.exe"
```

## 5. Criar o túnel desta máquina
```powershell
$cf = "C:\Sistema_Drop\tools\collector\cloudflared.exe"
& $cf tunnel login          # abre o navegador → autorize o domínio madeingroup.api.br
& $cf tunnel create coletor-ml-2
& $cf tunnel route dns coletor-ml-2 coletor2.madeingroup.api.br
```
O `create` imprime um **Tunnel ID** e salva um `<UUID>.json` em `%USERPROFILE%\.cloudflared\`.
Anote o UUID.

## 6. Criar o `config.yml`
Crie `%USERPROFILE%\.cloudflared\config.yml` (troque `<UUID>` pelo do passo 5):
```yaml
tunnel: coletor-ml-2
credentials-file: C:\Users\SEU_USUARIO\.cloudflared\<UUID>.json

ingress:
  - hostname: coletor2.madeingroup.api.br
    service: http://localhost:8777
  - service: http_status:404
```

## 7. Launcher (API + túnel) desta máquina
Crie `C:\Sistema_Drop\tools\collector\iniciar_coletor_completo_m2.bat`:
```bat
@echo off
cd /d "%~dp0..\.."
start "Coletor ML API" /min ".venv-camoufox\Scripts\python.exe" "tools\collector\collector_api.py"
timeout /t 4 /nobreak >nul
"tools\collector\cloudflared.exe" tunnel run coletor-ml-2
pause
```
(igual ao da Máquina 1, mas com `coletor-ml-2`.)

Opcional — auto-start no logon: crie um atalho desse `.bat` em `shell:startup`
(Win+R → `shell:startup` → colar atalho), janela minimizada.

## 8. Testar
```powershell
# sobe API + túnel:
C:\Sistema_Drop\tools\collector\iniciar_coletor_completo_m2.bat
# noutro terminal, valide a URL fixa desta máquina:
Invoke-RestMethod https://coletor2.madeingroup.api.br/health
```
Deve responder `{"status":"ok","service":"ml-collector",...}`.

## 9. Ligar o failover no servidor
Quando o passo 8 responder OK, **avise o responsável pelo backend** (ou peça ao Claude
da Máquina 1) para atualizar o `.env` do servidor Oracle para:
```
COLLECTOR_API_URL=https://coletor1.madeingroup.api.br,https://coletor2.madeingroup.api.br
```
e reiniciar o backend (`pm2 restart sistema-drop-backend --update-env`). O backend passa
a tentar a Máquina 1 e, se cair/der captcha, usa a Máquina 2 (IP residencial diferente).

---

### Checklist
- [ ] Projeto clonado + venv-camoufox (py3.11) + deps + `camoufox fetch`
- [ ] `tools/collector/.env` com o MESMO token da Máquina 1
- [ ] `cloudflared.exe` baixado
- [ ] Túnel `coletor-ml-2` criado + DNS `coletor2.madeingroup.api.br`
- [ ] `config.yml` apontando para `localhost:8777`
- [ ] Launcher m2 + (opcional) atalho no Inicializar
- [ ] `https://coletor2.madeingroup.api.br/health` responde OK
- [ ] `.env` do servidor atualizado com as 2 URLs + backend reiniciado

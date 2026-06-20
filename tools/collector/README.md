# Coletor ML local (Camoufox)

API local que recupera a **busca livre por palavra-chave** do Mercado Livre — que a
API oficial bloqueou (`/sites/MLB/search` → 403). Roda na **sua máquina** (IP
residencial), nunca no servidor Oracle. O backend chama esta API por HTTP.

```
[Backend / Oracle]  --HTTP /collect-->  [API local (esta) / Windows]
                                              └─ Camoufox anônimo → mercadolivre.com.br
                    <--- itens JSON ----  (ID MLB, título, preço, vendedor)
```

⚠️ **Risco de ToS:** raspar páginas do ML viola os termos. Mitigações adotadas:
navegação **anônima** (sem login → sem conta atrelada), **volume baixo**, **IP
residencial**. Risco aceito pelo dono em 2026-06-20.

## Instalação (uma vez)

Use a venv dedicada já criada (`.venv-camoufox`, Python 3.11):

```powershell
# da raiz do repo
.\.venv-camoufox\Scripts\python.exe -m pip install -r tools\collector\requirements.txt
# (camoufox/playwright já vieram de requirements-camoufox.txt + 'python -m camoufox fetch')

copy tools\collector\.env.example tools\collector\.env
# edite tools\collector\.env e defina COLLECTOR_API_TOKEN (token longo e aleatório)
```

## Rodar a API local

```powershell
.\.venv-camoufox\Scripts\python.exe tools\collector\collector_api.py
# health: http://localhost:8777/health
```

## Teste rápido do scraping (CLI, sem API)

```powershell
.\.venv-camoufox\Scripts\python.exe tools\collector\ml_search.py "fone bluetooth jbl"
# saída em output/ml_search/*.json  (rode headful primeiro; --headless só após validar)
```

## Tornar a API alcançável pelo servidor Oracle

A máquina local fica atrás de NAT/CGNAT. Exponha a porta `8777` por um **túnel**
(recomendado — não depende de IP fixo nem abre porta no roteador):

```powershell
# Cloudflare Tunnel (gratuito)
cloudflared tunnel --url http://localhost:8777
# → gera uma URL pública https://xxxx.trycloudflare.com
```

Coloque essa URL pública em `COLLECTOR_API_URL` no `.env` do **backend** (servidor
Oracle), e o mesmo `COLLECTOR_API_TOKEN` em `COLLECTOR_API_TOKEN`. O túnel carrega só
o tráfego de controle; o Camoufox continua saindo pelo **seu IP residencial**.

### Duas máquinas (failover)

Para alta disponibilidade, rode o coletor + túnel em **duas máquinas** e liste as duas
URLs separadas por vírgula no `.env` do backend. O backend tenta a 1ª; se cair, der erro
ou captcha, usa a 2ª (IP residencial diferente):

```env
COLLECTOR_ENABLED=true
COLLECTOR_API_URL=https://maquina1.trycloudflare.com,https://maquina2.trycloudflare.com
# 1 token compartilhado (mesmo COLLECTOR_API_TOKEN nas duas máquinas):
COLLECTOR_API_TOKEN=SEU_TOKEN
# ...ou um token por máquina, alinhado à ordem das URLs:
# COLLECTOR_API_TOKEN=tokenMaquina1,tokenMaquina2
```

Pode deixar a 2ª já pré-configurada e ligá-la depois — entradas vazias são ignoradas
(`COLLECTOR_API_URL=https://maquina1...,` funciona com só a 1ª no ar).

## Endpoints

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | — | status |
| POST | `/collect` | `Bearer <COLLECTOR_API_TOKEN>` | `{query, limit?, headless?}` → `{query, total, items[], captcha_detected, error}` |

Cada item: `{item_id (MLB…), title, price, seller, sold_text, href, source:"search_scraped"}`.

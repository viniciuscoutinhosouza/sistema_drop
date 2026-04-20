# MIG ECOMMERCE – Guia de Instalação em Novo Servidor

## Visão Geral do Sistema

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI 0.115, Python **3.11**, SQLAlchemy 2.0, oracledb 2.3 |
| Banco de dados | Oracle Cloud ATP (Autonomous Transaction Processing) |
| Frontend | Vue 3.4, Vite 4.5, AdminLTE 3.2, Pinia, Axios, Socket.io-client 4.8 |
| Jobs | APScheduler 3.10 |
| Autenticação | JWT (python-jose) + bcrypt 4.0.1 + passlib 1.7.4 |

---

## Pré-requisitos

### 1. Python 3.11 (OBRIGATÓRIO — não use 3.12+)

> **Atenção:** `oracledb` e `pydantic-core` não têm wheels binários para Python 3.12+. Use exatamente **Python 3.11**.

- Download: https://www.python.org/downloads/release/python-3119/
- Windows x64: `python-3.11.9-amd64.exe`
- Marque **"Add to PATH"** durante a instalação.

### 2. Node.js 18+ (para o frontend)

- Download: https://nodejs.org/en/download
- Versão recomendada: **LTS 20.x**

### 3. Oracle Cloud Wallet

- Faça login em https://cloud.oracle.com → Autonomous Database → MIGECOMMERCE
- Clique em **Database Connection** → Download Wallet
- Extraia o ZIP para `C:\sistema_drop\Wallet_MIGECOMMERCE\` (ou outro caminho, ajuste o `.env`)

---

## Passo a Passo

### Etapa 1 – Clonar o repositório

```bat
git clone https://github.com/viniciuscoutinhosouza/sistema_drop.git C:\Sistema_Drop
cd C:\Sistema_Drop
```

---

### Etapa 2 – Configurar o arquivo `.env` do backend

Crie o arquivo `C:\Sistema_Drop\BACKEND\.env` com o conteúdo abaixo, ajustando os valores:

```env
# Oracle ATP
ORACLE_USER=admin
ORACLE_PASSWORD=SuaSenhaOracleAqui
ORACLE_DSN=migecommerce_tp
ORACLE_WALLET_DIR=C:/Sistema_Drop/Wallet_MIGECOMMERCE
ORACLE_WALLET_PASSWORD=SuaSenhaWalletAqui

# JWT
JWT_SECRET=UmaChaveSecretaForteAqui
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
JWT_REFRESH_EXPIRE_DAYS=30

# Frontend CORS
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173

# Mercado Livre
ML_APP_ID=6712718703908494
ML_CLIENT_SECRET=SuaChaveMLAqui
ML_REDIRECT_URI=http://localhost:8000/api/v1/integrations/ml/callback

# Shopee
SHOPEE_PARTNER_ID=
SHOPEE_PARTNER_KEY=
SHOPEE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/shopee/callback

# Taxa por pedido pago (R$)
PLATFORM_FEE=2.00
```

> **Sobre o `ORACLE_DSN`:** o valor `migecommerce_tp` é o alias do serviço definido em `Wallet_MIGECOMMERCE/tnsnames.ora`. Se o nome do banco mudar, verifique esse arquivo.

---

### Etapa 3 – Instalar dependências do backend

Abra o CMD e execute:

```bat
cd C:\Sistema_Drop\BACKEND
python -m pip install -r requirements.txt
```

> **Atenção crítica:** o `requirements.txt` já pina `bcrypt==4.0.1`. Se reinstalar sem o arquivo, instale manualmente:
> ```bat
> pip install bcrypt==4.0.1
> ```
> `passlib 1.7.4` é incompatível com `bcrypt 5.x` — causa erro `ValueError: password cannot be longer than 72 bytes`.

---

### Etapa 4 – Executar os scripts SQL no Oracle ATP

Execute os scripts **na ordem** usando SQL*Plus, SQLcl, ou Oracle SQL Developer:

```
Scripts SQL/01_users.sql
Scripts SQL/02_financial.sql
Scripts SQL/03_products.sql
Scripts SQL/04_kits.sql
Scripts SQL/05_dropshipper_products.sql
Scripts SQL/06_orders.sql
Scripts SQL/07_integrations.sql   ← contém ALTER TABLE da FK orders→integrations
Scripts SQL/08_returns.sql
Scripts SQL/09_notifications.sql
Scripts SQL/10_webhooks.sql
```

> A FK `orders.integration_id → marketplace_integrations.id` foi propositalmente removida do script 06 e adicionada como `ALTER TABLE` no final do script 07, pois a tabela de destino só existe depois.

---

### Etapa 5 – Criar o usuário admin inicial

Após rodar os scripts SQL, crie o usuário admin executando este script Python **uma única vez**:

```bat
cd C:\Sistema_Drop\BACKEND
python create_admin.py
```

Crie o arquivo `create_admin.py` com o conteúdo abaixo (apague após usar):

```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from database import _SyncSession
from models.user import User
from services.auth_service import hash_password
from sqlalchemy import select

session = _SyncSession()
try:
    exists = session.execute(
        select(User).where(User.email == "admin@migcommerce.com.br")
    ).scalar_one_or_none()

    if exists:
        print("Admin já existe. Atualizando senha...")
        exists.password_hash = hash_password("admin@123")
    else:
        admin = User(
            email="admin@migcommerce.com.br",
            password_hash=hash_password("admin@123"),
            full_name="Administrador",
            whatsapp="",
            cpf_cnpj="00000000000",
            role="admin",
            is_active=True,
        )
        session.add(admin)
        print("Admin criado com sucesso.")

    session.commit()
    print("Senha: admin@123")
finally:
    session.close()
```

---

### Etapa 6 – Iniciar o sistema

Dê duplo clique em `C:\Sistema_Drop\start.bat` — ele abre duas janelas CMD:

| Janela | Serviço | URL |
|--------|---------|-----|
| MIG BACKEND | FastAPI + Uvicorn | http://localhost:8000 |
| MIG FRONTEND | Vite dev server | http://localhost:5173 |

Ou inicie separadamente:
- `start_backend.bat` — apenas o backend
- `start_frontend.bat` — apenas o frontend

> Na primeira execução, `start_frontend.bat` roda `npm install` automaticamente.

---

## Arquivos de Inicialização

### `BACKEND/run.py`

```python
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # reload=True perde a política do event loop no Windows
    )
```

> A política `WindowsSelectorEventLoopPolicy` é **obrigatória** no Windows. O loop `ProactorEventLoop` (padrão do Windows) é incompatível com o driver `oracledb` em modo síncrono via thread pool — causa desconexão silenciosa.

---

## Problemas Conhecidos e Soluções

### 1. `DPI-1047: Cannot locate Oracle Client`

**Causa:** oracledb sendo inicializado em modo thick (precisa do Instant Client).  
**Solução:** Não chamar `oracledb.init_oracle_client()`. O sistema usa thin mode — não requer Instant Client instalado.

---

### 2. `WinError 10054` / `DPY-4011: connection closed` ao conectar no Oracle ATP

**Causa:** SQLAlchemy async dialect tenta usar `oracledb.connect_async()` com SSL; no Windows com ProactorEventLoop isso causa desconexão imediata.  
**Solução:** O `database.py` usa engine **síncrono** com `creator=_make_oracle_connection` (bypassa o parser de URL do SQLAlchemy) e envolve todas as chamadas em `asyncio.to_thread()` via a classe `AsyncSyncSession`.

---

### 3. `ValueError: password cannot be longer than 72 bytes`

**Causa:** `passlib 1.7.4` é incompatível com `bcrypt >= 5.0`.  
**Solução:** Pinar `bcrypt==4.0.1` no `requirements.txt` (já está incluso).

---

### 4. `RuntimeError: Form data requires "python-multipart"`

**Causa:** O endpoint `POST /token` (Swagger Authorize) usa `OAuth2PasswordRequestForm` que exige `python-multipart`.  
**Solução:** Já incluso no `requirements.txt` como `python-multipart==0.0.26`.

---

### 5. Login no Swagger retorna `400 Bad Request` mesmo com credenciais corretas

**Causa:** O hash da senha no banco foi gerado com bcrypt 5.x (incompatível). Após trocar para bcrypt 4.0.1, os hashes antigos tornam-se inválidos.  
**Solução:** Execute o script `create_admin.py` da Etapa 5 — ele regrava o hash com a versão correta.

---

### 6. Backend não sobe — porta 8000 ocupada

**Causa:** Instância anterior ainda rodando (especialmente com `reload=False`).  
**Solução:** Feche a janela CMD do backend anterior antes de reiniciar.

---

### 7. Frontend não acha o backend (`Network Error` no Axios)

**Causa:** Vite proxy só funciona em dev. Em produção é necessário configurar Nginx/Caddy como reverse proxy.  
**Solução (dev):** O `vite.config.js` já configura proxy `/api` → `http://localhost:8000`. Certifique-se que o backend está rodando antes do frontend.

---

## Estrutura de Diretórios

```
C:\Sistema_Drop\
├── BACKEND\
│   ├── .env                  ← secrets (não comitar)
│   ├── main.py               ← FastAPI app + routers + Socket.io
│   ├── run.py                ← entry point (WindowsSelectorEventLoopPolicy)
│   ├── database.py           ← engine Oracle (sync + AsyncSyncSession wrapper)
│   ├── config.py             ← BaseSettings (lê .env)
│   ├── dependencies.py       ← get_current_user, require_role
│   ├── socket_manager.py     ← python-socketio server
│   ├── requirements.txt
│   ├── models\               ← ORM SQLAlchemy (user, order, product, kit, ...)
│   ├── schemas\              ← Pydantic v2 schemas
│   ├── routers\              ← endpoints por domínio (/auth, /orders, ...)
│   ├── services\             ← lógica de negócio (financial, ml, shopee, ...)
│   └── tasks\                ← APScheduler jobs (sync_orders, sync_stock, ...)
├── FRONTEND\
│   ├── vite.config.js        ← proxy /api → :8000
│   ├── package.json
│   └── src\
│       ├── composables\useApi.js  ← Axios + interceptor JWT refresh automático
│       ├── stores\           ← Pinia (auth, financial, notifications, ui)
│       ├── router\index.js   ← navigation guard + rotas protegidas
│       ├── layouts\          ← AuthLayout, DashboardLayout (AdminLTE)
│       ├── views\            ← páginas por módulo
│       └── components\       ← DataTable, ImageUploader, OrderStatusStepper, ...
├── Scripts SQL\              ← 01_users.sql … 10_webhooks.sql (executar em ordem)
├── Wallet_MIGECOMMERCE\      ← wallet Oracle Cloud (não comitar em repo público)
├── start.bat                 ← inicia backend + frontend
├── start_backend.bat
└── start_frontend.bat
```

---

## Variáveis de Ambiente para Produção

Em produção (Linux/servidor), substitua os `.bat` por serviços systemd ou Docker, e ajuste o `.env`:

```env
# Ajustar URLs para o domínio real
FRONTEND_URL=https://app.migcommerce.com.br
CORS_ORIGINS=https://app.migcommerce.com.br

ML_REDIRECT_URI=https://api.migcommerce.com.br/api/v1/integrations/ml/callback
SHOPEE_REDIRECT_URI=https://api.migcommerce.com.br/api/v1/integrations/shopee/callback

# JWT_SECRET deve ser uma string aleatória longa em produção
JWT_SECRET=gere-com-openssl-rand-hex-32
```

Em Linux, o `WindowsSelectorEventLoopPolicy` não é necessário — remova o bloco `if sys.platform == "win32"` do `run.py` e `main.py`.

---

## Usuário Admin Padrão

| Campo | Valor |
|-------|-------|
| E-mail | `admin@migcommerce.com.br` |
| Senha | `admin@123` |
| Role | `admin` |

> **Troque a senha após o primeiro login em produção.**

---

## Checklist de Instalação

- [ ] Python 3.11 instalado
- [ ] Node.js 18+ instalado
- [ ] Wallet Oracle extraída em `C:\Sistema_Drop\Wallet_MIGECOMMERCE\`
- [ ] `.env` criado e preenchido em `BACKEND\.env`
- [ ] `pip install -r requirements.txt` executado
- [ ] Scripts SQL 01–10 executados no Oracle ATP (em ordem)
- [ ] Script `create_admin.py` executado (cria/corrige hash do admin)
- [ ] `start.bat` executado — backend em :8000, frontend em :5173
- [ ] Login testado em http://localhost:8000/docs com `admin@migcommerce.com.br` / `admin@123`

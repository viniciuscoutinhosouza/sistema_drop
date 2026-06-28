# CLAUDE.md — MIG ECOMMERCE / Sistema Drop

## Visão Geral

Sistema de gestão de contas de marketplace para dropshippers (ACs) e galpões (UGOs).
Integra Mercado Livre e Shopee via OAuth multi-conta; gerencia pedidos, estoque, NF-e e anúncios.

---

## Stack e Versões

### Backend
| Pacote | Versão |
|---|---|
| Python | 3.11 |
| FastAPI | 0.115.6 |
| SQLAlchemy | 2.0.36 |
| oracledb (thin mode) | 2.3.0 |
| Pydantic | 2.10.4 |
| bcrypt | **4.0.1** (fixo — versões maiores quebram o passlib) |
| python-jose | latest |
| httpx | 0.28.1 |
| python-socketio | 5.11.4 |
| APScheduler | 3.10.4 |

### Frontend
| Pacote | Versão |
|---|---|
| Vue | 3.4 |
| Pinia | 2.1.7 |
| Vue Router | 4.5.1 |
| Axios | 1.3.4 |
| Socket.io-client | 4.8.1 |
| AdminLTE | 3 |
| Bootstrap | 5 |
| Vite | 4.5 |

Sem TypeScript, sem ESLint/Prettier.

---

## Estrutura de Pastas

```
Sistema_Drop/
├── BACKEND/
│   ├── main.py               # App FastAPI + montagem Socket.io
│   ├── database.py           # Engine Oracle + AsyncSyncSession wrapper
│   ├── config.py             # Pydantic Settings (lê .env)
│   ├── dependencies.py       # get_current_user, require_role(*roles)
│   ├── socket_manager.py     # Instância socketio.AsyncServer
│   ├── models/               # ORM SQLAlchemy
│   │   ├── user.py           # User, AccountAdministrator, CMIGAdministrator
│   │   ├── cmig.py           # CMIG, CMIGProduct, CMIGProductVariant, CMIGProductImage
│   │   ├── product.py        # CatalogProduct, DropshipperProduct, ProductListing, Kits…
│   │   ├── order.py          # Order, OrderItem, ManualOrder…
│   │   ├── integration.py    # MarketplaceAccount
│   │   └── warehouse.py      # Warehouse
│   ├── routers/              # 22 routers FastAPI
│   ├── services/             # Clientes externos (ml_service, shopee_service, bling_service…)
│   ├── tasks/scheduler.py    # Jobs APScheduler
│   └── static/uploads/       # Fotos enviadas via upload
├── FRONTEND/
│   ├── src/
│   │   ├── stores/           # Pinia: auth, ui, notifications, financial, cmig, go
│   │   ├── composables/      # useApi (Axios), useToast, useSocket, usePagination
│   │   ├── router/index.js   # 30+ rotas com meta.requiresAuth
│   │   ├── views/            # 16 categorias de views
│   │   └── components/       # Componentes reutilizáveis
│   └── vite.config.js        # Proxy /api → :8000, /ws → :8000 (ws:true)
└── Scripts SQL/              # Migrations Oracle numeradas (rodar em ordem)
```

---

## Como Rodar

```bash
# Backend
cd BACKEND
pip install -r requirements.txt    # Python 3.11
cp .env.example .env               # preencher variáveis Oracle + JWT + ML + Shopee
uvicorn main:socket_app --reload --port 8000

# Frontend (outro terminal)
cd FRONTEND
npm install
npm run dev                        # http://localhost:5173 (proxy → :8000)
```

---

## Servidor de Produção: LINUX
O acesso ao servidor em produção segue o comando abaixo
ssh -i c:/sistema_drop/ssh-key-2026-05-08.key ubuntu@163.176.165.201

✅ Instância Oracle Cloud Criada
Dados da instância:
Nome:                   meu-servidor-web
Status:                 Running (Ativo)
Sistema Operacional:    Ubuntu 22.04 LTS
Shape:                  VM.Standard.E2.1.Micro (Always Free)
IP Público:             163.176.165.201
IP Privado:             10.0.0.130
Região:                 Brazil East (São Paulo)
Usuário SSH:            ubuntu

Portas abertas (Security List):
Porta 22 (SSH) ✅
Porta 80 (HTTP) ✅
Porta 443 (HTTPS) ✅


## Convenções de Código

### Backend
- Routers retornam `dict` diretamente (sem schema Pydantic no retorno).
- Use `body: dict` para receber JSON nos endpoints — sem Pydantic request models.
- `require_role("ugo", "admin")` como dependência para acesso restrito.
- Sempre usar `await db.execute(select(...))` — mas `db.add()` e `db.delete()` são **síncronos** (sem await).
- Após `db.add()` antes do ID: chamar `await db.flush()` para obter o PK sem commitar.
- `model_dump(exclude_none=True)` para atualizações parciais com Pydantic v2.
- Colunas de variante de tamanho: `size_label` (não `size`) em `CatalogProductVariant` e `CMIGProductVariant`.

### Frontend
- Vue 3 Composition API + `<script setup>`.
- Composable `useApi` (Axios com interceptors JWT) — não usar `axios` diretamente.
- `useToast()` para feedback: `.success()`, `.error()`, `.warning()`, `.info()`.
- AdminLTE 3 + Bootstrap 5 — classes `card`, `card-header`, `card-body`, `btn btn-sm`.
- Ícones via Font Awesome 5 (`fas fa-*`).
- Rotas protegidas com `meta: { requiresAuth: true }`.

---

## Arquitetura e Decisões Importantes

### Oracle sem driver async
Não existe driver `oracledb` async. A solução adotada:
- `_sync_engine` = engine SQLAlchemy síncrono
- `AsyncSyncSession` = wrapper que executa operações via `asyncio.to_thread()`
- Nos routers: `db: AsyncSession = Depends(get_db)` — mas o tipo real é `AsyncSyncSession`
- **`db.add()` e `db.delete()` são síncronos** — nunca use `await` neles
- `oracledb.defaults.fetch_lobs = False` ativado globalmente para auto-converter CLOB em string

### JWT + Autenticação
- Token armazenado em `localStorage` (frontend)
- Axios injeta `Authorization: Bearer <token>` em todo request
- Em 401, interceptor tenta refresh automático e refaz o request original
- Se refresh falhar → redireciona para `/login`

### Papéis (roles)
| Role | Sigla | Acesso |
|---|---|---|
| Account Manager | `ac` | Gerencia CMIG, cria produtos CMIG, vê catálogo PG |
| Warehouse Operator | `ugo` | Gerencia PG, importa/sincroniza para PG, edita variantes |
| Admin | `admin` | Acesso total (inclui permissões UGO) |
| Gestor Operacional | `go` | Aprovações e visão gerencial |

### Fluxo CMIG → PG
1. AC cria `CMIGProduct` com fotos, dimensões e variantes
2. UGO importa para PG (`POST /cmigs/{id}/products/{pid}/import-to-pg`) → cria `CatalogProduct`
3. Vinculação salva `CMIGProduct.pg_product_id`
4. Sync posterior (`POST .../sync-pg`) atualiza marca, modelo, EAN, NCM, CEST, dimensões no PG

### Anúncios ML/Shopee
- `ProductListing` liga `DropshipperProduct` ↔ `MarketplaceAccount`
- `attributes_json` armazena specs no formato ML: `[{"id": "BRAND", "name": "Marca", "value": "Nike"}]`
- Jaccard similarity (threshold 0.6) para auto-match anúncio ↔ CMIGProduct
- Endpoint `/anuncios/{listing_id}/create-cmig-product` converte anúncio em CMIGProduct

### Tempo real
- Socket.io em `/ws/socket.io` (ASGI sub-app)
- `socket_manager.py` expõe `sio.emit(event, data, room=user_id)`
- Frontend usa `useSocket` composable

### Background Jobs (APScheduler)
| Job | Intervalo |
|---|---|
| sync_orders | 15 min |
| refresh_tokens | 1 hora |
| check_subscriptions | diário |
| sync_stock | 30 min |

---

## Integrações Externas e Variáveis de Ambiente

```env
# Oracle ATP
ORACLE_USER=
ORACLE_PASSWORD=
ORACLE_DSN=                    # ex: meudb_high
ORACLE_WALLET_DIR=             # opcional — caminho da pasta do wallet
ORACLE_WALLET_PASSWORD=

# JWT
JWT_SECRET_KEY=                # string longa aleatória
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Mercado Livre
ML_APP_ID=
ML_CLIENT_SECRET=
ML_REDIRECT_URI=

# Shopee
SHOPEE_PARTNER_ID=
SHOPEE_PARTNER_KEY=
SHOPEE_REDIRECT_URI=

# Bling (opcional)
BLING_CLIENT_ID=
BLING_CLIENT_SECRET=
```

---

## Prefixos de API

| Prefixo | Router |
|---|---|
| `/api/v1/auth` | Login, refresh token |
| `/api/v1/users` | Gestão de usuários |
| `/api/v1/dashboard` | Dados resumidos |
| `/api/v1/financial` | Financeiro |
| `/api/v1/catalog` | Catálogo de produtos |
| `/api/v1/pg` | Produto Geral (supplier_products.py) |
| `/api/v1/products` | Produtos do dropshipper |
| `/api/v1/kits` | Kits de produtos |
| `/api/v1/orders` | Pedidos |
| `/api/v1/manual-orders` | Pedidos manuais |
| `/api/v1/accounts` | Contas de marketplace |
| `/api/v1/products/{id}/listings` | Anúncios por produto |
| `/api/v1/returns` | Devoluções |
| `/api/v1/notifications` | Notificações |
| `/api/v1/webhooks` | Webhooks ML/Shopee |
| `/api/v1/warehouse` | Galpões |
| `/api/v1/goes` | Gestores Operacionais |
| `/api/v1/cmigs` | CMIGs e produtos CMIG |
| `/api/v1/anuncios` | Anúncios importados do ML |
| `/api/v1/simulator` | Simulador de preço |
| `/api/v1/competitor-analysis` | Análise de Concorrência (ML + IA) |
| `/api/v1/separation` | Separação (Carrinho Gaiola, pedidos não-FULL) |
| `/api/v1/marketplace-settings` | Config por marketplace (Super Admin) |

---

## Governança e Processo

### Regra de Proporcionalidade

Toda mudança se enquadra em um de dois níveis:

| Nível | Quando aplicar | O que fazer |
|-------|---------------|-------------|
| **Lightweight** | Mudança isolada, baixo risco, 1-2 arquivos | Implementar diretamente, atualizar LOG.md |
| **Full** | Estrutural, multi-arquivo, novo padrão, dado sensível | Specialist agent + auditoria + ADR se necessário + session-closer |

### Regras Invioláveis

1. **Conventional Commits obrigatório** — todo commit segue `<type>(<scope>): <descrição>`. Tipos: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `style`, `perf`. Exemplo: `feat(fiscal): add finalize-no-sefaz endpoint`.
2. **Nunca commitar `.env` ou segredos** — apenas `.env.example` com valores em branco.
3. **Experimentos e arquivos temporários** vão em `sandbox/` — nunca na raiz ou em módulos de produção.
4. **Código em inglês, conversação em português.**

### Avaliação Prévia Obrigatória (antes de implementar)

**Para TODA solicitação do usuário**, antes de escrever/refatorar qualquer código, invocar o agente `consistency-auditor` para:
1. Avaliar a **solicitação do usuário** (o que está sendo pedido, ambiguidades, impacto).
2. Avaliar o **plano de execução da Claude** (a abordagem proposta antes de codar).
3. Apontar inconsistências, lacunas, fluxos que ficariam fora de paridade e oportunidades de reutilização.

A Claude apresenta o plano, roda o `consistency-auditor` sobre ele, e só então implementa — incorporando os apontamentos. Exceção: tarefas triviais e somente-leitura (perguntas, investigações sem mudança de código) não exigem a avaliação prévia.

### Procedimento de Auditoria (Nível Full)

Antes de fechar qualquer feature estrutural, invocar em **paralelo**:
- `quality-guardian` — segurança, bugs, LGPD, tratamento de erros
- `consistency-auditor` — CRUDs incompletos, padrões inconsistentes
- `adr-consistency-checker` — respeito às decisões arquiteturais

Só entrega se nenhum tiver CRITICAL/HIGH/BLOQUEADO.

### Regra de Verificação — "entregue" exige prova de funcionamento

Uma mudança de nível **Full** não pode ser declarada concluída com base em "feito conforme o plano". Concluído significa **verificado funcionando**:

1. O código foi executado, não apenas escrito.
2. Se há build (Docker, frontend), rodou sem erro.
3. Se há serviço/rota, sobe e responde (health check, rota carrega).
4. Logs sem erro crítico de import ou dependência.
5. O caminho principal da feature foi percorrido ao menos uma vez.

Comandos de verificação típicos:
- Backend: `cd BACKEND && pytest tests/ -m "not integration"`
- Frontend: `cd FRONTEND && npm run build`
- Smoke: `curl http://localhost:8000/docs` (ou rota de saúde quando existir)

Ao declarar conclusão, **explicitar quais checks foram executados**. Falhou? Corrige antes de declarar.

### Agentes Disponíveis

| Agente | Quando invocar |
|--------|---------------|
| `quality-guardian` | Antes de fechar qualquer feature |
| `consistency-auditor` | Antes de fechar qualquer feature |
| `adr-consistency-checker` | Features estruturais / novos padrões |
| `debug-specialist` | Bugs, erros, comportamento inesperado |
| `deploy-operator` | Qualquer deploy em produção |
| `migration-specialist` | Migrações de dados/legados, alterações de schema multi-tabela em `Scripts SQL/` |
| `mercado-livre-especialista` | Decisões sobre a **API do ML** (como fazer X, por que o ML recusou). Regra: nunca afirmar "não dá" sem verificar na doc oficial/testar. Use antes de concluir algo sobre o ML. |
| `session-closer` | Ao final de sessão de trabalho significativa |

### ADRs (Architecture Decision Records)

Decisões arquiteturais registradas em `docs/decisions/`. Consultar antes de propor mudanças estruturais:
- [ADR-0001](docs/decisions/ADR-0001-oracle-asyncsyncsession.md) — Oracle + AsyncSyncSession
- [ADR-0002](docs/decisions/ADR-0002-vue3-adminlte-bootstrap.md) — Vue 3 + AdminLTE sem TypeScript
- [ADR-0003](docs/decisions/ADR-0003-jwt-localstorage.md) — JWT em localStorage
- [ADR-0004](DOCs/decisions/ADR-0004-stock-ssot-fases.md) — Estoque SSOT + reserva FULL + snapshots
- [ADR-0005](DOCs/decisions/ADR-0005-separacao-picking-cart.md) — Separação: Carrinho Gaiola + estados separated/shipped
- [ADR-0006](DOCs/decisions/ADR-0006-metricas-marketplace-live-vs-snapshot.md) — Métricas de marketplace: live passthrough vs. snapshot diário
- [ADR-0007](DOCs/decisions/ADR-0007-claims-vs-return-fisico.md) — Reclamações (claims ML) como subsistema próprio, distinto da Devolução física
- [ADR-0008](DOCs/decisions/ADR-0008-nfe-batch-mensal-e-anuncio-full-quando-local-zero.md) — Sync mensal de NF-e (batch ML) + anúncio não-FULL anuncia FULL quando LOCAL=0
- [ADR-0009](DOCs/decisions/ADR-0009-devolucao-nfe-driven.md) — Devolução NF-e-driven: NF-e fiscal-only (stock_updated=False) + contadores de inspeção como fonte canônica
- [ADR-0010](DOCs/decisions/ADR-0010-full-sempre-cmig.md) — Estoque FULL é sempre do produto CMIG (auto-criação de espelho do PG); sync ML vira conferência
- [ADR-0011](DOCs/decisions/ADR-0011-estudos-assincronos-ia-ml.md) — Estudos assíncronos IA+ML (job in-process por request + estudo persistido como memória)
- [ADR-0012](DOCs/decisions/ADR-0012-coletor-ml-local-camoufox.md) — Coletor de busca ML local (Camoufox) via HTTP, fora do servidor Oracle (3ª fonte opt-in da Análise de Concorrência)
- [ADR-0013](DOCs/decisions/ADR-0013-datahora-utc-armazenamento-conversao-borda.md) — Data/hora: UTC aware no armazenamento/transporte, conversão para America/Sao_Paulo na borda (fonte única: `utils/formatters.js` + `services/datetime_br.py`)
- [ADR-0014](DOCs/decisions/ADR-0014-estoque-anuncio-pausa-auto-e-sync-ml-metadados.md) — Estoque fixo vira teto (`min(fixo, disponível)`); pausa/reativação automática do anúncio por disponibilidade (`auto_paused`); FULL derivado na leitura (sem coluna redundante); job horário que sincroniza metadados do ML (promoções/descrição/status/FULL) **menos estoque**

Nova decisão arquitetural → criar próximo ADR em `docs/decisions/`.

### Lições Aprendidas

Ver `docs/lessons-learned.md` para armadilhas conhecidas documentadas (L-001 a L-011).

---

## Regras Específicas para Claude

1. **Nunca use `await` em `db.add()` ou `db.delete()`** — são síncronos no `AsyncSyncSession`.
2. **`size_label`**, não `size` — coluna de tamanho em variantes (CMIG e PG).
3. **bcrypt 4.0.1 fixo** — não atualizar sem testar passlib.
4. **Migrations SQL numeradas** em `Sistema_Drop/Scripts SQL/` (raiz do projeto, **não** dentro de BACKEND) — criar novos scripts seguindo o padrão `NN_descricao.sql`; usar bloco `DECLARE ... EXCEPTION WHEN e_col_exists` para ser idempotente.
5. **Oracle CLOB**: `oracledb.defaults.fetch_lobs = False` já está ativo — campos Text/CLOB chegam como string normalmente.
6. **Windows + asyncio**: `WindowsSelectorEventLoopPolicy` já configurado em `main.py` — não remover.
7. **Testes**: suite pytest em `BACKEND/tests/` — rodar `pytest tests/ -m "not integration"` para testes sem Oracle. Testes de integração requerem `.env` configurado.
8. **Sem TypeScript no frontend** — manter JS puro; não introduzir TS sem acordar com o usuário.
9. **Atualizar LOG.md** a cada alteração significativa com data/hora e resumo da mudança.

---

## Gotchas e Armadilhas Conhecidas

- `catalog_products.model` e `catalog_products.ean` foram adicionados na migration 22 (não estão no DDL original). Se o DB for recriado do zero, rodar a migration 28 (`28_catalog_products_model_ean.sql`) para garantir.
- O `AsyncSession` importável em qualquer módulo é na verdade `AsyncSyncSession` — o alias existe por compatibilidade.
- `selectinload` é obrigatório para carregar relacionamentos (`images`, `variants`) — o ORM não faz lazy load em contexto async.
- Campos ML vindos do webhook chegam como snake_case; já tratados em `ml_service.py`.
- Shopee OAuth usa HMAC-SHA256 com timestamp no header — `shopee_service.py` cuida disso.
- `fiscal_json` em anúncios armazena raw `{ncm, cest, gtin, origin}` — extrair com `json.loads()`.

---

## Estado atual

> Atualizar ao fechar cada fase de nível **Full**. Formato fixo — uma janela de contexto nova deve entender o projeto lendo só esta seção.

- **Objetivo final:** Sistema de gestão multi-conta (Mercado Livre + Shopee) para dropshippers e galpões, com fiscal NF-e integrado.
- **Fase atual:** Ciclo de estoque dos anúncios + sincronização com o ML (ADR-0014).
- **Último ponto validado:** ADR-0014 implementado (2026-06-28) — estoque fixo vira teto `min(fixo, disponível)`; pausa/reativação automática do anúncio por disponibilidade (coluna `auto_paused`, migration 114, só reativa o que o sistema pausou); FULL derivado na leitura dos anúncios (`has_full_stock`/`full_cmig_product_id`/saldos Local+FULL, sem coluna redundante); novo job horário `sync_listings_from_ml` que traz metadados do ML (título/preço/promoções via Seller Promotions v2/descrição/status/`logistic_type`-FULL/atributos/fotos/categoria/visitas) **menos estoque** (`skip_stock=True`). Auditado por quality-guardian + consistency-auditor + adr-consistency-checker (sem CRITICAL/HIGH em aberto). `py_compile` OK; `pytest -m "not integration"` 65 passed / 2 falhas **pré-existentes** em `test_orders.py` (não relacionadas).
- **Próximo passo:** Rodar a migration `114_listing_auto_paused.sql` no Oracle. Opcional: UI consumir `has_full_stock`/`auto_paused` (badge "tem FULL" e distinguir pausa automática de manual). Smoke do backend com `.env` real.
- **Bloqueios:** `BACKEND/Wallet_MIGECOMMERCE/` ausente — sem ela o backend não conecta no Oracle ATP.
- **Riscos ativos:** Nenhum.
- **Decisões pendentes:** Deploy em produção via Docker (caminho do `docker-compose.yml` novo) ou seguir com uvicorn + supervisor — definir antes do próximo deploy.

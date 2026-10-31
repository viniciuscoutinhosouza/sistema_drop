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
| `/api/v1/storage` | Endereçamento físico de estoque (ADR-0039): árvore de locais, alocação, caixas, reconciliação, etiqueta/QR, código interno — escopado por galpão |
| `/api/v1/goes` | Gestores Operacionais |
| `/api/v1/cmigs` | CMIGs e produtos CMIG |
| `/api/v1/anuncios` | Anúncios importados do ML |
| `/api/v1/simulator` | Simulador de preço |
| `/api/v1/competitor-analysis` | Análise de Concorrência (ML + IA) |
| `/api/v1/separation` | Separação (Carrinho Gaiola, pedidos não-FULL) |
| `/api/v1/marketplace-settings` | Config por marketplace (Super Admin) |
| `/api/v1/shopee` | Shopee: fiscal (upload NF-e), logística (ship/label/tracking), catálogo, custos |
| `/api/v1/integrations/eship` | eShip/Armazenaki (WMS): envio de ordens + conciliação enviadas × WMS |
| `/api/v1/traceability` | Rastreabilidade (ADR-0027): relatórios por lote/validade/serial/ANVISA (escopados por galpão) |
| `/api/v1/credits` | Crédito CMIG × Galpão (ADR-0034): extrato/saldo append-only por par |
| `/api/v1/customer-credits` | Crédito do CLIENTE × CMIG (ADR-0037): passivo com o comprador, append-only |
| `/api/v1/integrations/google-drive` | Google Drive (ADR-0038): conectar/status/cota; armazenamento de imagens (OAuth2 drive.file) |

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

#### Verificar no ambiente do dono — não no repositório local

`pytest` verde + `npm run build` OK **não é entrega**. O dono usa o sistema em **produção**
(`ecommerce.madeingroup.com.br`), e o ambiente DEV local **não consegue falar com o Mercado Livre**
(o refresh token do ML é de uso único: a produção o consome, e a cópia do banco DEV fica inválida
com `invalid_grant`). Ou seja: qualquer correção que dependa da API do ML **não pode ser validada
no DEV** — passa nos testes locais e continua quebrada para o dono.

Quando a correção nasce de um **bug que o dono viu na tela**, "entregue" exige:

1. **Deploy** — a correção tem de estar no servidor. Confirmar o commit em produção
   (`git log --oneline -1` no servidor), nunca presumir.
2. **Exercitar o caminho que ele clica** — chamar o endpoint/tela real em produção e mostrar a
   saída (ex.: a prévia do envio contendo o campo que faltava). Dado pessoal vai **mascarado**.
3. **Reportar o ambiente** de cada check: dizer "verificado" sem dizer *onde* é o erro que fez a
   mesma solicitação voltar 3×.

Regra prática: **se o dono não consegue ver a correção funcionando, ela não foi entregue.**

#### Falhar alto, nunca em silêncio

Campo obrigatório ausente, credencial vencida, integração desconectada: **nunca omitir em silêncio**.
Uma prévia que esconde o que falta transforma um erro de 1 linha em três rodadas de retrabalho. O
caminho é bloquear a ação e dizer o que falta (ver `preview_ordem` → `bloqueios[]`).

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
- [ADR-0008](DOCs/decisions/ADR-0008-nfe-batch-mensal-e-anuncio-full-quando-local-zero.md) — Sync mensal de NF-e (batch ML) + anúncio não-FULL anuncia FULL quando LOCAL=0 _(emendada por ADR-0027: produto rastreável nunca FULL e é excluído do Faturador)_
- [ADR-0009](DOCs/decisions/ADR-0009-devolucao-nfe-driven.md) — Devolução NF-e-driven: NF-e fiscal-only (stock_updated=False) + contadores de inspeção como fonte canônica
- [ADR-0010](DOCs/decisions/ADR-0010-full-sempre-cmig.md) — Estoque FULL é sempre do produto CMIG (auto-criação de espelho do PG); sync ML vira conferência
- [ADR-0011](DOCs/decisions/ADR-0011-estudos-assincronos-ia-ml.md) — Estudos assíncronos IA+ML (job in-process por request + estudo persistido como memória)
- [ADR-0012](DOCs/decisions/ADR-0012-coletor-ml-local-camoufox.md) — Coletor de busca ML local (Camoufox) via HTTP, fora do servidor Oracle (3ª fonte opt-in da Análise de Concorrência)
- [ADR-0013](DOCs/decisions/ADR-0013-datahora-utc-armazenamento-conversao-borda.md) — Data/hora: UTC aware no armazenamento/transporte, conversão para America/Sao_Paulo na borda (fonte única: `utils/formatters.js` + `services/datetime_br.py`)
- [ADR-0014](DOCs/decisions/ADR-0014-estoque-anuncio-pausa-auto-e-sync-ml-metadados.md) — Estoque fixo vira teto (`min(fixo, disponível)`); pausa/reativação automática do anúncio por disponibilidade (`auto_paused`); FULL derivado na leitura (sem coluna redundante); job horário que sincroniza metadados do ML (promoções/descrição/status/FULL) **menos estoque**
- [ADR-0015](DOCs/decisions/ADR-0015-emissao-propria-nfe-sefaz.md) — Emissão própria de NF-e direto à SEFAZ (mTLS + XMLDSig), substituindo o Focus; série manual configurável separada do marketplace; transmissão síncrona (indSinc=1) recuperável por N-6; certificado A1 local + senha cifrada (Fernet master key) e XML autorizado fora de `static/` _(emendada por ADR-0027: emissão própria passa a cobrir pedidos de marketplace rastreáveis, com `<rastro>`/`<med>`)_
- [ADR-0016](DOCs/decisions/ADR-0016-distribuicao-dfe-propria.md) — Distribuição de DFe própria (Ambiente Nacional) com controle de NSU por CMIG; manifestação própria; rate-limit cStat 656; parser endurecido + teto anti zip-bomb no docZip de terceiros
- [ADR-0017](DOCs/decisions/ADR-0017-dce-emissao-marketplace.md) — Emissão de DC-e (modelo 99) das contas CPF direto na SVRS no perfil **Marketplace** (a MIG assina com o A1 do CNPJ dela, por conta e ordem); chave inclui `tpEmit`; assinatura sem prefixo `ds:`; remetente = endereço do Galpão (IBGE por cidade+UF); destinatário `idOutros` sem CPF; DACE (PDF+QR); gate `dce_authorized` por CMIG
- [ADR-0018](DOCs/decisions/ADR-0018-cmig-identidade-fiscal-mutavel.md) — Identidade fiscal da CMIG é **mutável por substituição** (converter CPF ⇆ CNPJ zera o documento anterior, mantém "exatamente um"); alterar o tipo exige `ac`/`admin`; CPF→CNPJ exige IE+IBGE; efeitos colaterais (regime `live` de pedidos pendentes, recadastro eShip) são **avisados, não bloqueados**; documentos emitidos ficam como snapshot
- [ADR-0019](DOCs/decisions/ADR-0019-full-recomputavel-replay.md) — Estoque FULL **recomputável (replay)** a partir de 0 (como o local); débito de venda **dirigido pelo pedido** (não pela NF-e), uma única vez e só do FULL; reconciliação por inventário
- [ADR-0020](DOCs/decisions/ADR-0020-paridade-shopee-por-costuras.md) — Paridade Shopee por **costuras agnósticas** (Fases 1-7) entrando SEMPRE por ramo/rota/função nova, **NUNCA** dentro de bloco `if platform == "mercadolivre"` (regra de ouro); rotas sob `/api/v1/shopee` + `shopee_service` + `listings.py` agnóstico; fiscal = **anexar** XML da emissão própria (ADR-0015/0017), não emitir pela Shopee; logística fora da separação (picking é só ML); superfície comum tocada só aditivamente
- [ADR-0021](DOCs/decisions/ADR-0021-captura-completa-nfe-faturador-ml.md) — Captura completa das NF-e do Faturador ML (baldes por tipo de nota); **emendada** pela ADR-0022: a venda casada com pedido **FULL** deixou de ser fiscal-only e passa a baixar o galpão; **e pela ADR-0027**: pedido com produto rastreável é excluído do Faturador (emissão própria obrigatória)
- [ADR-0022](DOCs/decisions/ADR-0022-baixa-full-dirigida-pelo-retorno-simbolico.md) — Baixa do FULL dirigida pelo **retorno simbólico** (o ML emite 2 notas por venda FULL: `sale` + `symbolic_inbound_return`); o pedido **não** debita o FULL; supersede o ponto correspondente da ADR-0019

- [ADR-0023](DOCs/decisions/ADR-0023-estoque-composto-derivado.md) — Estoque de **produto composto (kit) é derivado** dos componentes em toda leitura, **nunca materializado** (`stock_quantity` do kit é sempre 0); ponto único `stock_calculator.composite_stock`; venda do kit reserva/baixa os **componentes**; kit fora do snapshot contábil
- [ADR-0024](DOCs/decisions/ADR-0024-galpao-work-type-dropship-multilojas.md) — **Tipo de trabalho do Galpão** (`warehouses.work_type`): `dropship` (conta vende PG + própria CMIG) × `multilojas` (só a própria CMIG; publicar PG é bloqueado). Enforcement em **ponto único** (`services/work_type_guard`) aplicado em TODOS os caminhos de publicação (anúncios + listings ML/Shopee); UI do Catálogo esconde a aba PG em multilojas; `work_type` inválido falha alto (400)
- [ADR-0025](DOCs/decisions/ADR-0025-rbac-permissoes-acao-editaveis.md) — **RBAC: permissões de ação editáveis por perfil** (Opção B): decompõe os 47 gates `require_role` dos routers em **permissões de ação nomeadas** (`require_permission("chave")`, catálogo em `services/action_permissions.py`, tabela `profile_action_permissions`), editáveis por perfil na UI. `base_role` **permanece** como **modo de escopo de dados** (as ~150 checagens `role==` de isolação galpão/CMIG **não** foram tocadas). Admin bypassa; fallback pro default do base_role preserva o comportamento no deploy. eShip segue role-based por ora
- [ADR-0026](DOCs/decisions/ADR-0026-papel-galpao-unificado.md) — **Papel único "Galpão"** (unifica `go`+`ugo`; emenda a ADR-0025): colapsa os dois papéis de galpão num único escopo (valor canônico `go`, rótulo "Galpão"; `ugo` aposentado, mantido no CHECK p/ rollback). Comportamento canônico = **isolado por galpão** (todo Galpão vê só o próprio `warehouse_id`; só admin é global) — **remove** os bypasses globais do antigo `ugo`. Dono-vs-operador vira **permissão de perfil + POSSE de registro em `goes`** (não `base_role`, não `go_id` herdado): ponto único `warehouse._owned_go_id`/`_can_access_warehouse`. eShip/import-sync/kit passam a incluir `go`; recompute global vira admin-only. Migração 140 idempotente (role/base_role ugo→go + consolida os 2 perfis-sistema num "Galpão", sem backfill de go_id). Devolução não-escopada por galpão = follow-up
- [ADR-0027](DOCs/decisions/ADR-0027-rastreabilidade-lote-validade-serial.md) — **Produtos rastreáveis (lote/validade/serial/medicamento)** como **sub-ledger paralelo aditivo** sobre o estoque escalar event-sourced (ADR-0004 intocado). `product_lots`/`product_serials`/`stock_lot_allocations`/`invoice_item_lots` (migrations 143/144). Invariante por construção `Σ balance == stock_quantity` (lote sintético **SEM-LOTE** reconcilia). Baixa **order-driven** (FEFO no `confirm_dispatch`; FEFO auto na emissão); reversão reusa a alocação. Duas travas do dono: rastreável **só emissão própria** (`assert_order_own_emission` via `affected_products_from_order`) e **nunca FULL** (`resolve_full_cmig_product`+`available_to_push`). Fiscal `<rastro>`/`<med>` só na emissão própria (snapshot imutável). **Emenda ADR-0008/0015/0021** (Faturador exclui rastreável). Relatórios `/api/v1/traceability` escopados por galpão (ADR-0026). Follow-ups: Shopee-Invoice-Issuer/CPF-DC-e, drift monitor, variante, inventário-por-lote, eShip (Fase 5 adiada)

- [ADR-0028](DOCs/decisions/ADR-0028-emissor-multiregime-fiscal-por-produto.md) — **Emissor NF-e multi-regime + codificação fiscal por produto** (emenda ADR-0015): o emissor próprio passa a cobrir **Regime Normal (CRT 3)** além do Simples — `xml_builder` monta `ICMS00/20/40/41/50/60` (+`ICMS90` fallback), `IPI`, `PIS/COFINS` reais por CST e `ICMSTot` real; **Simples byte-idêntico** (zero regressão). Tributação **por produto** com cascata **produto → default da CMIG → fallback** (`services/fiscal/fiscal_resolver.py`), **fail-loud** em CRT 3 sem CST, e **snapshot imutável** no `InvoiceItem` na criação da nota (migrations 147/148). Reforma **IBS/CBS/IS gated** por `tax_regime_mode` (não emitida no `legacy`). Fases futuras: ICMS10/70 completos, DIFAL Normal, grupos IBS/CBS no XML, NFC-e. Pré-req p/ emitir: config fiscal da CMIG (CRT/IE/IBGE/série) + cert A1 + prova em homologação

- [ADR-0029](DOCs/decisions/ADR-0029-cmig-product-mode.md) — **Modo de produto da CMIG** (`cmigs.product_mode`: `both`/`cmig_only`/`pg_only`, migration 149): define quais grupos de produto (PG×CMIG) aparecem/são permitidos na venda local e publicação, **por CMIG** — eixo ortogonal ao `work_type` do galpão (ADR-0024; multilojas vence por AND). **Ponto único** `services/product_mode.py::assert_product_group_allowed(..., is_pg, is_cmig, is_full)` (o `work_type_guard` virou adaptador que delega, fim das cópias inline). **Exceção FULL** (`is_full` isento): CMIG sempre no envio ao FULL (ADR-0010); criar CMIGProduct nunca bloqueado; `pg_only` bloqueia publicar/vender CMIG direto mas o push de estoque FULL é isento. Fail-loud (403) nos pontos de mutação (anúncio/listing/pedido-manual); `/catalog` segue warehouse-scoped + front esconde aba. Default `both` (zero regressão). 16 testes
- [ADR-0030](DOCs/decisions/ADR-0030-emissao-nfe-por-conta-own-vs-marketplace.md) — **Modo de emissão de NF-e por conta** (própria × marketplace): gera a NF-e de pedidos **não-FULL** pelo sistema (emissão própria SEFAZ) em vez do emissor do marketplace, por conta
- [ADR-0031](DOCs/decisions/ADR-0031-recebimento-por-galpao-banco-e-flags.md) — **Recebimento por Galpão (Fase 1)**: cadastro de **Banco/gateway** por galpão (`warehouse_bank_accounts`, API Key cifrada Fernet, estilo ASAAS) + 2 flags de checkout inertes (`pg_requires_prepaid`, `manual_sale_requires_payment`). Migration 152
- [ADR-0032](DOCs/decisions/ADR-0032-asaas-integracao-pagamento-webhook.md) — **Integração ASAAS (Fase 2)**: cobrança da venda manual + webhook público. `payment_charges` (migration 153); webhook ancorado em `asaas_payment_id` (nunca no corpo), auth por hash constant-time, idempotente por `webhook_events`, flipa só `payment_status`. `ensure_webhook` idempotente; `charge_service` = ponto único (valor = venda + frete; lock anti-TOCTOU)
- [ADR-0033](DOCs/decisions/ADR-0033-checkout-publico-venda-manual-token.md) — **Checkout público da venda manual (Fase 3)**: `orders.public_token` (migration 154) dá ao cliente acesso sem login para ver/ajustar itens e pagar via ASAAS. Mexer em item com desconto (`unit_price < list_price` snapshot) marca `needs_price_review` e **bloqueia o pagamento** até o operador liberar. Editar cancela cobrança velha (não cobra valor errado). Estágios derivados; separação/entrega adiados
- [ADR-0034](DOCs/decisions/ADR-0034-credito-cmig-galpao-extrato.md) — **Crédito CMIG × Galpão (Fase 4)**: razão append-only `cmig_warehouse_credits` (migration 155); saldo derivado (Σcred − Σdéb) via `services/credit_service`; Extrato em Financeiro escopado por galpão/CMIG (ADR-0026). Enforcement de PG pré-pago na entrega = guarda pronta, adiada junto com os estados 3-5
- [ADR-0035](DOCs/decisions/ADR-0035-perfil-unico-escopo-no-perfil-de-acesso.md) — **Papel único; escopo deriva do Perfil de Acesso**: `users.role` deixa de ser coluna e vira hybrid derivado de `UserProfile.base_role` ("Escopo de dados"); o SSOT `services/data_scope.py` passa a ler `user._scope_base_role` (carimbado em `get_current_user`). eShip migrado de role→permissão (chaves `eship_*`, migration 158). Coluna `users.role` removida (migration 159)
- [ADR-0036](DOCs/decisions/ADR-0036-capacidade-nunca-se-amarra-em-escopo.md) — **Capacidade nunca se amarra em helper de escopo**: capacidades que estavam presas em `is_conta/is_galpao/is_global` (criar CMIG, config fiscal + certificado A1, tipo fiscal, DC-e, import/sync PG, movimentar estoque) viram **permissões de ação editáveis por Perfil** (7 chaves novas + `nfe_gerenciar` reusado; migration 162 semeia = zero-regressão). Autorização = **permissão (capacidade) AND `assert_cmig_access` (escopo, intocado)**. Dono de galpão (posse em `goes`, ADR-0026) reconhecido como proprietário em `require_owner`; `create_cmig` scope-aware (galpão forçado ao próprio `warehouse_id`). Canal de ação no front (`action_permissions` no login/refresh + `hasAction()` + `meta.actionKey`). **Emenda** ADR-0018 (tipo fiscal vira permissão, default ac/admin) e ADR-0017 (DC-e vira permissão, default admin). Follow-up: rotas de operador ainda em `meta.role` + views CmigProductListView/IntegrationsView/CollaboratorsModal
- [ADR-0038](DOCs/decisions/ADR-0038-google-drive-armazenamento-imagens.md) — **Armazenamento de imagens no Google Drive** (OAuth2 `drive.file`): integração OAuth de usuário (refresh+access cifrados Fernet; app PUBLICADO; conta ativa única admin-only; migration 167 `google_drive_accounts`). Pasta raiz `Ecommerce_Imagens` + subpastas por área (`Separacao`…), `ensure_folder` idempotente. **Download servido pelo sistema, nunca por link público (LGPD)** + **escopo por galpão obrigatório** (resolve o `drive_file_id` pelo registro escopado, nunca pelo id cru — anti-IDOR). Callback público só troca o `code`. 1º consumidor: fotos da separação (ADR-0005 emendada). Convive com `static/uploads` (migrar o resto é follow-up)
- [ADR-0037](DOCs/decisions/ADR-0037-cancelamento-venda-direta-credito-cliente-e-devolucao.md) — **Cancelamento de venda direta + crédito do cliente + NF-e de devolução**: (1) etiqueta de envio sem identificação do produto (transportador não vê o conteúdo; produto só na conferência interna ML); (2) `POST /orders/{id}/cancel` soft-cancel (libera reserva, cancela cobrança ASAAS, 409 `requires_devolution` se há NF-e autorizada) com permissão `pedido_cancelar`; (3) **3º razão de crédito** `customer_credits` (migration 163, append-only por `(cmig_id, person_id)`, UNIQUE `(order_id, entry_type)`) distinto do ADR-0034 — passivo com o COMPRADOR, gerado ao cancelar pedido pago; `services/customer_credit_service` + `GET/POST /api/v1/customer-credits` (permissão `credito_cliente_gerenciar`); (4) `POST /orders/{id}/devolution-nfe` emite rascunho de devolução (entrada, finalidade=4, CFOP 1202/2202, snapshot fiscal, refNFe via `invoices.referenced_access_key` migration 165). **Invariante crítico (ADR-0009):** NF-e de devolução `stock_updated=False`, inerte ao replay (guard em `_apply_stock_movement`) — retorno ao estoque só pela inspeção (sem dupla-contagem). Seed migration 164 (zero-regressão). Transmissão SEFAZ a validar em homologação. Follow-ups: abrir `Return` de inspeção na emissão; tela de extrato/débito do crédito do cliente; cancelamento fiscal de DC-e (CPF)

- [ADR-0039](DOCs/decisions/ADR-0039-enderecamento-fisico-estoque.md) — **Endereçamento físico de estoque** como camada ADITIVA de localização (diz ONDE o estoque está, reconcilia com o saldo escalar e NUNCA grava saldo — espírito SEM-LOTE da ADR-0027). **Árvore** `storage_locations` por galpão (level_type texto livre; `full_code` derivado recomputado na subárvore no rename; `is_storable` na folha; `area_kind` → galpão misto; UNIQUE `(warehouse_id, full_code)`); **alocação** `product_allocations` (±lot_id, UNIQUE funcional `(loc,prod,NVL(lot,0))`); **caixas** `product_allocation_packs` (heterogêneas) + **embalagem-padrão** reutilizável; **etiqueta/QR** `storage_box_labels` (token→alocação, QR/barcode renderizados no front via CDN, sem dep no backend); **código interno** `product_eans.source` ('ean'|'internal') = EAN-13 faixa prefixo 2 + DV, único SÓ p/ internos (índice funcional — UNIQUE global seria regressão cross-galpão), gerar dispara recompute. Invariante: Σ qty_units reconcilia com `stock_quantity` LOCAL (FULL de fora, ADR-0019); **kit excluído** (ADR-0023). Escopo por galpão derivado do usuário, nunca do path (ADR-0026); capacidade = permissão de perfil `endereco_configurar`/`endereco_movimentar` (ADR-0036; migrations 173/174). Rotas `/api/v1/storage`. Fase 1 = estrutura+alocação+caixas+mapa+reconciliação+etiqueta+código interno; **Fase 2** = picking (rota+FEFO+esgotar caixa aberta/preservar fechada) no `PickingCart` (ADR-0005 a emendar); Fase 3 = inventário por endereço/transferência em massa/box tracking

Nova decisão arquitetural → criar próximo ADR em `docs/decisions/`.

### Lições Aprendidas

Ver `docs/lessons-learned.md` para armadilhas conhecidas documentadas (L-001 a L-013).

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
- **Venda direta — cancelamento + crédito do cliente + NF-e de devolução (ADR-0037, EM PRODUÇÃO 2026-10-26):** (1) etiqueta de envio sem identificação do produto (3 renderizadores; produto só na conferência interna ML); (2) `POST /orders/{id}/cancel` soft-cancel (libera reserva + cancela cobrança ASAAS + crédito ao cliente se pago + 409 `requires_devolution` se há NF-e); (3) 3º razão `customer_credits` (migrations 163-165) + `GET/POST /api/v1/customer-credits`; (4) `POST /orders/{id}/devolution-nfe` (rascunho entrada finalidade=4, CFOP 1202/2202, refNFe, snapshot fiscal; **inerte ao replay** `stock_updated=False` — ADR-0009, sem dupla-contagem); front: botão "Cancelar pedido" + fluxo. Auditado (trio): 2 CRITICAL + 3 HIGH corrigidos (guards pré-release, UNIQUE anti-TOCTOU, order_id cross-scope, clone fiscal drift-proof, fail-loud). Verificado em produção: suite 317 ok (2 pré-existentes), migrations aplicadas, health 200, rotas no OpenAPI, build front. **A validar com o dono/contabilidade em homologação:** transmissão SEFAZ da devolução (CFOP/tPag90/refNFe). **Follow-ups:** abrir `Return` de inspeção na emissão; tela de extrato/débito do crédito do cliente; cancelamento fiscal de DC-e (CPF).
- **Fase atual:** **RBAC/Perfil de Acesso (ADR-0035/0036)** — papel único + escopo no Perfil, e capacidades (CMIG/fiscal/PG/estoque) decompostas em permissões editáveis. Antes: Recebimento/checkout por Galpão (Fases 1-4, ADR-0031→0034, ainda não deployado); Paridade Shopee (ADR-0020) e NF-e própria SEFAZ (ADR-0015/0016) em produção.
- **RBAC capacidades → Perfil (ADR-0036, EM PRODUÇÃO 2026-10-24, commit `116fe69`):** as capacidades que estavam presas no helper de ESCOPO (`is_conta/is_galpao/is_global`) — criar/editar CMIG, tipo fiscal, co-admin, eShip da CMIG, config fiscal + **certificado A1**, DC-e, import/sync PG, inutilizar NF-e, desmontar KIT — viraram **permissões de ação editáveis por Perfil** (7 chaves novas + `nfe_gerenciar` reusado). Autorização = **permissão AND `assert_cmig_access`** (escopo intocado). Dono de galpão reconhecido como proprietário via posse em `goes` (ADR-0026); `create_cmig` scope-aware. Canal de ação no front (`action_permissions` no login/refresh + `hasAction()` + `meta.actionKey`). **Migration 162 rodada em produção = 13 linhas (zero-regressão: admin=7, ac=3, go=3).** Trio de auditoria 0 CRÍTICO; 2 ALTO/HIGH corrigidos (`/invoices/inutilize` ganhou escopo; `update_cmig` exige `cmig_gerenciar`). Verificado em produção (commit no servidor, `/docs` 200, nginx 200, bundle novo). Limpeza de 3 imports órfãos no commit `9e8caf4` (não-deployado — F401 sem runtime). **Pendente do dono:** habilitar `cmig_gerenciar`+`cmig_fiscal_config` no perfil do `go.harmonyexpress` na tela Perfil (zero-regressão: o deploy sozinho não muda nada p/ ele) e exercitar criar CMIG + certificado. **Follow-up (não trancar operadores — exige verificar seed de menu por item):** cadastrar produto CMIG como `go` (rota/tela de produtos) + migrar rotas de operador (returns/estoque/monitoring/anuncios-AC/campanha/full-cnpjs/settings-users-warehouse) de `meta.role` p/ menuKey/actionKey; views CmigProductListView/IntegrationsView/CollaboratorsModal.
- **Recebimento/checkout (2026-10-21, NÃO deployado — aguarda revisão + credencial ASAAS do dono):** Fases 1-4 implementadas, auditadas (trio, 0 CRITICAL/BLOQUEADOR; HIGH/ALTO corrigidos) e verificadas por import+pytest(286 ok, 2 pré-existentes)+`npm run build`. **F1** (ADR-0031, migration 152): `warehouse_bank_accounts` cifrada + 2 flags. **F2** (ADR-0032, migration 153): `services/asaas_service` + `charge_service` (ponto único: valor = venda+frete, lock anti-TOCTOU, cancela+recria se valor mudou) + webhook público `/api/v1/webhooks/asaas` (ancora na cobrança, hash constant-time, idempotente, flipa só `payment_status`; trata refund; notifica) + `create/list/refresh/cancel-charge`; delete de banco bloqueado se há cobrança. **F3** (ADR-0033, migration 154): `orders.public_token`/`needs_price_review` + `order_items.list_price`; router público `routers/public_checkout.py` (sem JWT, só pelo token) GET/PATCH-item/POST-pay; operador: public-link (gerar/regenerar/revogar) + price-review/approve; página `PublicCheckoutView.vue` (`/checkout/:token`, usa fetch); editar item com desconto bloqueia pagamento até revisão; teto de qtd. **F4** (ADR-0034, migration 155): `cmig_warehouse_credits` + `credit_service` + `routers/credits.py` + tela Extrato (`/financial/credito`). **Migrations 152-155 ainda NÃO rodadas em produção.**
- **Fase anterior (Paridade Shopee):** NF-e própria SEFAZ (ADR-0015/0016) em produção (478 provada cStat 100 em homologação).
- **Último ponto validado:** **Paridade Shopee Fases 1-7 entregues** (2026-07-25) — config **LIVE** em produção (`.env` partner_id 2039749 + chave live + host produção); loja real "Made In Group" (shop_id 1556009762) conectada (conta id 141). **Regra de ouro respeitada:** nenhum diff dentro de bloco `if platform == "mercadolivre"` — tudo entrou por rota/função/ramo novo (ADR-0020). Fase 3 fiscal (`shopee_fiscal.py`, migration 135 `shopee_invoice_status`): upload-invoice **anexa** o XML da emissão própria (ADR-0015/0017), não emite pela Shopee; bloqueia sem NF-e/DC-e; reentrante. Fase 4 logística (`shopee_logistics.py`): ship (gate NF-e)/label(poll 202)/tracking; `separation.py` exclui Shopee do picking (separação é só ML). Fases 5-6: FIX crítico `update_item_stock` (`seller_stock`), `listings.py` `_build_shopee_item` reescrito + pause/reactivate, `shopee_catalog.py`. Fase 7 custos: `get_escrow_detail`→`Order.platform_fee` (verificado ao vivo: 46.8+25.2=72.0). Commits `3a8b239`/`0e7dfef`/`0da24db`/`146b329`/`39560be`. Auditado por shopee-especialista + consistency-auditor + quality-guardian (CRITICALs corrigidos). **Também nesta sessão:** eShip "Armazenaki" (conciliação ordens enviadas × WMS, per-CMIG + consolidado; commits `240a573`/`044bc82`/`e4df93d`); fiscal ML 10714 (2ª onda — `cest` preso no `fiscal_json` de 136 anúncios removido em produção, 161 SKUs re-sync em 3 contas CNPJ, `can_invoice`→true) + mensagem clara p/ 10419 das contas CPF (commit `bca6c5b`); `razaoSocialDestinatario` p/ CNPJ no eShip (commit `cf8f47f` + migration 133).
- **eShip — pedido Shopee ao WMS (2026-09-15, commits `567a18d`/`e42e675`/`a122fa0`):** pedido Shopee agora vai ao eShip "da mesma forma que o ML, com todos os documentos" (pedido do dono). **Fase 1** — parsing agnóstico do endereço (estado por extenso→sigla via `_UF_POR_NOME`; aliases Shopee `full_address`/`district`/`town`/`zipcode`, chaves ML primeiro → sem regressão) + `transporte_code_for_order` por ramo novo; verificado com 3 pedidos Shopee reais. **Fase 2** — etiqueta (PDF) anexada no WMS: ponto único `shopee_service.resolve_label_pdf` (create→poll(READY)→download; None em PROCESSING; raise em FAILED), `eship._resolve_labels_shopee` (reusa cache `private_labels/shopee_{id}.pdf` com guard `size>0`; `(pdf, None)` — Shopee não tem ZPL) via dispatcher `_resolve_labels_for`; mensagem "etiqueta não liberada" agnóstica. Regra de ouro respeitada (nada em `if platform == "mercadolivre"`). 30 testes; deploy PM2 OK; **exercitado ao vivo** com 8 pedidos Shopee reais — a costura chega ao `create_shipping_document`, a Shopee recusa (`batch_api_all_failed`, pré-`ship_order`) e degrada sem travar. Auditado (quality-guardian + consistency-auditor, sem CRITICAL/HIGH). Follow-up: migrar o `label()` inline de `shopee_logistics.py` para o ponto único.
- **Próximo passo (recebimento/checkout):** com o dono: (1) revisar o fluxo; (2) **rodar as migrations 152-155** em produção; (3) deploy do backend+frontend; (4) cadastrar uma **conta ASAAS real** no galpão e **Configurar webhook**; (5) **exercitar**: gerar link do pedido manual, abrir em `/checkout/:token`, ajustar item, confirmar que item com desconto bloqueia o pagamento, pagar via ASAAS e ver o webhook confirmar (`payment_status=paid`). Follow-ups documentados: adicionar produto novo na página pública; rate-limit/expiração do token; edição de preço na re-análise; wire do `assert_pg_prepaid` no gate de entrega (com os estados Separação/Enviado/Entregue, adiados pelo dono); débito automático do crédito na entrega. **Shopee (anterior):** exercitar `upload_invoice_doc`/`ship_order`/etiqueta/`add_item` reais + Push Key LIVE no `.env`; Transmitir SEFAZ da 478 em produção.
- **Bloqueios:** `BACKEND/Wallet_MIGECOMMERCE/` ausente — sem ela o backend não conecta no Oracle ATP. Recebimento/checkout: sem **credencial ASAAS real** o fluxo de cobrança/webhook não é validável no DEV. Shopee: Push Key LIVE ainda não cadastrada no `.env`.
- **Riscos ativos:** Duplicação deliberada `shopee_service` ⇆ `ml_service` (preço de não acoplar os dois — ADR-0020); manter a regra de ouro em toda evolução Shopee futura.
- **Decisões pendentes:** Deploy em produção via Docker (caminho do `docker-compose.yml` novo) ou seguir com uvicorn + supervisor — definir antes do próximo deploy.

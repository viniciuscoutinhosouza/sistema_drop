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
| `/api/v1/shopee` | Shopee: fiscal (upload NF-e), logística (ship/label/tracking), catálogo, custos |
| `/api/v1/integrations/eship` | eShip/Armazenaki (WMS): envio de ordens + conciliação enviadas × WMS |

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
- [ADR-0008](DOCs/decisions/ADR-0008-nfe-batch-mensal-e-anuncio-full-quando-local-zero.md) — Sync mensal de NF-e (batch ML) + anúncio não-FULL anuncia FULL quando LOCAL=0
- [ADR-0009](DOCs/decisions/ADR-0009-devolucao-nfe-driven.md) — Devolução NF-e-driven: NF-e fiscal-only (stock_updated=False) + contadores de inspeção como fonte canônica
- [ADR-0010](DOCs/decisions/ADR-0010-full-sempre-cmig.md) — Estoque FULL é sempre do produto CMIG (auto-criação de espelho do PG); sync ML vira conferência
- [ADR-0011](DOCs/decisions/ADR-0011-estudos-assincronos-ia-ml.md) — Estudos assíncronos IA+ML (job in-process por request + estudo persistido como memória)
- [ADR-0012](DOCs/decisions/ADR-0012-coletor-ml-local-camoufox.md) — Coletor de busca ML local (Camoufox) via HTTP, fora do servidor Oracle (3ª fonte opt-in da Análise de Concorrência)
- [ADR-0013](DOCs/decisions/ADR-0013-datahora-utc-armazenamento-conversao-borda.md) — Data/hora: UTC aware no armazenamento/transporte, conversão para America/Sao_Paulo na borda (fonte única: `utils/formatters.js` + `services/datetime_br.py`)
- [ADR-0014](DOCs/decisions/ADR-0014-estoque-anuncio-pausa-auto-e-sync-ml-metadados.md) — Estoque fixo vira teto (`min(fixo, disponível)`); pausa/reativação automática do anúncio por disponibilidade (`auto_paused`); FULL derivado na leitura (sem coluna redundante); job horário que sincroniza metadados do ML (promoções/descrição/status/FULL) **menos estoque**
- [ADR-0015](DOCs/decisions/ADR-0015-emissao-propria-nfe-sefaz.md) — Emissão própria de NF-e direto à SEFAZ (mTLS + XMLDSig), substituindo o Focus; série manual configurável separada do marketplace; transmissão síncrona (indSinc=1) recuperável por N-6; certificado A1 local + senha cifrada (Fernet master key) e XML autorizado fora de `static/`
- [ADR-0016](DOCs/decisions/ADR-0016-distribuicao-dfe-propria.md) — Distribuição de DFe própria (Ambiente Nacional) com controle de NSU por CMIG; manifestação própria; rate-limit cStat 656; parser endurecido + teto anti zip-bomb no docZip de terceiros
- [ADR-0017](DOCs/decisions/ADR-0017-dce-emissao-marketplace.md) — Emissão de DC-e (modelo 99) das contas CPF direto na SVRS no perfil **Marketplace** (a MIG assina com o A1 do CNPJ dela, por conta e ordem); chave inclui `tpEmit`; assinatura sem prefixo `ds:`; remetente = endereço do Galpão (IBGE por cidade+UF); destinatário `idOutros` sem CPF; DACE (PDF+QR); gate `dce_authorized` por CMIG
- [ADR-0018](DOCs/decisions/ADR-0018-cmig-identidade-fiscal-mutavel.md) — Identidade fiscal da CMIG é **mutável por substituição** (converter CPF ⇆ CNPJ zera o documento anterior, mantém "exatamente um"); alterar o tipo exige `ac`/`admin`; CPF→CNPJ exige IE+IBGE; efeitos colaterais (regime `live` de pedidos pendentes, recadastro eShip) são **avisados, não bloqueados**; documentos emitidos ficam como snapshot
- [ADR-0019](DOCs/decisions/ADR-0019-full-recomputavel-replay.md) — Estoque FULL **recomputável (replay)** a partir de 0 (como o local); débito de venda **dirigido pelo pedido** (não pela NF-e), uma única vez e só do FULL; reconciliação por inventário
- [ADR-0020](DOCs/decisions/ADR-0020-paridade-shopee-por-costuras.md) — Paridade Shopee por **costuras agnósticas** (Fases 1-7) entrando SEMPRE por ramo/rota/função nova, **NUNCA** dentro de bloco `if platform == "mercadolivre"` (regra de ouro); rotas sob `/api/v1/shopee` + `shopee_service` + `listings.py` agnóstico; fiscal = **anexar** XML da emissão própria (ADR-0015/0017), não emitir pela Shopee; logística fora da separação (picking é só ML); superfície comum tocada só aditivamente

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
- **Fase atual:** Paridade Shopee (Fases 1-7) — dar à Shopee paridade operacional com o ML por costuras agnósticas, sem tocar o caminho crítico do ML (ADR-0020). NF-e própria SEFAZ (ADR-0015/0016) já em produção (478 provada cStat 100 em homologação).
- **Último ponto validado:** **Paridade Shopee Fases 1-7 entregues** (2026-07-25) — config **LIVE** em produção (`.env` partner_id 2039749 + chave live + host produção); loja real "Made In Group" (shop_id 1556009762) conectada (conta id 141). **Regra de ouro respeitada:** nenhum diff dentro de bloco `if platform == "mercadolivre"` — tudo entrou por rota/função/ramo novo (ADR-0020). Fase 3 fiscal (`shopee_fiscal.py`, migration 135 `shopee_invoice_status`): upload-invoice **anexa** o XML da emissão própria (ADR-0015/0017), não emite pela Shopee; bloqueia sem NF-e/DC-e; reentrante. Fase 4 logística (`shopee_logistics.py`): ship (gate NF-e)/label(poll 202)/tracking; `separation.py` exclui Shopee do picking (separação é só ML). Fases 5-6: FIX crítico `update_item_stock` (`seller_stock`), `listings.py` `_build_shopee_item` reescrito + pause/reactivate, `shopee_catalog.py`. Fase 7 custos: `get_escrow_detail`→`Order.platform_fee` (verificado ao vivo: 46.8+25.2=72.0). Commits `3a8b239`/`0e7dfef`/`0da24db`/`146b329`/`39560be`. Auditado por shopee-especialista + consistency-auditor + quality-guardian (CRITICALs corrigidos). **Também nesta sessão:** eShip "Armazenaki" (conciliação ordens enviadas × WMS, per-CMIG + consolidado; commits `240a573`/`044bc82`/`e4df93d`); fiscal ML 10714 (2ª onda — `cest` preso no `fiscal_json` de 136 anúncios removido em produção, 161 SKUs re-sync em 3 contas CNPJ, `can_invoice`→true) + mensagem clara p/ 10419 das contas CPF (commit `bca6c5b`); `razaoSocialDestinatario` p/ CNPJ no eShip (commit `cf8f47f` + migration 133).
- **Próximo passo:** **Exercitar o que depende de evento/ação do dono na Shopee** (não validável no sandbox/DEV): `upload_invoice_doc` com anexo real, `ship_order`/etiqueta (exige pedido READY_TO_SHIP), `add_item` real (publicar item de teste), e cadastrar a **Push Key LIVE** no `.env`. Fiscal SEFAZ própria: dono clicar **Transmitir SEFAZ** da 478 em **produção** (documento fiscal real) → cStat 100.
- **Bloqueios:** `BACKEND/Wallet_MIGECOMMERCE/` ausente — sem ela o backend não conecta no Oracle ATP. Shopee: Push Key LIVE ainda não cadastrada no `.env`.
- **Riscos ativos:** Duplicação deliberada `shopee_service` ⇆ `ml_service` (preço de não acoplar os dois — ADR-0020); manter a regra de ouro em toda evolução Shopee futura.
- **Decisões pendentes:** Deploy em produção via Docker (caminho do `docker-compose.yml` novo) ou seguir com uvicorn + supervisor — definir antes do próximo deploy.

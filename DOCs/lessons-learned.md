# Lições Aprendidas — Sistema Drop (MIG ECOMMERCE)

Formato: `L-NNN | Contexto → O que aconteceu → Lição → Como evitar`

---

## Backend / Oracle

**L-001 | bcrypt + passlib**  
Contexto: Atualização de dependências.  
O que aconteceu: Versões de `bcrypt` acima de `4.0.1` quebram a integração com `passlib[bcrypt]`.  
Lição: A versão do bcrypt deve ser fixada em `4.0.1`.  
Como evitar: Não atualizar `bcrypt` sem testar `passlib` primeiro. Pin explícito no `requirements.txt`.

**L-002 | db.add() / db.delete() síncronos**  
Contexto: SQLAlchemy 2.x + AsyncSyncSession wrapper.  
O que aconteceu: Usar `await db.add()` ou `await db.delete()` causa `TypeError` porque esses métodos são síncronos no wrapper.  
Lição: Só `db.execute()`, `db.flush()`, `db.commit()`, `db.refresh()` e `db.rollback()` precisam de `await`.  
Como evitar: Nunca usar `await` em `db.add()` e `db.delete()`. Verificar ao revisar novos routers.

**L-003 | CLOB / LOB retornado como objeto**  
Contexto: Oracle ATP com campos `Text` (CLOB) no SQLAlchemy.  
O que aconteceu: Sem configuração especial, campos CLOB retornavam objetos LOB em vez de strings, causando erros de serialização JSON.  
Lição: Definir `oracledb.defaults.fetch_lobs = False` globalmente na inicialização do engine.  
Como evitar: Já configurado em `database.py`. Não remover essa linha.

**L-004 | await db.flush() antes de usar PK**  
Contexto: Criação de registro e uso imediato do ID gerado.  
O que aconteceu: Após `db.add(obj)`, o `obj.id` ainda é `None` até o flush/commit.  
Lição: Chamar `await db.flush()` após `db.add()` para obter o PK gerado sem commitar a transação.  
Como evitar: Padrão: `db.add(obj)` → `await db.flush()` → usar `obj.id`.

**L-005 | selectinload obrigatório para relacionamentos**  
Contexto: Carregar `images` e `variants` de um produto.  
O que aconteceu: Relacionamentos sem `selectinload` retornam `MissingGreenlet` em contexto async.  
Lição: Sempre usar `selectinload(Model.relacao)` em queries que precisem de joins.  
Como evitar: Ao criar novo endpoint com relacionamentos, incluir `options(selectinload(...))` na query.

**L-006 | size_label, não size**  
Contexto: Coluna de tamanho em variantes.  
O que aconteceu: O campo de tamanho nas variantes se chama `size_label` (não `size`) em `CatalogProductVariant` e `CMIGProductVariant`.  
Lição: Usar sempre `size_label`.  
Como evitar: Buscar por `size_label` ao referenciar variantes.

---

## Mercado Livre / Integrações

**L-007 | Webhooks ML chegam em snake_case**  
Contexto: Processamento de notificações do Mercado Livre.  
O que aconteceu: Campos do webhook chegam em snake_case (`seller_id`, `resource`), já tratados em `ml_service.py`.  
Lição: Não tentar converter manualmente — o serviço já cuida disso.  
Como evitar: Processar webhooks sempre via `ml_service.py`.

**L-008 | Oracle Cloud Always Free — 2 ATP databases**  
Contexto: Infraestrutura gratuita.  
O que aconteceu: A instância Always Free permite 2 bancos ATP, suficientes para prod + staging.  
Lição: Usar um banco para produção e outro para homologação, sem custo adicional.  
Como evitar: N/A — oportunidade, não problema.

---

## Frontend

**L-009 | Proxy Vite — ws: true obrigatório para Socket.io**  
Contexto: Configuração do proxy em `vite.config.js`.  
O que aconteceu: Sem `ws: true` no proxy `/ws`, o Socket.io não consegue fazer upgrade para WebSocket.  
Lição: O proxy `/ws` precisa de `ws: true` e `changeOrigin: true`.  
Como evitar: Já configurado. Não remover `ws: true` do proxy.

**L-010 | useApi obrigatório (não axios direto)**  
Contexto: Chamadas HTTP no frontend.  
O que aconteceu: Chamar `axios` diretamente bypassa os interceptors de JWT (injeção do token + refresh automático em 401).  
Lição: Sempre usar o composable `useApi` que já encapsula o Axios configurado.  
Como evitar: Nunca importar `axios` diretamente nos componentes/views.

---

## Windows / Dev Environment

**L-011 | WindowsSelectorEventLoopPolicy em Windows**  
Contexto: Rodar FastAPI + asyncio no Windows.  
O que aconteceu: `asyncio` no Windows usa `ProactorEventLoop` por padrão, incompatível com algumas libs.  
Lição: `WindowsSelectorEventLoopPolicy` deve estar configurado em `main.py`.  
Como evitar: Não remover o bloco `if sys.platform == 'win32'` do `main.py`.

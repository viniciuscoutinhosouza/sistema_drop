# ADR-0001 — Oracle DB + AsyncSyncSession wrapper

**Status:** Accepted  
**Data:** 2026-05-15

## Contexto

O sistema requer um banco de dados robusto com suporte a transações ACID complexas, e a equipe já possui contrato Oracle Cloud Always Free (2 ATP databases). FastAPI com SQLAlchemy 2.x é assíncrono por design, mas o driver `oracledb` não oferece suporte async nativo.

## Decisão

Manter Oracle ATP como banco de dados e implementar um wrapper `AsyncSyncSession` que executa as operações síncronas do `oracledb` via `asyncio.to_thread()`, preservando a interface assíncrona nos routers FastAPI.

## Alternativas Consideradas

| Alternativa | Motivo para Rejeitar |
|-------------|---------------------|
| PostgreSQL (Supabase) | Migração do schema completo + dados de produção com custo/risco alto; Oracle já funcionando |
| SQLite para dev | Dialeto diferente de Oracle; mascararia bugs de produção |
| Driver síncrono com FastAPI | Bloquearia event loop; prejudicaria performance de I/O concorrente |

## Consequências

- **Positivo**: Mantém interface `async/await` nos routers; sem bloqueio de event loop.
- **Negativo**: `db.add()` e `db.delete()` são síncronos — nunca usar `await` neles. `db.execute()` deve sempre usar `await`.
- **Regra derivada**: Todo router deve usar `AsyncSession = Depends(get_db)` mas o tipo real é `AsyncSyncSession`.
- **Regra derivada**: `oracledb.defaults.fetch_lobs = False` ativado globalmente para auto-converter CLOB em string.

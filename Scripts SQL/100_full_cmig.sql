-- 100_full_cmig.sql — FULL é sempre do produto CMIG (ADR-0010)
--
-- Esta mudança é de COMPORTAMENTO (código), não de schema: `full_stock` mantém a
-- chave (product_type, product_id, marketplace_account_id), mas product_type passa a
-- ser SEMPRE 'cmig'. Não há DDL obrigatório aqui.
--
-- A conversão dos dados existentes (linhas product_type='pg' → 'cmig', auto-criando o
-- CMIGProduct espelho do PG) é feita pela rotina idempotente:
--     POST /api/v1/stock/migrate-full-pg-to-cmig?dry_run=true   (relatório)
--     POST /api/v1/stock/migrate-full-pg-to-cmig?dry_run=false  (aplica)
--
-- Índice único que garante "1 CMIGProduct espelho por (cmig, pg)" — torna a
-- auto-criação do espelho idempotente também sob concorrência (re-SELECT+flush
-- sozinho não barra inserts paralelos). Verificado: 0 duplicatas em produção.
-- Oracle indexa apenas linhas onde pg_product_id NÃO é NULL (NULLs não entram no
-- índice composto só quando TODAS as colunas são NULL; aqui cmig_id é NOT NULL, então
-- para não indexar linhas sem vínculo usamos índice baseado em função).
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uix_cmigprod_cmig_pg ON cmig_products('
    || 'CASE WHEN pg_product_id IS NULL THEN NULL ELSE cmig_id END, pg_product_id)';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- Migration 149: modo de grupo de produto da CMIG (product_mode).
--
-- Define quais grupos de produto a CMIG usa/permite (UI do Catálogo, Pedido Manual, publicação):
--   'both'      → usa Produto Geral (PG) + a própria CMIG (comportamento atual).
--   'cmig_only' → só a própria CMIG; o PG fica escondido/bloqueado.
--   'pg_only'   → só o PG; o produto CMIG fica escondido/bloqueado.
--
-- EXCEÇÃO (ADR-0010): o envio ao FULL SEMPRE usa/mostra o produto CMIG, INDEPENDENTE do modo —
-- 'pg_only' + FULL é válido. O guard central (services/product_mode.py) isenta os caminhos FULL.
--
-- Complementar ao warehouse.work_type (ADR-0024): galpão 'multilojas' bloqueia PG no galpão. As
-- regras são ortogonais e combinam por AND — multilojas VENCE. NÃO há backfill cmig_only para
-- galpões multilojas (conceitos independentes).
--
-- Default 'both' + NOT NULL preenche as CMIGs existentes preservando o comportamento atual.
-- Idempotente: ORA-01430 (coluna já existe) e ORA-02264/02275 (constraint já existe) são ignorados.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE cmigs ADD (product_mode VARCHAR2(20) DEFAULT ''both'' NOT NULL)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_name_used   EXCEPTION;  -- ORA-02264: nome de constraint já em uso
  e_already     EXCEPTION;  -- ORA-02275: constraint referencial/duplicada já existe
  PRAGMA EXCEPTION_INIT(e_name_used, -2264);
  PRAGMA EXCEPTION_INIT(e_already, -2275);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE cmigs ADD CONSTRAINT CHK_CMIG_PRODUCT_MODE ' ||
    'CHECK (product_mode IN (''both'',''cmig_only'',''pg_only''))';
EXCEPTION
  WHEN e_name_used THEN NULL;
  WHEN e_already THEN NULL;
END;
/

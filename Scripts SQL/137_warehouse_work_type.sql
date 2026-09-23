-- Migration 137: tipo de trabalho do Galpão (work_type).
--
-- Define a regra de venda das contas do galpão:
--   'dropship'   → contas vendem produtos do Produto Geral (PG) + a própria CMIG.
--   'multilojas' → o PG é só base para cadastro na CMIG; cada conta vende SÓ a própria CMIG.
-- Default 'dropship' (comportamento atual). NOT NULL com default preenche os galpões existentes.
--
-- Idempotente: ORA-01430 (coluna já existe) é ignorado.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE warehouses ADD (work_type VARCHAR2(20) DEFAULT ''dropship'' NOT NULL)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

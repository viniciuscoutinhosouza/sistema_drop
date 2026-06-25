-- Migration 113: credenciais eShip por Conta MIG (empresa)
-- A apikey do eShip é única por empresa (spec eship-integracao-api.md §1). Move a
-- configuração para a CMIG: cada empresa tem seu subdomínio + apikey + código de
-- armazém de origem (codigoArmazemOrigem, obrigatório ao criar ordens).
-- Idempotente via EXCEPTION WHEN e_col_exists.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE cmigs ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('eship_base_url',       'VARCHAR2(500)');   -- ex: https://armazenaki.eship.com.br/v3
  add_col('eship_api_key',        'VARCHAR2(500)');   -- header api: <apikey>
  add_col('eship_warehouse_code', 'VARCHAR2(50)');    -- codigoArmazemOrigem (obrig. na ordem)
  add_col('eship_active',         'NUMBER(1) DEFAULT 0 NOT NULL');
  DBMS_OUTPUT.PUT_LINE('Colunas eShip adicionadas a cmigs.');
END;
/

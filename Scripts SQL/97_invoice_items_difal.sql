-- Migration 97: Campos DIFAL em invoice_items (Fase 1 — EC 87/2015)
-- DIFAL obrigatório em vendas interestaduais a consumidor final não-contribuinte.
-- Idempotente via EXCEPTION WHEN e_col_exists.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE invoice_items ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('difal_base',            'NUMBER(15,2)');
  add_col('difal_aliquota_orig',   'NUMBER(5,2)');   -- alíquota ICMS na UF origem
  add_col('difal_aliquota_dest',   'NUMBER(5,2)');   -- alíquota ICMS na UF destino
  add_col('difal_value',           'NUMBER(15,2)');  -- ICMS diferencial = base × (dest - orig)
  add_col('difal_fcp_aliquota',    'NUMBER(5,2)');   -- FCP (Fundo de Combate à Pobreza) % destino
  add_col('difal_fcp_value',       'NUMBER(15,2)');  -- FCP = base × fcp_aliquota
  DBMS_OUTPUT.PUT_LINE('Colunas DIFAL adicionadas a invoice_items.');
END;
/

-- Migration 98: Campos IBS / CBS / IS em invoice_items (Fase 2 — Reforma Tributária EC 132/2023)
-- IBS = substitui ICMS + ISS  |  CBS = substitui PIS + COFINS  |  IS = Imposto Seletivo
-- Estrutura preparada para convivência (2026-2032) e regime pleno (2033+).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE invoice_items ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  -- CBS (federal — substitui PIS/COFINS)
  add_col('cbs_cst',       'VARCHAR2(2)');
  add_col('cbs_aliquota',  'NUMBER(6,4)');
  add_col('cbs_base',      'NUMBER(15,2)');
  add_col('cbs_value',     'NUMBER(15,2)');

  -- IBS (dual — substitui ICMS estadual + ISS municipal)
  add_col('ibs_cst',           'VARCHAR2(2)');
  add_col('ibs_aliquota_uf',   'NUMBER(6,4)');
  add_col('ibs_aliquota_mun',  'NUMBER(6,4)');
  add_col('ibs_base',          'NUMBER(15,2)');
  add_col('ibs_value',         'NUMBER(15,2)');

  -- IS (Imposto Seletivo — produtos prejudiciais à saúde e ao meio ambiente)
  add_col('is_value',      'NUMBER(15,2)');

  DBMS_OUTPUT.PUT_LINE('Colunas IBS/CBS/IS adicionadas a invoice_items.');
END;
/

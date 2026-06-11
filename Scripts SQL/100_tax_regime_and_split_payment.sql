-- Migration 100: tax_regime_mode em cmig_fiscal_config + split_payment em orders
-- Fase 2: prepara estrutura para coexistência tributária e Split Payment.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_table VARCHAR2, p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE ' || p_table || ' ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  -- cmig_fiscal_config: modo de regime tributário
  add_col('cmig_fiscal_config', 'tax_regime_mode',
          'VARCHAR2(12) DEFAULT ''legacy'' NOT NULL');

  -- CHECK constraint (adiciona apenas se não existir)
  BEGIN
    EXECUTE IMMEDIATE q'[
      ALTER TABLE cmig_fiscal_config
        ADD CONSTRAINT chk_tax_regime_mode
        CHECK (tax_regime_mode IN ('legacy', 'transition', 'reform'))
    ]';
  EXCEPTION WHEN OTHERS THEN NULL;
  END;

  -- orders: split payment (retenção automática na origem — plataformas 2027+)
  add_col('orders', 'split_payment_amount', 'NUMBER(15,2)');
  add_col('orders', 'split_payment_ref',    'VARCHAR2(100)');
  add_col('orders', 'split_payment_date',   'TIMESTAMP');

  DBMS_OUTPUT.PUT_LINE('Colunas tax_regime_mode e split_payment adicionadas.');
END;
/

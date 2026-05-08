-- Migration 49: Suporte a CPF na CMIG
-- Permite cadastro de Pessoa Física (CPF + Nome) antes de ter CNPJ/Razão Social.
-- CNPJ e company_name se tornam opcionais; CPF é novo campo único.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmigs ADD (cpf VARCHAR2(14))';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_const_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_const_exists, -02264);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmigs ADD CONSTRAINT uq_cmig_cpf UNIQUE (cpf)';
EXCEPTION
  WHEN e_const_exists THEN NULL;
END;
/

-- Tornar cnpj nullable (era NOT NULL)
DECLARE
  v_nullable VARCHAR2(1);
BEGIN
  SELECT nullable INTO v_nullable
  FROM user_tab_columns
  WHERE table_name = 'CMIGS' AND column_name = 'CNPJ';
  IF v_nullable = 'N' THEN
    EXECUTE IMMEDIATE 'ALTER TABLE cmigs MODIFY (cnpj VARCHAR2(18) NULL)';
  END IF;
END;
/

-- Tornar company_name nullable (era NOT NULL)
DECLARE
  v_nullable VARCHAR2(1);
BEGIN
  SELECT nullable INTO v_nullable
  FROM user_tab_columns
  WHERE table_name = 'CMIGS' AND column_name = 'COMPANY_NAME';
  IF v_nullable = 'N' THEN
    EXECUTE IMMEDIATE 'ALTER TABLE cmigs MODIFY (company_name VARCHAR2(255) NULL)';
  END IF;
END;
/


COMMIT;
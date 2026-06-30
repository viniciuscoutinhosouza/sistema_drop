-- Migration 115: Config de emissão própria de NF-e (SEFAZ direto) por CMIG.
-- Substitui o Focus na emissão MANUAL: certificado A1 local, senha CIFRADA no
-- banco (master key Fernet — nunca a senha em claro), série manual configurável
-- (separada das séries do Faturador ML), liberação de produção faseada e controle
-- de NSU da Distribuição de DFe. Aditiva, nullable e idempotente (ORA-01430).
-- As colunas focus_* permanecem (legacy) — não dropar.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE cmig_fiscal_config ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  -- Certificado A1 local + senha cifrada (cofre próprio, não mais o Focus)
  add_col('cert_path',            'VARCHAR2(255)');   -- caminho do .pfx no servidor (fora de static/)
  add_col('cert_pass_encrypted',  'VARCHAR2(512)');   -- senha do .pfx CIFRADA (Fernet) — nunca em claro
  -- Go-live faseado por empresa: só emite em produção quando = 1
  add_col('production_released',  'NUMBER(1) DEFAULT 0 NOT NULL');
  -- Série específica configurável para a emissão MANUAL via SEFAZ (separada do marketplace).
  -- Numeração desdobrada por ambiente para não queimar números de produção em testes.
  add_col('manual_nfe_serie',                 'NUMBER(3)');
  add_col('manual_nfe_next_number',           'NUMBER(9) DEFAULT 1 NOT NULL');
  add_col('manual_nfe_next_number_homolog',   'NUMBER(9) DEFAULT 1 NOT NULL');
  -- FECP (ex.: RJ 2%) — aplicado por produto conforme lista do RICMS, não em todo CSOSN 102.
  add_col('aliquota_fecp',        'NUMBER(5,2) DEFAULT 0 NOT NULL');
  -- Distribuição de DFe (Ambiente Nacional): último NSU processado por CNPJ.
  add_col('ultimo_nsu',           'VARCHAR2(20) DEFAULT ''0'' NOT NULL');
  DBMS_OUTPUT.PUT_LINE('Colunas de emissao SEFAZ propria adicionadas a cmig_fiscal_config.');
END;
/

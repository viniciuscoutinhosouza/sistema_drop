-- Migration 147: codificação tributária POR PRODUTO (+ defaults na CMIG).
--
-- Fundação da "codificação tributária por produto com default na CMIG" (Estágio 1):
--   * cmig_products / catalog_products ganham 16 campos fiscais, TODOS NULLABLE.
--     NULL = usar o default da CMIG (o produto SOBRESCREVE; a CMIG expõe o padrão).
--   * cmig_fiscal_config ganha 12 default_* (os padrões herdados quando o produto está vazio).
--   * invoice_items.ibs_cst / cbs_cst alargados de VARCHAR2(2) → VARCHAR2(3) (CST do CBS/IBS = 3 díg).
--
-- NÃO recria csosn/origin/cest/ncm (já existem e são reusados). NÃO toca o EMISSOR (estágio 2).
-- Idempotente: cada ADD ignora ORA-01430 (coluna já existe); cada MODIFY é no-op se já estiver igual.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_ddl VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_ddl;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;

  PROCEDURE modify_col(p_ddl VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_ddl;
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLCODE IN (-1430, -1442, -1451, -1735) THEN NULL; ELSE RAISE; END IF;
  END;

  PROCEDURE add_fiscal_cols(p_table VARCHAR2) IS
  BEGIN
    add_col('ALTER TABLE '||p_table||' ADD (cfop VARCHAR2(4))');
    add_col('ALTER TABLE '||p_table||' ADD (icms_cst VARCHAR2(2))');
    add_col('ALTER TABLE '||p_table||' ADD (icms_aliquota NUMBER(5,2))');
    add_col('ALTER TABLE '||p_table||' ADD (icms_reducao_bc NUMBER(5,2))');
    add_col('ALTER TABLE '||p_table||' ADD (fcp_aliquota NUMBER(5,2))');
    add_col('ALTER TABLE '||p_table||' ADD (pis_cst VARCHAR2(2))');
    add_col('ALTER TABLE '||p_table||' ADD (cofins_cst VARCHAR2(2))');
    add_col('ALTER TABLE '||p_table||' ADD (pis_aliquota NUMBER(7,4))');
    add_col('ALTER TABLE '||p_table||' ADD (cofins_aliquota NUMBER(7,4))');
    add_col('ALTER TABLE '||p_table||' ADD (ipi_cst VARCHAR2(2))');
    add_col('ALTER TABLE '||p_table||' ADD (ipi_aliquota NUMBER(7,4))');
    add_col('ALTER TABLE '||p_table||' ADD (ipi_cenq VARCHAR2(3))');
    add_col('ALTER TABLE '||p_table||' ADD (ibscbs_cst VARCHAR2(3))');
    add_col('ALTER TABLE '||p_table||' ADD (cclasstrib VARCHAR2(6))');
    add_col('ALTER TABLE '||p_table||' ADD (cbenef VARCHAR2(10))');
    add_col('ALTER TABLE '||p_table||' ADD (mot_des_icms VARCHAR2(2))');
  END;
BEGIN
  -- Campos fiscais por produto (CMIG e PG)
  add_fiscal_cols('cmig_products');
  add_fiscal_cols('catalog_products');

  -- Defaults na config fiscal da CMIG
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_cfop VARCHAR2(4))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_csosn VARCHAR2(3))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_icms_cst VARCHAR2(2))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_icms_aliquota NUMBER(5,2))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_pis_cst VARCHAR2(2))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_cofins_cst VARCHAR2(2))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_pis_aliquota NUMBER(7,4))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_cofins_aliquota NUMBER(7,4))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_ipi_cst VARCHAR2(2))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_ibscbs_cst VARCHAR2(3))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_cclasstrib VARCHAR2(6))');
  add_col('ALTER TABLE cmig_fiscal_config ADD (default_origin NUMBER(1))');

  -- Alinha largura do CST de CBS/IBS no snapshot do item (2 → 3 dígitos)
  modify_col('ALTER TABLE invoice_items MODIFY (ibs_cst VARCHAR2(3))');
  modify_col('ALTER TABLE invoice_items MODIFY (cbs_cst VARCHAR2(3))');
END;
/

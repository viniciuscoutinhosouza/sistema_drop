-- Migration 148: colunas fiscais do snapshot no invoice_items (Regime Normal — CRT 3).
--
-- A migration 147 adicionou icms_reducao_bc / fcp_aliquota / mot_des_icms / cbenef / ipi_cenq aos
-- PRODUTOS (cmig_products/catalog_products) mas NÃO ao `invoice_items`. Sem essas colunas o
-- `apply_fiscal_snapshot` pula a gravação (hasattr=False) e o `sefaz_service._item` lê None →
-- NF-e de CST 20 sai com <pRedBC>0.00</pRedBC> (ICMS maior que o devido), FCP nunca destacado e
-- cBenef nunca emitido (RJ rejeita). Esta migration fecha o buraco: grava o SNAPSHOT fiscal no item.
--
-- `fcp_value` é o valor monetário do FCP gravado no item (hoje recomputado no builder a partir de
-- fcp_aliquota × base; aqui persiste o snapshot do total).
--
-- Idempotente: cada ADD ignora ORA-01430 (coluna já existe). Mesmo padrão da 147 (que JÁ foi
-- aplicada em produção — NÃO editar a 147).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_ddl VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_ddl;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE invoice_items ADD (icms_reducao_bc NUMBER(5,2))');
  add_col('ALTER TABLE invoice_items ADD (fcp_aliquota NUMBER(5,2))');
  add_col('ALTER TABLE invoice_items ADD (fcp_value NUMBER(15,2))');
  add_col('ALTER TABLE invoice_items ADD (mot_des_icms VARCHAR2(2))');
  add_col('ALTER TABLE invoice_items ADD (cbenef VARCHAR2(10))');
  add_col('ALTER TABLE invoice_items ADD (ipi_cenq VARCHAR2(3))');
END;
/

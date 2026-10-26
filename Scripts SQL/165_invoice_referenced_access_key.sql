-- 165_invoice_referenced_access_key.sql
-- ADR-0037 (devolução emitida): coluna para a CHAVE da NF-e de venda referenciada por uma
-- NF-e de DEVOLUÇÃO (finalidade=4). O emissor próprio (sefaz_service.build_nota_emissao) lê
-- este campo para montar <ide><NFref><refNFe> no XML — exigência fiscal da devolução.
-- (Na devolução import-driven, ADR-0009, a chave fica em returns.referenced_access_key; aqui é a
-- devolução que NÓS emitimos, então precisa estar no próprio Invoice.)
-- Idempotente (ORA-01430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE invoices ADD referenced_access_key VARCHAR2(50)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

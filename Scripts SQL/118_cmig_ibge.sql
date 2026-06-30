-- Migration 118: código IBGE do município da CMIG (emitente).
-- Obrigatório para a emissão própria de NF-e: compõe cMunFG da chave e o cMun do
-- enderEmit (7 dígitos). O destinatário (people) já tem ibge_code. A busca por CNPJ
-- (cnpj_lookup → BrasilAPI) já retorna o código; aqui só persistimos no emitente.
-- Aditiva, nullable, idempotente (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmigs ADD (ibge_code VARCHAR2(7))';
  DBMS_OUTPUT.PUT_LINE('Coluna cmigs.ibge_code adicionada.');
EXCEPTION
  WHEN e_col_exists THEN
    DBMS_OUTPUT.PUT_LINE('Coluna cmigs.ibge_code ja existe, continuando.');
END;
/

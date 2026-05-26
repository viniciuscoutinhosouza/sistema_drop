-- ============================================================
-- MIG ECOMMERCE – Script 71: CSOSN por produto (CMIG e PG)
-- ============================================================
-- Adiciona campo CSOSN (Código de Situação da Operação no Simples Nacional)
-- em cmig_products e catalog_products. Necessário para o Faturador do
-- Mercado Livre emitir NFe — o painel "Edite os dados fiscais do anúncio"
-- exige esse campo (ex: "102 - Tributada pelo Simples Nacional sem
-- permissão de crédito").
--
-- Scope: opcional por produto, com fallback derivado do CRT da CMIG
-- (CRT 1/2 → CSOSN 102; CRT 3 → CST 00, tratado em outro fluxo).
--
-- Idempotente: bloco DECLARE/EXCEPTION_INIT(-01430) ignora se a coluna
-- já existir.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD csosn VARCHAR2(3)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD csosn VARCHAR2(3)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

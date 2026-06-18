-- 101_full_mirror_flag.sql — marca os CMIGProdutos "espelho" do FULL (ADR-0010)
--
-- Espelho = CMIGProduto auto-criado pelo sistema só para segurar o estoque FULL de um
-- produto cujo anúncio é vinculado ao PG. Diferente de um produto CMIG real (vindo de
-- import de anúncio ou do fluxo CMIG→PG). A flag permite: (a) proteger o espelho de
-- exclusão/desativação (ele segura o FULL); (b) identificá-lo na UI.
--
-- Assinatura do espelho: tem pg_product_id, NÃO veio de anúncio (source_listing_id NULL)
-- e usa o SKU do PG como sku_cmig (resolve_full_cmig_product cria assim).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD is_full_mirror NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

UPDATE cmig_products cp
   SET cp.is_full_mirror = 1
 WHERE cp.source_listing_id IS NULL
   AND cp.pg_product_id IS NOT NULL
   AND EXISTS (
     SELECT 1 FROM catalog_products cat
      WHERE cat.id = cp.pg_product_id AND cat.sku = cp.sku_cmig
   );

COMMIT;

-- Migration 80: rastreabilidade de origem variacao em cmig_products
--
-- Quando 'Criar Produto CMIG' eh disparado de um anuncio ML com variacoes,
-- cada variacao (cor/tamanho/voltagem) vira UM CMIGProduct separado.
-- Estes 2 campos rastreiam de qual anuncio + qual variacao especifica veio,
-- para que o sistema marque na UI as variacoes ja importadas e nao deixe
-- importar a mesma variacao 2x.
--
-- source_listing_id:   FK product_listings.id (anuncio de origem)
-- source_variation_id: string com o `id` da variacao ML (ex: "175890123")
--
-- Indice composto para checagem rapida "esta variacao ja foi importada?"

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD source_listing_id NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD source_variation_id VARCHAR2(100)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_cmig_products_source_var ON cmig_products(source_listing_id, source_variation_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

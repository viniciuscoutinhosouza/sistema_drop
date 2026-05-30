-- Migration 78: variation_group_id + family_name_ml em product_listings
-- Suporte a "Anuncios com Variacoes" em categorias User Products do ML.
-- Em vez de criar 1 anuncio com array variations (rejeitado em User Products),
-- agrupa N anuncios ja publicados via mesma family_name no ML; o ML renderiza
-- como variacoes na VIP (pickers de cor/tamanho).
--
-- variation_group_id: UUID local que une listings irmaos (NULL = anuncio simples)
-- family_name_ml:     valor enviado ao ML no PUT /items/{id} { family_name: ... }

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD variation_group_id VARCHAR2(36)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD family_name_ml VARCHAR2(200)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_listings_variation_group ON product_listings(variation_group_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

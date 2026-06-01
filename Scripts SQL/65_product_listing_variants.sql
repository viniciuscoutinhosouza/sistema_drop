-- Migration 65: Cria product_listing_variants
-- Mapeia ml_variation_id (ML API) <-> catalog_product_variants (local)
-- por listing publicado. Permite sync de estoque por variação e
-- dedução correta ao processar pedidos com variation_id.
DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE product_listing_variants (
        id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        listing_id          NUMBER NOT NULL,
        catalog_variant_id  NUMBER,
        ml_variation_id     NUMBER,
        shopee_model_id     NUMBER,
        available_quantity  NUMBER DEFAULT 0 NOT NULL,
        price_override      NUMBER(15,2),
        created_at          TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT fk_plv_listing  FOREIGN KEY (listing_id)         REFERENCES product_listings(id)          ON DELETE CASCADE,
        CONSTRAINT fk_plv_variant  FOREIGN KEY (catalog_variant_id) REFERENCES catalog_product_variants(id),
        CONSTRAINT uq_plv_ml_var   UNIQUE (listing_id, ml_variation_id)
    )';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/
DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -01408);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_plv_listing ON product_listing_variants(listing_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/
DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -01408);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_plv_ml_var ON product_listing_variants(ml_variation_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

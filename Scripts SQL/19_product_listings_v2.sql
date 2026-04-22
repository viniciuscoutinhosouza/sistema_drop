-- Script 19: Product Listings v2
-- Permite listing sem product_id (desvinculado), adiciona FK para catalog_product_id
-- e garante unicidade de (account_id, platform_item_id)

-- 1. Permite listing sem product_id (desvinculado de DropshipperProduct)
ALTER TABLE product_listings MODIFY product_id NULL;

-- 2. Link direto a produto PG (CatalogProduct)
ALTER TABLE product_listings ADD catalog_product_id NUMBER;
ALTER TABLE product_listings ADD CONSTRAINT fk_pl_catalog
    FOREIGN KEY (catalog_product_id) REFERENCES catalog_products(id);

-- 3. Índice para busca por platform_item_id
CREATE INDEX idx_pl_platform_item ON product_listings(platform_item_id);

-- 4. Um item de plataforma só pode ter 1 listing por conta
ALTER TABLE product_listings ADD CONSTRAINT uq_pl_account_item
    UNIQUE (account_id, platform_item_id);

COMMIT;

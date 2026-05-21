-- 67_remove_variant_support.sql
-- Remove estruturas de banco adicionadas para suporte a produto variante.
-- Idempotente: verifica existência antes de cada operação.

-- 1. Drop product_listing_variants (tabela inteira)
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'PRODUCT_LISTING_VARIANTS';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'DROP TABLE product_listing_variants CASCADE CONSTRAINTS';
  END IF;
END;
/

-- 2. Drop ml_variation_id de order_items
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_tab_columns
  WHERE table_name = 'ORDER_ITEMS' AND column_name = 'ML_VARIATION_ID';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE order_items DROP COLUMN ml_variation_id';
  END IF;
END;
/

-- 3. Drop product_type de catalog_products
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_tab_columns
  WHERE table_name = 'CATALOG_PRODUCTS' AND column_name = 'PRODUCT_TYPE';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE catalog_products DROP COLUMN product_type';
  END IF;
END;
/

COMMIT;

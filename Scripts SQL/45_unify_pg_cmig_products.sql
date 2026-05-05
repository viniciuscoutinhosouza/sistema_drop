-- Migration 45: Unificar schema entre catalog_products (PG) e cmig_products (CMIG)
-- - Renomeia cmig_products.sale_price -> suggested_price (e em cmig_product_variants)
-- - Adiciona cmig_products.category_id (FK -> categories), migra dados de category_name e dropa a coluna antiga
-- - Adiciona catalog_products.video_id e catalog_products.attributes_json
-- - Mantem cmig_products.pictures_json (apenas para fallback de leitura legada)
-- Idempotente: pode ser re-executada sem erro.

-- ============================================================
-- 1) cmig_products: RENAME sale_price -> suggested_price
-- ============================================================
DECLARE
    v_has_new INT;
    v_has_old INT;
BEGIN
    SELECT COUNT(*) INTO v_has_new FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'CMIG_PRODUCTS' AND COLUMN_NAME = 'SUGGESTED_PRICE';
    SELECT COUNT(*) INTO v_has_old FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'CMIG_PRODUCTS' AND COLUMN_NAME = 'SALE_PRICE';
    IF v_has_new = 0 AND v_has_old = 1 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE cmig_products RENAME COLUMN sale_price TO suggested_price';
    ELSIF v_has_new = 0 AND v_has_old = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD suggested_price NUMBER(15,2)';
    END IF;
END;
/

-- ============================================================
-- 2) cmig_product_variants: RENAME sale_price -> suggested_price
-- ============================================================
DECLARE
    v_has_new INT;
    v_has_old INT;
BEGIN
    SELECT COUNT(*) INTO v_has_new FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'CMIG_PRODUCT_VARIANTS' AND COLUMN_NAME = 'SUGGESTED_PRICE';
    SELECT COUNT(*) INTO v_has_old FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'CMIG_PRODUCT_VARIANTS' AND COLUMN_NAME = 'SALE_PRICE';
    IF v_has_new = 0 AND v_has_old = 1 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE cmig_product_variants RENAME COLUMN sale_price TO suggested_price';
    ELSIF v_has_new = 0 AND v_has_old = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE cmig_product_variants ADD suggested_price NUMBER(15,2)';
    END IF;
END;
/

-- ============================================================
-- 3) cmig_products: ADD category_id NUMBER
-- ============================================================
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD category_id NUMBER';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

-- 3a) FK constraint para categories
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM USER_CONSTRAINTS
     WHERE CONSTRAINT_NAME = 'FK_CMIGPROD_CATEGORY';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE cmig_products ADD CONSTRAINT fk_cmigprod_category '
                       || 'FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL';
    END IF;
END;
/

-- 3b) Migrar dados de category_name -> category_id (apenas se a coluna antiga existir)
DECLARE
    v_has_old INT;
BEGIN
    SELECT COUNT(*) INTO v_has_old FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'CMIG_PRODUCTS' AND COLUMN_NAME = 'CATEGORY_NAME';
    IF v_has_old = 1 THEN
        FOR rec IN (
            SELECT DISTINCT TRIM(category_name) AS cname
              FROM cmig_products
             WHERE category_name IS NOT NULL
               AND TRIM(category_name) IS NOT NULL
               AND category_id IS NULL
        ) LOOP
            DECLARE
                v_cat_id NUMBER;
            BEGIN
                BEGIN
                    SELECT id INTO v_cat_id FROM categories
                     WHERE LOWER(name) = LOWER(rec.cname) AND parent_id IS NULL
                     FETCH FIRST 1 ROWS ONLY;
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN
                        INSERT INTO categories(name, parent_id) VALUES (rec.cname, NULL)
                        RETURNING id INTO v_cat_id;
                END;
                UPDATE cmig_products
                   SET category_id = v_cat_id
                 WHERE TRIM(category_name) = rec.cname
                   AND category_id IS NULL;
            END;
        END LOOP;
    END IF;
END;
/

-- 3c) DROP coluna category_name (idempotente)
DECLARE
    v_has_old INT;
BEGIN
    SELECT COUNT(*) INTO v_has_old FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'CMIG_PRODUCTS' AND COLUMN_NAME = 'CATEGORY_NAME';
    IF v_has_old = 1 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE cmig_products DROP COLUMN category_name';
    END IF;
END;
/

-- 3d) Index em category_id
DECLARE
    e_idx_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_cmigprod_category ON cmig_products(category_id)';
EXCEPTION
    WHEN e_idx_exists THEN NULL;
END;
/

-- ============================================================
-- 4) catalog_products: ADD video_id
-- ============================================================
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD video_id VARCHAR2(100)';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

-- ============================================================
-- 5) catalog_products: ADD attributes_json (CLOB)
-- ============================================================
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE catalog_products ADD attributes_json CLOB';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

-- ============================================================
-- 6) catalog_product_variants: ADD suggested_price (simetria com CMIG)
-- ============================================================
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE catalog_product_variants ADD suggested_price NUMBER(15,2)';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

-- Migration 52: distinção real de modalidade de envio + reputação do vendedor
-- - product_listings.logistic_type (substitui o boolean is_full): cross_docking | drop_off | xd_drop_off | self_service | fulfillment
-- - marketplace_accounts.power_seller_status (Mercado Líder: platinum/gold/silver) e level_id (termômetro 1_red ... 5_green)
-- - marketplace_accounts.reputation_cached_at para TTL do cache de reputação
-- Idempotente. Mantém is_full por compatibilidade (deprecated, drop em migration futura).

-- 1) product_listings.logistic_type
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD logistic_type VARCHAR2(30)';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

-- 1a) Backfill: is_full=1 -> fulfillment ; is_full=0 -> cross_docking (default seguro)
UPDATE product_listings
   SET logistic_type = CASE WHEN NVL(is_full, 0) = 1 THEN 'fulfillment' ELSE 'cross_docking' END
 WHERE logistic_type IS NULL;
COMMIT;

-- 1b) Index para filtros por logistic_type
DECLARE
    e_idx_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_pl_logistic_type ON product_listings(logistic_type)';
EXCEPTION
    WHEN e_idx_exists THEN NULL;
END;
/

-- 2) marketplace_accounts.power_seller_status
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD power_seller_status VARCHAR2(20)';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

-- 3) marketplace_accounts.level_id
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD level_id VARCHAR2(20)';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

-- 4) marketplace_accounts.reputation_cached_at
DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD reputation_cached_at TIMESTAMP WITH TIME ZONE';
EXCEPTION
    WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

-- Migration 32: Add ml_item_id to order_items
-- Stores the ML item ID (e.g. MLB123456) to enable ProductListing lookup
-- for items where seller_sku was empty in the ML order response

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_items ADD ml_item_id VARCHAR2(200)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

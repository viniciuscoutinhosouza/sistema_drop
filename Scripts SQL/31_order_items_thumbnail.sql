-- Migration 31: Add thumbnail_url to order_items
-- Stores the product thumbnail URL from the marketplace order response

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_items ADD thumbnail_url VARCHAR2(1000)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

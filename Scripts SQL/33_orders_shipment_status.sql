-- Migration 33: Add shipment_status to orders
-- Stores the ML shipment status (shipped, handling, ready_to_ship, delivered, etc.)
-- independently from the internal order status stepper

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD shipment_status VARCHAR2(50)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

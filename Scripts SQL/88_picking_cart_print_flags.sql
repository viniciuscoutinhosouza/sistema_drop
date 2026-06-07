-- 88_picking_cart_print_flags.sql
-- Rastreio de impressão de etiqueta e NF-e por pedido na gaiola (Separação Fase 2).
-- Idempotente: exceção -1430 = coluna já existe.

DECLARE e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE picking_cart_orders ADD label_printed_at TIMESTAMP WITH TIME ZONE';
EXCEPTION WHEN e_exists THEN NULL; END;
/
DECLARE e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE picking_cart_orders ADD label_printed_by NUMBER';
EXCEPTION WHEN e_exists THEN NULL; END;
/
DECLARE e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE picking_cart_orders ADD nfe_printed_at TIMESTAMP WITH TIME ZONE';
EXCEPTION WHEN e_exists THEN NULL; END;
/
DECLARE e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE picking_cart_orders ADD nfe_printed_by NUMBER';
EXCEPTION WHEN e_exists THEN NULL; END;
/

SET SERVEROUTPUT ON
DECLARE v_n NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_n FROM user_tab_columns
   WHERE table_name = 'PICKING_CART_ORDERS'
     AND column_name IN ('LABEL_PRINTED_AT','LABEL_PRINTED_BY','NFE_PRINTED_AT','NFE_PRINTED_BY');
  DBMS_OUTPUT.PUT_LINE('picking_cart_orders print flags=' || v_n || ' (esperado 4)');
END;
/

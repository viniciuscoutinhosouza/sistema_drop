-- 186_cart_mode_scan_auto.sql
-- Adiciona 'scan_auto' (bipagem automática) ao CHECK de picking_carts.cart_mode.
--
-- Bug: a migration 85 criou `ck_cart_mode CHECK (cart_mode IN ('manual','scan'))`. O modo 'scan_auto'
-- foi adicionado depois no código (backend create_cart + front "Bipagem automática"), mas a constraint
-- barrava o INSERT -> ORA-02290 (check constraint violated) ao criar a gaiola. Recria o CHECK com os
-- 3 modos. Idempotente.

DECLARE
  e_not_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_not_exists, -2443);  -- ORA-02443: constraint inexistente
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_carts DROP CONSTRAINT ck_cart_mode';
EXCEPTION
  WHEN e_not_exists THEN NULL;
END;
/

DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -2264);  -- ORA-02264: nome de constraint já em uso
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_carts ADD CONSTRAINT ck_cart_mode
    CHECK (cart_mode IN (''manual'', ''scan'', ''scan_auto''))';
EXCEPTION
  WHEN e_exists THEN NULL;
END;
/

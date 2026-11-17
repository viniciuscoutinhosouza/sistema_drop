-- 187_cart_public_token.sql
-- Link externo da gaiola (molde do checkout público, ADR-0033 `orders.public_token`): token de acesso
-- PÚBLICO (sem login) a UMA gaiola específica — para um galpão que despacha mas não tem acesso ao
-- sistema. Gerado sob demanda e revogável. Índice único (NULL não é indexado → vários sem token OK).
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);  -- ORA-01430: coluna já existe
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_carts ADD public_token VARCHAR2(64)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);  -- ORA-00955: nome já em uso
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_cart_public_token ON picking_carts (public_token)';
EXCEPTION
  WHEN e_exists THEN NULL;
END;
/

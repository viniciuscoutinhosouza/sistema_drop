-- 166_picking_separation_photos.sql
-- Separação com FOTOS (webcam): a etapa "Separado" passa a exigir foto(s) tiradas na separação.
-- Guarda as URLs (JSON array, em static/uploads) por pedido-na-gaiola.
-- Idempotente (ORA-01430 coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_cart_orders ADD separation_photos_json CLOB';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

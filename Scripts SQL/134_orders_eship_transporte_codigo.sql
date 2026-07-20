-- Migration 134: selo de idempotência do TRANSPORTE do eShip em orders.
--
-- Guarda o `codigoTransporte` gravado na ordem do eShip (ex.: "01" = Correios). Serve como selo
-- para NÃO reenviar o PutOrdem de transporte a cada ciclo de sync (o scheduler roda a cada 15min).
-- Nulo = transporte ainda não definido no WMS para este pedido.
--
-- Idempotente: ORA-01430 (coluna já existe) é ignorado.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (eship_transporte_codigo VARCHAR2(10))';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

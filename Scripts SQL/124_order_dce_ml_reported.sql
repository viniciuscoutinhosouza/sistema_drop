-- 124: marcador de idempotência do envio da DC-e ao Mercado Livre (POST invoice_data).
-- Evita reenviar o documento fiscal a cada clique na etiqueta enquanto o ML processa.
-- Idempotente (ORA-01430 = coluna já existe).
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_dce ADD (ml_reported_at TIMESTAMP WITH TIME ZONE)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

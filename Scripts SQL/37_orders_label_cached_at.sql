-- 37_orders_label_cached_at.sql
-- Adiciona coluna para rastrear quando a etiqueta de envio do ML foi salva localmente.
-- Idempotente.

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    BEGIN
        EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (label_cached_at TIMESTAMP WITH TIME ZONE)';
    EXCEPTION
        WHEN e_col_exists THEN NULL;
    END;
END;
/
COMMIT;

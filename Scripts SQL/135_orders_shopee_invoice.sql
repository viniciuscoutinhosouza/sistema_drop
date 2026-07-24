-- 135_orders_shopee_invoice.sql
-- Estado do anexo da NF-e no pedido Shopee (Fase 3 — fiscal).
--
-- Contexto: no BR a Shopee exige que a nota seja ANEXADA (order/upload_invoice_doc) e VALIDADA
-- contra a SEFAZ antes de expedir (ship_order). O Drop emite a NF-e própria (SEFAZ) e anexa.
-- Guardamos o estado do anexo por pedido:
--   None|pending  = comprador pediu nota, ainda não anexada
--   uploaded      = documento enviado à Shopee (validação SEFAZ é assíncrona)
--   validated     = Shopee validou (invoice_data preenchido no get_order_detail)
--   rejected      = SEFAZ/Shopee recusou (reenvio permitido)
--
-- Idempotente: EXCEPTION WHEN e_col_exists (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);   -- ORA-01430: column already exists

  PROCEDURE add_col(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE orders ADD (shopee_invoice_status VARCHAR2(20))');
  add_col('ALTER TABLE orders ADD (shopee_invoice_uploaded_at TIMESTAMP(6) WITH TIME ZONE)');
  COMMIT;
END;
/

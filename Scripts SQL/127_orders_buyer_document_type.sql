-- 127_orders_buyer_document_type.sql
-- Documento fiscal do comprador: guardar o TIPO (CPF|CNPJ) informado pelo Mercado Livre.
--
-- Contexto: o ML removeu `buyer.identification` da resposta de GET /orders/{id} (privacidade) —
-- por isso `orders.buyer_document` nascia NULO em 100% dos pedidos, e a ordem enviada ao WMS
-- (eShip) ia sem `cpfDestinatario`/`cnpjDestinatario`, que são obrigatórios. O documento passa a
-- ser buscado em GET /orders/{id}/billing_info (x-version: 2), que devolve
-- `identification.{type, number}`. Guardamos o `type` para escolher CPF vs CNPJ pela FONTE, e não
-- pelo comprimento da string (um CPF com zero à esquerda perdido viraria "CNPJ" por engano).
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
  add_col('ALTER TABLE orders ADD (buyer_document_type VARCHAR2(10))');   -- 'CPF' | 'CNPJ'
  COMMIT;
END;
/

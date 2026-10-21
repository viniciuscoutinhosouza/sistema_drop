-- 154_manual_order_public_checkout.sql
-- Fase 3 (ADR-0033): checkout público da venda manual por token + re-análise de desconto.
--  (a) orders.public_token: token opaco (secrets.token_urlsafe) que dá ao cliente acesso
--      SEM login à página de checkout do próprio pedido (escopo estrito a esse pedido).
--  (b) orders.public_token_created_at: quando o link foi gerado (auditoria/expiração futura).
--  (c) orders.needs_price_review: 0|1 — o cliente mexeu em item com desconto; o operador
--      precisa re-analisar o preço antes de liberar o pagamento ("falhar alto").
--  (d) order_items.list_price: snapshot do preço de referência (suggested_price) na venda,
--      para detectar desconto de forma estável (preço do produto muda com o tempo).
-- Idempotente (ORA-01430 coluna / ORA-00955 objeto).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (public_token VARCHAR2(64))';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (public_token_created_at TIMESTAMP WITH TIME ZONE)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (needs_price_review NUMBER(1) DEFAULT 0 NOT NULL)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE order_items ADD (list_price NUMBER(15,2))';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

-- Índice único no token (buscamos o pedido pelo token no endpoint público).
-- ORA-00955 objeto já existe; ORA-01452 linhas duplicadas (NULLs não contam no índice único Oracle).
DECLARE
  e_obj_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_obj_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_orders_public_token ON orders (public_token)';
EXCEPTION
  WHEN e_obj_exists THEN NULL;
END;
/

-- Migration 57: Adiciona orders.nfe_invoices_json (CLOB) — cache da lista
-- completa de NF-e do Faturador ML de um pedido (nota de venda + notas de
-- referência, como Retorno Simbólico de pedidos Full). Populado quando o
-- modal de NF-e do pedido é consultado.
-- Idempotente.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD nfe_invoices_json CLOB';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

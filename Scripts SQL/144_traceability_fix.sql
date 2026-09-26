-- Migration 144: correções de schema da rastreabilidade (ADR-0027), pós-auditoria da Fase 1.
-- Forward-only: corrige a 143 já aplicada, sem reescrevê-la. Idempotente.
--
--   [HIGH] uq_sla_serial(serial_id) sozinho impedia RE-VENDA de serial devolvido → troca para
--          (order_id, serial_id): permite o mesmo serial em pedidos diferentes ao longo do tempo,
--          mas único por pedido.
--   [MEDIUM] uq_sla_item_lot(order_item_id, lot_id): no Oracle NULLs são distintos → não protegia
--          idempotência quando order_item_id é NULL (webhook/manual/FEFO server-side). Troca para
--          (order_id, product_type, product_id, lot_id) — sempre preenchido para alocação de lote.
--   [MEDIUM] product_serials.status VARCHAR2(12) não cabe 'awaiting_return'/'pending_validation' →
--          amplia para VARCHAR2(20) (paridade com o vocabulário de baldes de stock_lot_allocations).
--
-- Idempotente: ORA-01418 (índice não existe) no DROP; ORA-00955 (objeto já existe) no CREATE.

-- 1. Ampliar product_serials.status para 20 (widening é seguro; re-run não falha).
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_serials MODIFY (status VARCHAR2(20))';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

-- 2. Trocar o índice de idempotência de lote: order_item_id (nullable) → chave sempre preenchida.
DECLARE
  e_idx_missing EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_missing, -1418);
BEGIN
  EXECUTE IMMEDIATE 'DROP INDEX uq_sla_item_lot';
EXCEPTION
  WHEN e_idx_missing THEN NULL;
END;
/

DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_sla_order_lot ON stock_lot_allocations
    (order_id, product_type, product_id, lot_id)';
EXCEPTION
  WHEN e_exists THEN NULL;
END;
/

-- 3. Trocar a unicidade do serial: serial_id (vitalício) → (order_id, serial_id) (permite re-venda).
DECLARE
  e_idx_missing EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_missing, -1418);
BEGIN
  EXECUTE IMMEDIATE 'DROP INDEX uq_sla_serial';
EXCEPTION
  WHEN e_idx_missing THEN NULL;
END;
/

DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_sla_order_serial ON stock_lot_allocations
    (order_id, serial_id)';
EXCEPTION
  WHEN e_exists THEN NULL;
END;
/

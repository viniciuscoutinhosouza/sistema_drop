-- 185_fix_uq_sla_serial.sql
-- Corrige o índice uq_sla_order_serial para NÃO bloquear múltiplas alocações de LOTE no mesmo pedido.
--
-- Bug (confirmado ao vivo): o índice UNIQUE (order_id, serial_id) foi criado na migration 144 para
-- impedir o mesmo SERIAL repetido num pedido. Mas alocação de LOTE tem serial_id = NULL, e o Oracle
-- COLIDE duas linhas (order_id não-nulo, serial_id NULL) nesse índice composto (a chave não é
-- toda-nula → é indexada). Resultado: pedido de KIT (2+ componentes → 2+ alocações de lote por
-- pedido) estourava ORA-00001 na 2ª alocação e a emissão de NF-e caía (PendingRollbackError).
--
-- Correção: índice PARCIAL via expressão CASE. Para linha de LOTE (serial_id NULL) a 1ª coluna vira
-- NULL também → a chave fica TODA-nula → o Oracle NÃO a indexa → sem restrição. Para linha de SERIAL
-- (serial_id NOT NULL) a chave vira (order_id, serial_id) → dedupe de serial por pedido preservada.
-- Sem backfill (só troca de índice).

DECLARE
  e_idx_missing EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_missing, -1418);  -- ORA-01418: índice não existe
BEGIN
  EXECUTE IMMEDIATE 'DROP INDEX uq_sla_order_serial';
EXCEPTION
  WHEN e_idx_missing THEN NULL;
END;
/

DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);  -- ORA-00955: nome já em uso
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_sla_order_serial ON stock_lot_allocations
    (CASE WHEN serial_id IS NOT NULL THEN order_id END, serial_id)';
EXCEPTION
  WHEN e_exists THEN NULL;
END;
/

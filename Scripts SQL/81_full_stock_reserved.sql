-- Fase 1 — Reserva FULL.
-- Adiciona reserved_qty em full_stock pra modelar a janela "venda baixada → shipped".
-- Quando uma venda FULL é baixada, debita reserved_qty; quando shipped, libera reserved
-- e debita qty (estoque físico FULL).
-- Disponível FULL = max(0, qty - reserved_qty).
-- Idempotente: ignora erro de coluna já existente (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE full_stock ADD reserved_qty NUMBER DEFAULT 0 NOT NULL';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

-- Backfill: reset reserved_qty para 0 em linhas existentes (deveria já estar 0 pelo DEFAULT,
-- mas garantimos consistência caso a migração rode em DB que já tinha a coluna sem default).
UPDATE full_stock SET reserved_qty = 0 WHERE reserved_qty IS NULL;
COMMIT;

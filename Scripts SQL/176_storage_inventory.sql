-- Migration 176: Inventário por endereço — Endereçamento Fase 3a (ADR-0039).
-- (1) expande o CHECK de product_allocation_movements.reason p/ incluir 'adjust' (contagem física
--     corrige o qty_units da alocação SEM tocar o saldo escalar — ADR-0004 intocado);
-- (2) storage_locations ganha last_counted_at / last_counted_by (dirige o ciclo de contagem:
--     folhas por nunca/mais-antigo contado).
-- Idempotente: cada DDL em bloco próprio tratando ORA-02443 (constraint não existe no drop),
-- ORA-02264/ORA-00955 (nome já usado no recreate) e ORA-01430 (coluna já existe).

-- ── reason += 'adjust' (Oracle não altera CHECK in-place → DROP + ADD) ────────
DECLARE e_no_con EXCEPTION; PRAGMA EXCEPTION_INIT(e_no_con, -2443);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE product_allocation_movements DROP CONSTRAINT ck_palloc_mov_reason';
EXCEPTION WHEN e_no_con THEN NULL; END;
/

DECLARE
  e_dup EXCEPTION; PRAGMA EXCEPTION_INIT(e_dup, -2264);   -- nome já usado por constraint existente
  e_obj EXCEPTION; PRAGMA EXCEPTION_INIT(e_obj, -955);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_allocation_movements ADD CONSTRAINT ck_palloc_mov_reason
                     CHECK (reason IN (''dispatch'',''return'',''adjust''))';
EXCEPTION WHEN e_dup THEN NULL; WHEN e_obj THEN NULL; END;
/

-- ── storage_locations: carimbo do ciclo de contagem ──────────────────────────
DECLARE e_col EXCEPTION; PRAGMA EXCEPTION_INIT(e_col, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE storage_locations ADD last_counted_at TIMESTAMP WITH TIME ZONE';
EXCEPTION WHEN e_col THEN NULL; END;
/

DECLARE e_col EXCEPTION; PRAGMA EXCEPTION_INIT(e_col, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE storage_locations ADD last_counted_by NUMBER REFERENCES users(id)';
EXCEPTION WHEN e_col THEN NULL; END;
/

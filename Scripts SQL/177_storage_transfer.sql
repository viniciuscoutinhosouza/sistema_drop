-- Migration 177: Transferência entre endereços — Endereçamento Fase 3b (ADR-0039).
-- Expande o CHECK de product_allocation_movements.reason p/ incluir 'transfer_out'/'transfer_in'
-- (transferência INTERNA: muda só o local; Σ qty_units do produto NÃO muda; out(−N)+in(+N)=0 —
-- net-zero intra-galpão; NUNCA toca o saldo escalar — ADR-0004). Oracle não altera CHECK in-place →
-- DROP + ADD. O CHECK recriado lista os CINCO valores (Oracle substitui o CHECK inteiro).
-- Idempotente: ORA-02443 (drop sem constraint), ORA-02264/ORA-00955 (add com nome já usado).

DECLARE e_no_con EXCEPTION; PRAGMA EXCEPTION_INIT(e_no_con, -2443);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE product_allocation_movements DROP CONSTRAINT ck_palloc_mov_reason';
EXCEPTION WHEN e_no_con THEN NULL; END;
/

DECLARE
  e_dup EXCEPTION; PRAGMA EXCEPTION_INIT(e_dup, -2264);
  e_obj EXCEPTION; PRAGMA EXCEPTION_INIT(e_obj, -955);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_allocation_movements ADD CONSTRAINT ck_palloc_mov_reason
                     CHECK (reason IN (''dispatch'',''return'',''adjust'',''transfer_out'',''transfer_in''))';
EXCEPTION WHEN e_dup THEN NULL; WHEN e_obj THEN NULL; END;
/

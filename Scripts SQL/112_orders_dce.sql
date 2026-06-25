-- Migration 112: suporte a DC-e (Declaração de Conteúdo Eletrônica) em orders
-- Contas pessoa física (CPF) não emitem NF-e — o ML aguarda a DC-e. Adiciona:
--   dce_status — estado da emissão da DC-e (paralelo ao nfe_status)
--   pack_id    — id do pack/carrinho do ML (dedup da DC-e por envio: pedidos de
--                carrinho compartilham o mesmo shipment/pack)
-- Idempotente via EXCEPTION WHEN e_col_exists.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('dce_status', 'VARCHAR2(30)');
  add_col('pack_id',    'VARCHAR2(50)');
  DBMS_OUTPUT.PUT_LINE('Colunas dce_status e pack_id adicionadas a orders.');
END;
/

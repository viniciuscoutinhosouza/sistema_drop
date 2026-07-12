-- 126_orders_eship_ordem.sql
-- eShip: guardar a resposta bruta do webServicePostOrdem e o instante do claim de envio.
--
-- Contexto (2 bugs que estas colunas ajudam a fechar):
--  1) O envio ficava PRESO em eship_dispatch_status='sending' quando a etapa da Ordem falhava
--     (o `return` dentro do try pulava o `except` que setaria 'failed'). Sem TTL, todo clique
--     seguinte era recusado com "envio já em andamento". `eship_dispatch_at` registra QUANDO o
--     claim foi feito, permitindo retomar um lock órfão (processo morto) após alguns minutos.
--  2) O id da ordem gravado era não-confiável (havia fallback para o número do pedido do ML).
--     `eship_last_response` guarda a RESPOSTA CRUA do WMS, para o usuário conferir/auditar a
--     ordem realmente criada.
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
  add_col('ALTER TABLE orders ADD (eship_last_response CLOB)');
  add_col('ALTER TABLE orders ADD (eship_dispatch_at TIMESTAMP WITH TIME ZONE)');
  COMMIT;
END;
/

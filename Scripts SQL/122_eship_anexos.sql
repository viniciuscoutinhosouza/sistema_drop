-- 122_eship_anexos.sql — Selos de anexo/estado do envio completo ao eShip (WMS)
--
-- O envio completo ao eShip (Ordem + NF-e XML + Etiqueta) é idempotente e tolerante a parcial.
-- Estas colunas em `orders` guardam o que já foi anexado (para o reenvio não duplicar) e o
-- estado observável do despacho. `eship_dispatch_attempts` é usado pela rotina automática (Fase 2).
--
-- Idempotente: EXCEPTION WHEN e_col_exists (coluna -1430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);    -- ORA-01430: column already exists

  PROCEDURE run(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  run('ALTER TABLE orders ADD (eship_nfe_attached      NUMBER(1) DEFAULT 0)');
  run('ALTER TABLE orders ADD (eship_label_attached    NUMBER(1) DEFAULT 0)');
  run('ALTER TABLE orders ADD (eship_dispatch_status   VARCHAR2(20))');
  run('ALTER TABLE orders ADD (eship_dispatch_error    VARCHAR2(500))');
  run('ALTER TABLE orders ADD (eship_dispatch_attempts NUMBER DEFAULT 0)');
END;
/

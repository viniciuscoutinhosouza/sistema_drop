-- Migration 100: Integração eShip (WMS) — config por galpão + vínculo do pedido.
-- Módulo isolado em BACKEND/integrations/eship/. Idempotente.

-- 1) Config do eShip por galpão (warehouse). Opt-in: is_active controla o uso.
DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE eship_config (
      id            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      warehouse_id  NUMBER NOT NULL,
      base_url      VARCHAR2(500),
      api_key       VARCHAR2(500),
      is_active     NUMBER(1) DEFAULT 0 CONSTRAINT chk_eship_active CHECK (is_active IN (0,1)),
      created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_eship_wh FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE,
      CONSTRAINT uq_eship_wh UNIQUE (warehouse_id)
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

-- 2) Vínculo do pedido com a ordem no eShip (id retornado pelo WMS).
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE orders ADD eship_order_id VARCHAR2(100)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

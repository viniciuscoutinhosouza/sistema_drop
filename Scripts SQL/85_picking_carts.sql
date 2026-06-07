-- 85_picking_carts.sql
-- Módulo de Separação (Operador Logístico / pedidos NÃO-FULL).
-- Cria: picking_carts (Carrinho Gaiola), picking_cart_orders (pedido↔gaiola),
--       picking_cart_items (progresso de bipagem — Processo 2).
--
-- NOTA: `mode` é palavra reservada no Oracle → coluna cart_mode.
-- Idempotente e auto-corretivo: clean slate só se picking_carts estiver VAZIA.

-- ── Clean slate guardado (só se picking_carts vazia ou inexistente) ────────────
DECLARE
  v_cnt     NUMBER := 0;
  e_noexist EXCEPTION; PRAGMA EXCEPTION_INIT(e_noexist, -942);
BEGIN
  BEGIN
    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM picking_carts' INTO v_cnt;
  EXCEPTION WHEN e_noexist THEN v_cnt := 0;
  END;
  IF v_cnt = 0 THEN
    BEGIN EXECUTE IMMEDIATE 'DROP TABLE picking_cart_items CASCADE CONSTRAINTS PURGE';
    EXCEPTION WHEN e_noexist THEN NULL; END;
    BEGIN EXECUTE IMMEDIATE 'DROP TABLE picking_cart_orders CASCADE CONSTRAINTS PURGE';
    EXCEPTION WHEN e_noexist THEN NULL; END;
    BEGIN EXECUTE IMMEDIATE 'DROP TABLE picking_carts CASCADE CONSTRAINTS PURGE';
    EXCEPTION WHEN e_noexist THEN NULL; END;
  END IF;
END;
/

-- ── Carrinho Gaiola (cabeçalho) — sem FKs externas inline ──────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE picking_carts (
      id            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cart_number   VARCHAR2(30)  NOT NULL,
      warehouse_id  NUMBER,
      cart_mode     VARCHAR2(10)  DEFAULT ''manual'' NOT NULL,
      status        VARCHAR2(15)  DEFAULT ''open'' NOT NULL,
      carrier_name  VARCHAR2(120),
      notes         VARCHAR2(500),
      created_by    NUMBER        NOT NULL,
      created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      separated_by  NUMBER,
      separated_at  TIMESTAMP WITH TIME ZONE,
      delivered_by  NUMBER,
      delivered_at  TIMESTAMP WITH TIME ZONE,
      CONSTRAINT ck_cart_mode   CHECK (cart_mode IN (''manual'',''scan'')),
      CONSTRAINT ck_cart_status CHECK (status IN (''open'',''separated'',''delivered'',''cancelled''))
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Pedido ↔ Gaiola ────────────────────────────────────────────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE picking_cart_orders (
      id            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cart_id       NUMBER       NOT NULL,
      order_id      NUMBER       NOT NULL,
      item_status   VARCHAR2(15) DEFAULT ''pending'' NOT NULL,
      separated_by  NUMBER,
      separated_at  TIMESTAMP WITH TIME ZONE,
      CONSTRAINT ck_pco_status CHECK (item_status IN (''pending'',''separated'')),
      CONSTRAINT fk_pco_cart FOREIGN KEY (cart_id)
        REFERENCES picking_carts(id) ON DELETE CASCADE,
      CONSTRAINT uq_pco_cart_order UNIQUE (cart_id, order_id)
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Itens esperados / progresso de bipagem (Processo 2) ────────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE picking_cart_items (
      id                   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cart_order_id        NUMBER       NOT NULL,
      order_item_id        NUMBER       NOT NULL,
      component_catalog_id NUMBER,
      sku                  VARCHAR2(100),
      ean                  VARCHAR2(20),
      expected_qty         NUMBER       DEFAULT 1 NOT NULL,
      scanned_qty          NUMBER       DEFAULT 0 NOT NULL,
      CONSTRAINT fk_pci_cart_order FOREIGN KEY (cart_order_id)
        REFERENCES picking_cart_orders(id) ON DELETE CASCADE
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Índices de apoio ───────────────────────────────────────────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_carts_wh_status ON picking_carts (warehouse_id, status)';
EXCEPTION WHEN e_exists THEN NULL;
END;
/
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_pco_order ON picking_cart_orders (order_id)';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── FKs externas (best-effort: ignora já-existe e alvo-ausente) ────────────────
DECLARE
  e1 EXCEPTION; PRAGMA EXCEPTION_INIT(e1, -955);
  e2 EXCEPTION; PRAGMA EXCEPTION_INIT(e2, -2275);
  e3 EXCEPTION; PRAGMA EXCEPTION_INIT(e3, -2264);
  e4 EXCEPTION; PRAGMA EXCEPTION_INIT(e4, -942);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_carts ADD CONSTRAINT fk_cart_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)';
EXCEPTION WHEN e1 THEN NULL; WHEN e2 THEN NULL; WHEN e3 THEN NULL; WHEN e4 THEN NULL;
END;
/
DECLARE
  e1 EXCEPTION; PRAGMA EXCEPTION_INIT(e1, -955);
  e2 EXCEPTION; PRAGMA EXCEPTION_INIT(e2, -2275);
  e3 EXCEPTION; PRAGMA EXCEPTION_INIT(e3, -2264);
  e4 EXCEPTION; PRAGMA EXCEPTION_INIT(e4, -942);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_carts ADD CONSTRAINT fk_cart_creator
    FOREIGN KEY (created_by) REFERENCES users(id)';
EXCEPTION WHEN e1 THEN NULL; WHEN e2 THEN NULL; WHEN e3 THEN NULL; WHEN e4 THEN NULL;
END;
/
DECLARE
  e1 EXCEPTION; PRAGMA EXCEPTION_INIT(e1, -955);
  e2 EXCEPTION; PRAGMA EXCEPTION_INIT(e2, -2275);
  e3 EXCEPTION; PRAGMA EXCEPTION_INIT(e3, -2264);
  e4 EXCEPTION; PRAGMA EXCEPTION_INIT(e4, -942);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE picking_cart_orders ADD CONSTRAINT fk_pco_order
    FOREIGN KEY (order_id) REFERENCES orders(id)';
EXCEPTION WHEN e1 THEN NULL; WHEN e2 THEN NULL; WHEN e3 THEN NULL; WHEN e4 THEN NULL;
END;
/

-- ── Diagnóstico ────────────────────────────────────────────────────────────────
SET SERVEROUTPUT ON
DECLARE
  v_c NUMBER; v_o NUMBER; v_i NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_c FROM user_tables WHERE table_name = 'PICKING_CARTS';
  SELECT COUNT(*) INTO v_o FROM user_tables WHERE table_name = 'PICKING_CART_ORDERS';
  SELECT COUNT(*) INTO v_i FROM user_tables WHERE table_name = 'PICKING_CART_ITEMS';
  DBMS_OUTPUT.PUT_LINE('picking_carts=' || v_c || ' picking_cart_orders=' || v_o ||
    ' picking_cart_items=' || v_i || ' (esperado 1 1 1)');
END;
/

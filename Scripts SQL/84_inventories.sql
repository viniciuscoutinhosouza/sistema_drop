-- 84_inventories.sql
-- Módulo de Inventário físico de estoque (PG e CMIG)
-- Cria: inventories, inventory_items (+ índice) e menu_keys de permissão.
--
-- NOTA: `number` e `mode` são palavras reservadas no Oracle → colunas inv_number/inv_mode.
-- Idempotente e auto-corretivo: se `inventories` estiver VAZIA (módulo novo, sem dados),
-- faz clean slate (drop + recreate) pra eliminar constraints parciais de tentativas
-- anteriores. NÃO dropa se houver dados.

-- ── Clean slate guardado (só se inventories estiver vazia ou não existir) ──────
DECLARE
  v_cnt     NUMBER := 0;
  e_noexist EXCEPTION; PRAGMA EXCEPTION_INIT(e_noexist, -942);
BEGIN
  BEGIN
    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM inventories' INTO v_cnt;
  EXCEPTION WHEN e_noexist THEN v_cnt := 0;
  END;
  IF v_cnt = 0 THEN
    BEGIN EXECUTE IMMEDIATE 'DROP TABLE inventory_items CASCADE CONSTRAINTS PURGE';
    EXCEPTION WHEN e_noexist THEN NULL; END;
    BEGIN EXECUTE IMMEDIATE 'DROP TABLE inventories CASCADE CONSTRAINTS PURGE';
    EXCEPTION WHEN e_noexist THEN NULL; END;
  END IF;
END;
/

-- ── Tabela de inventários (cabeçalho) — sem FKs externas ──────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE inventories (
      id            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      inv_number    NUMBER        NOT NULL,
      inv_mode      VARCHAR2(12)  NOT NULL,
      catalog_type  VARCHAR2(10)  NOT NULL,
      cmig_id       NUMBER,
      warehouse_id  NUMBER,
      status        VARCHAR2(12)  DEFAULT ''draft'' NOT NULL,
      notes         VARCHAR2(1000),
      created_by    NUMBER        NOT NULL,
      created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      finalized_by  NUMBER,
      finalized_at  TIMESTAMP WITH TIME ZONE,
      CONSTRAINT ck_inv_mode    CHECK (inv_mode IN (''baseline'',''adjustment'')),
      CONSTRAINT ck_inv_catalog CHECK (catalog_type IN (''pg'',''cmig'')),
      CONSTRAINT ck_inv_status  CHECK (status IN (''draft'',''finalized'',''cancelled''))
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Tabela de itens (linhas de contagem) ──────────────────────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE inventory_items (
      id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      inventory_id NUMBER       NOT NULL,
      product_type VARCHAR2(10) NOT NULL,
      product_id   NUMBER       NOT NULL,
      system_qty   NUMBER       DEFAULT 0 NOT NULL,
      counted_qty  NUMBER,
      delta        NUMBER,
      counted_at   TIMESTAMP WITH TIME ZONE,
      CONSTRAINT ck_inventory_items_type CHECK (product_type IN (''pg'',''cmig'')),
      CONSTRAINT fk_inventory_items_inv FOREIGN KEY (inventory_id)
        REFERENCES inventories(id) ON DELETE CASCADE,
      CONSTRAINT uq_inventory_items UNIQUE (inventory_id, product_type, product_id)
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Índice para o calculador buscar contagens por produto ─────────────────────
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE INDEX ix_invitem_product ON inventory_items (product_type, product_id)
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── FKs externas (best-effort: ignora já-existe e alvo-ausente) ───────────────
-- Códigos tolerados: -955 nome usado | -2275 ref já existe | -2264 nome de
-- constraint já usado | -942 tabela-alvo ausente.
DECLARE
  e1 EXCEPTION; PRAGMA EXCEPTION_INIT(e1, -955);
  e2 EXCEPTION; PRAGMA EXCEPTION_INIT(e2, -2275);
  e3 EXCEPTION; PRAGMA EXCEPTION_INIT(e3, -2264);
  e4 EXCEPTION; PRAGMA EXCEPTION_INIT(e4, -942);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE inventories ADD CONSTRAINT fk_inv_cmig
    FOREIGN KEY (cmig_id) REFERENCES cmigs(id)';
EXCEPTION WHEN e1 THEN NULL; WHEN e2 THEN NULL; WHEN e3 THEN NULL; WHEN e4 THEN NULL;
END;
/

DECLARE
  e1 EXCEPTION; PRAGMA EXCEPTION_INIT(e1, -955);
  e2 EXCEPTION; PRAGMA EXCEPTION_INIT(e2, -2275);
  e3 EXCEPTION; PRAGMA EXCEPTION_INIT(e3, -2264);
  e4 EXCEPTION; PRAGMA EXCEPTION_INIT(e4, -942);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE inventories ADD CONSTRAINT fk_inv_warehouse
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
  EXECUTE IMMEDIATE 'ALTER TABLE inventories ADD CONSTRAINT fk_inv_creator
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
  EXECUTE IMMEDIATE 'ALTER TABLE inventories ADD CONSTRAINT fk_inv_finalizer
    FOREIGN KEY (finalized_by) REFERENCES users(id)';
EXCEPTION WHEN e1 THEN NULL; WHEN e2 THEN NULL; WHEN e3 THEN NULL; WHEN e4 THEN NULL;
END;
/

-- ── Permissões: novas menu_keys nos perfis de sistema ─────────────────────────
-- admin e gl (UGO): veem e criam. go e gc: apenas veem. Tolerante a -942.
DECLARE
  v_id   NUMBER;
  e_nota EXCEPTION; PRAGMA EXCEPTION_INIT(e_nota, -942);
BEGIN
  FOR p IN (
    SELECT 'admin' AS pname, 1 AS can_create FROM DUAL UNION ALL
    SELECT 'gl',             1               FROM DUAL UNION ALL
    SELECT 'go',             0               FROM DUAL UNION ALL
    SELECT 'gc',             0               FROM DUAL
  ) LOOP
    BEGIN
      SELECT id INTO v_id FROM user_profiles WHERE name = p.pname;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      v_id := NULL;
    END;
    IF v_id IS NOT NULL THEN
      MERGE INTO profile_menu_permissions dst
      USING (SELECT v_id AS pid, 'inventario' AS mk FROM DUAL) src
      ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
      WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);

      IF p.can_create = 1 THEN
        MERGE INTO profile_menu_permissions dst
        USING (SELECT v_id AS pid, 'inventario_criar' AS mk FROM DUAL) src
        ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
        WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);
      END IF;
    END IF;
  END LOOP;
  COMMIT;
EXCEPTION WHEN e_nota THEN NULL;
END;
/

-- ── Diagnóstico ───────────────────────────────────────────────────────────────
SET SERVEROUTPUT ON
DECLARE
  v_inv  NUMBER;
  v_item NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_inv  FROM user_tables WHERE table_name = 'INVENTORIES';
  SELECT COUNT(*) INTO v_item FROM user_tables WHERE table_name = 'INVENTORY_ITEMS';
  DBMS_OUTPUT.PUT_LINE('inventories=' || v_inv || ' inventory_items=' || v_item ||
    ' (esperado 1 e 1)');
END;
/

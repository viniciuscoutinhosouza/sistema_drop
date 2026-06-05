-- 83_user_profiles.sql
-- Gestão de perfis de acesso configuráveis (super admin)
-- Cria: user_profiles, profile_menu_permissions
-- Altera: users.profile_id

-- ── Tabela de perfis ─────────────────────────────────────────────────────────
DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE user_profiles (
      id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      name       VARCHAR2(50)  NOT NULL,
      label      VARCHAR2(100) NOT NULL,
      base_role  VARCHAR2(20)  NOT NULL,
      is_system  NUMBER(1)     DEFAULT 0  NOT NULL,
      is_active  NUMBER(1)     DEFAULT 1  NOT NULL,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Tabela de permissões de menu por perfil ───────────────────────────────────
DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE profile_menu_permissions (
      id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      profile_id NUMBER       NOT NULL,
      menu_key   VARCHAR2(100) NOT NULL,
      CONSTRAINT fk_pmp_profile FOREIGN KEY (profile_id)
        REFERENCES user_profiles(id) ON DELETE CASCADE,
      CONSTRAINT uq_pmp_key UNIQUE (profile_id, menu_key)
    )
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Coluna profile_id em users ────────────────────────────────────────────────
DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE '
    ALTER TABLE users ADD profile_id NUMBER
      REFERENCES user_profiles(id) ON DELETE SET NULL
  ';
EXCEPTION WHEN e_exists THEN NULL;
END;
/

-- ── Seed: perfis de sistema (não podem ser deletados) ────────────────────────
BEGIN
  FOR r IN (
    SELECT 'admin' AS name, 'Administrador'        AS label, 'admin' AS base_role FROM DUAL UNION ALL
    SELECT 'go',            'Gestor Operacional',              'go'                FROM DUAL UNION ALL
    SELECT 'gl',            'Gestor Logístico',                'ugo'               FROM DUAL UNION ALL
    SELECT 'gc',            'Gestor de Conta',                 'ac'                FROM DUAL
  ) LOOP
    MERGE INTO user_profiles dst
    USING (SELECT r.name AS name FROM DUAL) src
    ON (dst.name = src.name)
    WHEN NOT MATCHED THEN
      INSERT (name, label, base_role, is_system, is_active)
      VALUES (r.name, r.label, r.base_role, 1, 1);
  END LOOP;
  COMMIT;
END;
/

-- ── Seed: permissões de menu para cada perfil de sistema ─────────────────────
-- AC / Gestor de Conta
DECLARE
  v_id NUMBER;
BEGIN
  SELECT id INTO v_id FROM user_profiles WHERE name = 'gc';
  FOR k IN (
    SELECT 'cmig'          AS mk FROM DUAL UNION ALL
    SELECT 'integrations'          FROM DUAL UNION ALL
    SELECT 'cmig_reports'          FROM DUAL UNION ALL
    SELECT 'full_cnpjs'            FROM DUAL UNION ALL
    SELECT 'anuncios'              FROM DUAL UNION ALL
    SELECT 'atendimento'           FROM DUAL UNION ALL
    SELECT 'financeiro'            FROM DUAL UNION ALL
    SELECT 'pedidos'               FROM DUAL UNION ALL
    SELECT 'catalog'               FROM DUAL UNION ALL
    SELECT 'pedido_manual'         FROM DUAL UNION ALL
    SELECT 'devolucoes'            FROM DUAL UNION ALL
    SELECT 'estoque'               FROM DUAL UNION ALL
    SELECT 'pessoas'               FROM DUAL UNION ALL
    SELECT 'fiscal_entradas'       FROM DUAL UNION ALL
    SELECT 'fiscal_saidas'         FROM DUAL
  ) LOOP
    MERGE INTO profile_menu_permissions dst
    USING (SELECT v_id AS pid, k.mk AS mk FROM DUAL) src
    ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
    WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);
  END LOOP;
  COMMIT;
END;
/

-- GL / Gestor Logístico (UGO)
DECLARE
  v_id NUMBER;
BEGIN
  SELECT id INTO v_id FROM user_profiles WHERE name = 'gl';
  FOR k IN (
    SELECT 'pg'            AS mk FROM DUAL UNION ALL
    SELECT 'cmig'                  FROM DUAL UNION ALL
    SELECT 'pedidos'               FROM DUAL UNION ALL
    SELECT 'estoque'               FROM DUAL UNION ALL
    SELECT 'ag_retorno'            FROM DUAL UNION ALL
    SELECT 'devolucoes'            FROM DUAL UNION ALL
    SELECT 'pessoas'               FROM DUAL UNION ALL
    SELECT 'fiscal_entradas'       FROM DUAL UNION ALL
    SELECT 'fiscal_saidas'         FROM DUAL UNION ALL
    SELECT 'rotinas'               FROM DUAL UNION ALL
    SELECT 'config_usuarios'       FROM DUAL
  ) LOOP
    MERGE INTO profile_menu_permissions dst
    USING (SELECT v_id AS pid, k.mk AS mk FROM DUAL) src
    ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
    WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);
  END LOOP;
  COMMIT;
END;
/

-- GO / Gestor Operacional
DECLARE
  v_id NUMBER;
BEGIN
  SELECT id INTO v_id FROM user_profiles WHERE name = 'go';
  FOR k IN (
    SELECT 'rotinas'       AS mk FROM DUAL UNION ALL
    SELECT 'go_empresa'            FROM DUAL UNION ALL
    SELECT 'go_usuarios'           FROM DUAL
  ) LOOP
    MERGE INTO profile_menu_permissions dst
    USING (SELECT v_id AS pid, k.mk AS mk FROM DUAL) src
    ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
    WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);
  END LOOP;
  COMMIT;
END;
/

-- Admin (todos os menus)
DECLARE
  v_id NUMBER;
BEGIN
  SELECT id INTO v_id FROM user_profiles WHERE name = 'admin';
  FOR k IN (
    SELECT 'cmig'              AS mk FROM DUAL UNION ALL
    SELECT 'integrations'              FROM DUAL UNION ALL
    SELECT 'cmig_reports'              FROM DUAL UNION ALL
    SELECT 'full_cnpjs'                FROM DUAL UNION ALL
    SELECT 'anuncios'                  FROM DUAL UNION ALL
    SELECT 'atendimento'               FROM DUAL UNION ALL
    SELECT 'financeiro'                FROM DUAL UNION ALL
    SELECT 'pedidos'                   FROM DUAL UNION ALL
    SELECT 'catalog'                   FROM DUAL UNION ALL
    SELECT 'pedido_manual'             FROM DUAL UNION ALL
    SELECT 'devolucoes'                FROM DUAL UNION ALL
    SELECT 'estoque'                   FROM DUAL UNION ALL
    SELECT 'pessoas'                   FROM DUAL UNION ALL
    SELECT 'fiscal_entradas'           FROM DUAL UNION ALL
    SELECT 'fiscal_saidas'             FROM DUAL UNION ALL
    SELECT 'pg'                        FROM DUAL UNION ALL
    SELECT 'ag_retorno'                FROM DUAL UNION ALL
    SELECT 'rotinas'                   FROM DUAL UNION ALL
    SELECT 'go_empresa'                FROM DUAL UNION ALL
    SELECT 'go_usuarios'               FROM DUAL UNION ALL
    SELECT 'config_usuarios'           FROM DUAL UNION ALL
    SELECT 'config_gestores'           FROM DUAL UNION ALL
    SELECT 'config_ai'                 FROM DUAL UNION ALL
    SELECT 'config_api_console'        FROM DUAL UNION ALL
    SELECT 'config_perfis'             FROM DUAL
  ) LOOP
    MERGE INTO profile_menu_permissions dst
    USING (SELECT v_id AS pid, k.mk AS mk FROM DUAL) src
    ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
    WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);
  END LOOP;
  COMMIT;
END;
/

-- ============================================================
-- Migration 140: UNIFICAÇÃO dos papéis `go` e `ugo` no papel único "Galpão".
-- ============================================================
--
-- DECISÃO CANÔNICA (travada com o dono):
--   * Papel unificado: valor `go`, rótulo "Galpão". `ugo` é APOSENTADO — não mais oferecido nem
--     usado, mas MANTIDO no CHECK constraint `chk_users_role` (ver script 16) por segurança/rollback.
--     Por isso esta migration NÃO altera o CHECK constraint.
--   * Comportamento canônico = ISOLADO POR GALPÃO: todo usuário "Galpão" enxerga só o próprio
--     `warehouse_id`. Os bypasses globais do antigo `ugo` foram removidos no backend; o antigo `go`
--     (já isolado por galpão) recebeu as capacidades que o `ugo` tinha.
--   * Dono-vs-operador deixou de ser papel → virou permissão de perfil (menu_permissions +
--     profile_action_permissions), gated pelos menus `go_empresa`/`go_usuarios`.
--
-- IDEMPOTÊNCIA: cada passo é reexecutável.
--   - UPDATEs são naturalmente idempotentes (na 2ª rodada não há mais linhas `ugo` a converter).
--   - A consolidação de perfis usa INSERT ... WHERE NOT EXISTS e re-verifica a contagem de perfis
--     de sistema `go` antes de agir (na 2ª rodada já há só 1 → não faz nada).
--
-- ORDEM IMPORTA:
--   1) users.role  ugo → go
--   2) user_profiles.base_role  ugo → go
--   3) Consolidação dos 2 perfis de sistema base_role='go' num só "Galpão" (união de menus/ações).
--
-- ISOLAMENTO (importante): NÃO fazemos backfill de `go_id` nos operadores. Ser "dono do galpão" é
-- definido por POSSUIR um registro em `goes` (goes.user_id == users.id), NÃO por ter go_id setado.
-- A gestão de galpão (warehouse.py) usa esse critério de posse; assim um operador (não-dono) fica
-- restrito ao próprio galpão mesmo com go_id herdado, e nunca enxerga galpão irmão.
--
-- Relação com a 139 (seed de action_permissions): NÃO alteramos a 139 retroativamente. Após a
-- unificação o grant_keys('ugo', ...) da 139 vira no-op (não há perfil de sistema base_role='ugo').
-- A chave que estava só no `ugo` (criar_ac) é garantida no perfil "Galpão" consolidado pelo passo 4
-- (a UNIÃO das ações do outro perfil é copiada), e o catálogo (services/action_permissions.py) já
-- passou `criar_ac` para default_base_roles=['admin','go'].
-- ============================================================


-- ── Passo 1: converte o papel dos usuários  ugo → go ───────────────────────────────────────────
-- (NÃO fazemos backfill de go_id — ver nota ISOLAMENTO no cabeçalho: dono = registro em `goes`.)
UPDATE users SET role = 'go' WHERE role = 'ugo';
COMMIT;


-- ── Passo 2: converte o base_role dos perfis  ugo → go ─────────────────────────────────────────
-- Depois deste passo, haverá 2 perfis is_system=1 com base_role='go': o antigo 'go' (name='go') e
-- o antigo 'gl' (name='gl', que era base_role='ugo'). São consolidados no passo 3.
UPDATE user_profiles SET base_role = 'go' WHERE base_role = 'ugo';
COMMIT;


-- ── Passo 3: consolida os 2 perfis de sistema base_role='go' num único "Galpão" ────────────────
-- Escolhe o de MENOR id como canônico; move para ele a UNIÃO de profile_menu_permissions e
-- profile_action_permissions do outro; reaponta users.profile_id; limpa as tabelas-filha do outro;
-- remove (soft/hard) o perfil redundante. Idempotente: só age quando existem >= 2 perfis.
DECLARE
  v_canon   NUMBER;   -- perfil canônico (menor id)
  v_other   NUMBER;   -- perfil redundante
  v_count   NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_profiles
   WHERE is_system = 1 AND base_role = 'go';

  IF v_count < 2 THEN
    RETURN;  -- já consolidado (ou nada a fazer) — reexecução segura
  END IF;

  -- Canônico = menor id; redundante = maior id (assume exatamente 2 perfis de sistema 'go').
  SELECT MIN(id), MAX(id) INTO v_canon, v_other
    FROM user_profiles
   WHERE is_system = 1 AND base_role = 'go';

  -- 4a) UNIÃO dos menus: copia do redundante para o canônico os que faltam.
  INSERT INTO profile_menu_permissions (profile_id, menu_key)
  SELECT v_canon, s.menu_key
    FROM profile_menu_permissions s
   WHERE s.profile_id = v_other
     AND NOT EXISTS (
       SELECT 1 FROM profile_menu_permissions d
        WHERE d.profile_id = v_canon AND d.menu_key = s.menu_key
     );

  -- 4b) UNIÃO das ações: copia do redundante para o canônico as que faltam.
  --     (a tabela profile_action_permissions existe a partir da migration 138.)
  INSERT INTO profile_action_permissions (profile_id, permission_key)
  SELECT v_canon, s.permission_key
    FROM profile_action_permissions s
   WHERE s.profile_id = v_other
     AND NOT EXISTS (
       SELECT 1 FROM profile_action_permissions d
        WHERE d.profile_id = v_canon AND d.permission_key = s.permission_key
     );

  -- 4c) Reaponta os usuários do perfil redundante para o canônico ANTES de removê-lo.
  UPDATE users SET profile_id = v_canon WHERE profile_id = v_other;

  -- 4d) Limpa as tabelas-filha do redundante (o ON DELETE CASCADE também cobriria, mas explicitamos).
  DELETE FROM profile_action_permissions WHERE profile_id = v_other;
  DELETE FROM profile_menu_permissions   WHERE profile_id = v_other;

  -- 4e) Remove o perfil redundante (já sem users e sem filhos).
  DELETE FROM user_profiles WHERE id = v_other;

  -- 4f) Rotula o canônico como "Galpão" (mantém o `name` existente — 'go' ou 'gl' é indiferente).
  UPDATE user_profiles SET label = 'Galpão' WHERE id = v_canon;

  COMMIT;
END;
/


-- ── Passo 3g: garante que o perfil "Galpão" canônico tenha a UNIÃO mínima de menus e ações ─────
-- Rede de segurança para DB recriado do zero (onde os seeds das 83/138/139 podem ter deixado
-- conjuntos parciais). Semeia as chaves esperadas do papel unificado; idempotente (NOT EXISTS).
DECLARE
  v_canon NUMBER;
BEGIN
  SELECT MIN(id) INTO v_canon
    FROM user_profiles
   WHERE is_system = 1 AND base_role = 'go';

  IF v_canon IS NULL THEN
    RETURN;  -- sem perfil de sistema 'go' — nada a semear
  END IF;

  -- Menus do Galpão unificado (união operador + dono).
  FOR k IN (
    SELECT 'pg' AS mk FROM dual UNION ALL
    SELECT 'cmig' FROM dual UNION ALL
    SELECT 'pedidos' FROM dual UNION ALL
    SELECT 'estoque' FROM dual UNION ALL
    SELECT 'separacao' FROM dual UNION ALL
    SELECT 'ag_retorno' FROM dual UNION ALL
    SELECT 'inventario' FROM dual UNION ALL
    SELECT 'inventario_criar' FROM dual UNION ALL
    SELECT 'devolucoes' FROM dual UNION ALL
    SELECT 'pessoas' FROM dual UNION ALL
    SELECT 'fiscal_entradas' FROM dual UNION ALL
    SELECT 'fiscal_saidas' FROM dual UNION ALL
    SELECT 'rotinas' FROM dual UNION ALL
    SELECT 'config_usuarios' FROM dual UNION ALL
    SELECT 'integracao_envio' FROM dual UNION ALL
    SELECT 'go_empresa' FROM dual UNION ALL
    SELECT 'go_usuarios' FROM dual UNION ALL
    SELECT 'relatorio_vendas' FROM dual
  ) LOOP
    INSERT INTO profile_menu_permissions (profile_id, menu_key)
    SELECT v_canon, k.mk FROM dual
     WHERE NOT EXISTS (
       SELECT 1 FROM profile_menu_permissions
        WHERE profile_id = v_canon AND menu_key = k.mk
     );
  END LOOP;

  -- Ações do Galpão unificado (union das defaults de 'go' + a chave que era só do 'ugo': criar_ac).
  FOR a IN (
    SELECT 'usuarios_criar' AS pk FROM dual UNION ALL
    SELECT 'relatorio_vendas' FROM dual UNION ALL
    SELECT 'criar_ac' FROM dual
  ) LOOP
    INSERT INTO profile_action_permissions (profile_id, permission_key)
    SELECT v_canon, a.pk FROM dual
     WHERE NOT EXISTS (
       SELECT 1 FROM profile_action_permissions
        WHERE profile_id = v_canon AND permission_key = a.pk
     );
  END LOOP;

  COMMIT;
END;
/


-- ============================================================
-- FIM da migration 140. Após rodar:
--   * Nenhum usuário/perfil com role/base_role='ugo' (convertidos em 'go').
--   * Um único perfil de sistema "Galpão" (base_role='go') com a UNIÃO de menus e ações.
--   * `ugo` permanece válido no CHECK apenas para rollback; sem uso ativo.
-- ============================================================

-- Migration 158: SEED das permissões de ação do eShip nos perfis de SISTEMA (ADR-0035 Fase 2e).
--
-- O eShip deixou de ser role-based (require_role) e passou a require_permission com 3 chaves novas
-- (eship_consultar | eship_operar | eship_config). Este seed concede as chaves aos perfis-SISTEMA
-- EXATAMENTE conforme os papéis que o require_role original liberava → ZERO-REGRESSÃO:
--   eship_consultar  ← admin, ugo, go, ac   (require_role("admin","ugo","go","ac"))
--   eship_operar     ← admin, ugo, go       (require_role("admin","ugo","go"))
--   eship_config     ← admin                (require_role("admin"))
--
-- Idempotente: só insere (profile_id, permission_key) que ainda não existe. Só toca is_system=1
-- (perfis editados pelo dono não são alterados). Mesmo padrão da migration 139.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);

  admin_keys t_keys := t_keys('eship_consultar', 'eship_operar', 'eship_config');
  go_keys    t_keys := t_keys('eship_consultar', 'eship_operar');
  ugo_keys   t_keys := t_keys('eship_consultar', 'eship_operar');
  ac_keys    t_keys := t_keys('eship_consultar');

  PROCEDURE grant_keys(p_base_role VARCHAR2, p_keys t_keys) IS
  BEGIN
    FOR prof IN (
      SELECT id FROM user_profiles
      WHERE is_system = 1 AND base_role = p_base_role
    ) LOOP
      FOR i IN 1 .. p_keys.COUNT LOOP
        INSERT INTO profile_action_permissions (profile_id, permission_key)
        SELECT prof.id, p_keys(i) FROM dual
        WHERE NOT EXISTS (
          SELECT 1 FROM profile_action_permissions
          WHERE profile_id = prof.id AND permission_key = p_keys(i)
        );
      END LOOP;
    END LOOP;
  END;
BEGIN
  grant_keys('admin', admin_keys);
  grant_keys('go',    go_keys);
  grant_keys('ugo',   ugo_keys);   -- no-op (perfis ugo consolidados em go na migration 140)
  grant_keys('ac',    ac_keys);
  COMMIT;
END;
/

-- Migration 180: SEED da permissão de ação `bling_gerenciar` (ADR-0036).
--
-- Gerenciar a integração Bling por CMIG (conectar/desconectar/testar) é uma CAPACIDADE editável por
-- Perfil (require_permission), não um gate fixo. Concede a chave aos perfis-SISTEMA conforme o
-- default do catálogo (services/action_permissions.py): ac + admin — coerente com quem gerencia a
-- CMIG (cmig_gerenciar). Autorização efetiva = permissão (aqui) AND assert_cmig_access (escopo).
--
-- Idempotente: só insere (profile_id, permission_key) que ainda não existe; só toca is_system=1.
-- Mesmo padrão da migration 162.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);

  admin_keys t_keys := t_keys('bling_gerenciar');
  ac_keys    t_keys := t_keys('bling_gerenciar');

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
  grant_keys('ac',    ac_keys);
  COMMIT;
END;
/

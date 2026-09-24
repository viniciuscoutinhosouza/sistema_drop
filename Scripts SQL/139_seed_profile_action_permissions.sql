-- Migration 139: SEED das permissões de ação dos perfis de SISTEMA (ADR-0025).
--
-- Reprodutibilidade: a fase 1 semeou em produção via script ad-hoc. Esta migration versiona o
-- mesmo seed para que um DB recriado do zero fique com paridade de comportamento (cada perfil de
-- sistema recebe as permissões default do seu base_role — igual ao antigo require_role).
--
-- Fonte da verdade do catálogo: BACKEND/services/action_permissions.py (default_base_roles).
-- Aqui os defaults estão materializados por base_role. Se o catálogo mudar, ajustar este seed OU
-- editar o perfil pela UI (Gestão de Perfis) — o fallback em require_permission cobre lacunas.
--
-- Idempotente: só insere o par (profile_id, permission_key) que ainda não existe. Só toca perfis
-- de sistema (is_system=1); perfis criados/editados pelo dono não são alterados.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);

  -- Defaults por base_role (espelham default_keys_for_base_role do catálogo)
  admin_keys t_keys := t_keys(
    'usuarios_gerenciar','perfis_gerenciar','go_gerenciar','api_console','usuarios_criar',
    'criar_ac','nfe_gerenciar','cfop_gerenciar','ncm_gerenciar','config_marketplace',
    'config_email','ia_config','relatorio_vendas','pg_admin','anuncios_admin'
  );
  ac_keys  t_keys := t_keys('nfe_gerenciar','relatorio_vendas');
  ugo_keys t_keys := t_keys('criar_ac');
  go_keys  t_keys := t_keys('usuarios_criar','relatorio_vendas');

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
  grant_keys('ugo',   ugo_keys);
  grant_keys('go',    go_keys);
  COMMIT;
END;
/

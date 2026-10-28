-- Migration 170: SEED das permissões de ação de pagamento (confirmar manual / cancelar).
-- Chaves novas em services/action_permissions.py: pagamento_confirmar, pagamento_cancelar.
-- Concede aos perfis-SISTEMA conforme default_base_roles (admin/go/ac) → ZERO-REGRESSÃO (quem já
-- operava o menu Pedidos passa a ter as ações). Só is_system=1; idempotente. Molde da migration 164.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);

  all_keys t_keys := t_keys('pagamento_confirmar', 'pagamento_cancelar');

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
  grant_keys('admin', all_keys);
  grant_keys('go',    all_keys);
  grant_keys('ac',    all_keys);
  COMMIT;
END;
/

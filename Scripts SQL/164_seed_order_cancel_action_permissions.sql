-- Migration 164: SEED das permissões de ação de cancelamento/crédito-cliente (ADR-0037).
--
-- Duas chaves novas no catálogo (services/action_permissions.py):
--   pedido_cancelar            ← admin, go, ac   (cancelar pedido de venda direta)
--   credito_cliente_gerenciar  ← admin, go, ac   (lançar/baixar crédito do cliente)
-- Concede aos perfis-SISTEMA conforme o default_base_roles → ZERO-REGRESSÃO (o deploy sozinho
-- preserva quem já operava venda direta). Só toca is_system=1 (perfis editados pelo dono não
-- são alterados). Idempotente: só insere (profile_id, permission_key) que ainda não existe.
-- Mesmo padrão da migration 162.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);

  admin_keys t_keys := t_keys('pedido_cancelar', 'credito_cliente_gerenciar');
  go_keys    t_keys := t_keys('pedido_cancelar', 'credito_cliente_gerenciar');
  ac_keys    t_keys := t_keys('pedido_cancelar', 'credito_cliente_gerenciar');

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
  grant_keys('ac',    ac_keys);
  COMMIT;
END;
/

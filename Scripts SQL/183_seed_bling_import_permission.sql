-- Migration 183: SEED da permissão `bling_importar` (ADR-0040 Fase 2).
-- Importar catálogo do Bling (categorias/produtos/kits → CMIG ou PG) é capacidade editável por Perfil.
-- Default = ac + admin (mesmo par de bling_gerenciar; a importação é parte do fluxo Bling por CMIG).
-- Autorização efetiva = permissão AND assert_cmig_access (escopo) AND product_mode (ADR-0024/0029).
-- Idempotente; só is_system=1. Mesmo molde da migration 180.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);
  admin_keys t_keys := t_keys('bling_importar');
  ac_keys    t_keys := t_keys('bling_importar');

  PROCEDURE grant_keys(p_base_role VARCHAR2, p_keys t_keys) IS
  BEGIN
    FOR prof IN (SELECT id FROM user_profiles WHERE is_system = 1 AND base_role = p_base_role) LOOP
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

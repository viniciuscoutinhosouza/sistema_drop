-- Migration 162: SEED das novas permissões de ação CMIG/Fiscal/PG/Estoque (ADR-0036).
--
-- As capacidades de gerenciar CMIG, configuração fiscal + certificado, tipo fiscal, DC-e, import/
-- sync PG e movimentação de estoque deixaram de ser gates fixos `is_conta/is_galpao/is_global`
-- (helper de ESCOPO) e viraram PERMISSÕES DE AÇÃO editáveis por Perfil (require_permission /
-- user_has_permission). Este seed concede as chaves aos perfis-SISTEMA EXATAMENTE conforme os
-- papéis que o gate inline original liberava → ZERO-REGRESSÃO:
--   cmig_gerenciar      ← ac, admin   (criar/editar CMIG + co-admin + integração eShip)
--   cmig_tipo_fiscal    ← ac, admin   (CPF <-> CNPJ — ADR-0018)
--   cmig_fiscal_config  ← ac, admin   (config fiscal + certificado A1 + modo de emissão)
--   cmig_dce_authorized ← admin       (DC-e por conta e ordem — ADR-0017, default restrito)
--   pg_importar         ← go, admin   (importar Produto CMIG -> PG)
--   pg_sincronizar      ← go, admin   (sincronizar Produto CMIG -> PG)
--   estoque_movimentar  ← go, admin   (desmontar KIT / ajustes manuais de estoque)
--
-- Idempotente: só insere (profile_id, permission_key) que ainda não existe. Só toca is_system=1
-- (perfis editados pelo dono não são alterados). Mesmo padrão da migration 158.

DECLARE
  TYPE t_keys IS TABLE OF VARCHAR2(100);

  admin_keys t_keys := t_keys(
    'cmig_gerenciar', 'cmig_tipo_fiscal', 'cmig_fiscal_config', 'cmig_dce_authorized',
    'pg_importar', 'pg_sincronizar', 'estoque_movimentar'
  );
  ac_keys    t_keys := t_keys('cmig_gerenciar', 'cmig_tipo_fiscal', 'cmig_fiscal_config');
  go_keys    t_keys := t_keys('pg_importar', 'pg_sincronizar', 'estoque_movimentar');
  ugo_keys   t_keys := t_keys('pg_importar', 'pg_sincronizar', 'estoque_movimentar');

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
  grant_keys('go',    go_keys);
  grant_keys('ugo',   ugo_keys);   -- no-op (perfis ugo consolidados em go na migration 140)
  COMMIT;
END;
/

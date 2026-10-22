-- Migration 156: backfill de profile_id para TODOS os usuários (Fase 1 do plano "só Perfil de Acesso", ADR-0035).
--
-- Hoje um usuário SEM profile_id cai no FALLBACK (dependencies._resolve_user_*_keys / auth):
-- usa o perfil-SISTEMA (is_system=1, is_active=1) cujo base_role == users.role. Esta migration
-- apenas MATERIALIZA esse vínculo (grava o profile_id explicitamente) — comportamento idêntico,
-- ZERO regressão. É o passo que, mais adiante (Fase 3), permite remover o fallback e o campo role.
--
-- Escolhe o perfil-sistema mais ANTIGO do base_role (MIN(id)) — espelha o `order_by(id).first()`
-- do fallback atual. Só toca linhas com profile_id NULL e só quando existe perfil-sistema casável
-- (fail-safe: nunca zera nem sobrescreve um profile_id já definido).
--
-- Idempotente: reexecutar não altera nada (não há mais NULL casável). profile_id permanece NULLABLE
-- nesta fase (a obrigatoriedade/NOT NULL entra na Fase 3, junto com a remoção do fallback).

BEGIN
  UPDATE users u
     SET u.profile_id = (
           SELECT MIN(p.id)
             FROM user_profiles p
            WHERE p.is_system = 1
              AND p.is_active = 1
              AND p.base_role = u.role
         )
   WHERE u.profile_id IS NULL
     AND EXISTS (
           SELECT 1
             FROM user_profiles p
            WHERE p.is_system = 1
              AND p.is_active = 1
              AND p.base_role = u.role
         );
  COMMIT;
END;
/

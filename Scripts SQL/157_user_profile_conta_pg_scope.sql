-- Migration 157: UserProfile.conta_pg_scope (ADR-0035 Fase 2d).
--
-- Torna configurável, POR PERFIL DE ACESSO, a base de visibilidade de PG do AC (modo CONTA):
--   'posse'        → galpões das CMIGs de que o AC é DONO (owner_ac_id) — PADRÃO = comportamento atual
--   'administracao'→ galpões das CMIGs que o AC ADMINISTRA (cmig_administrators) — colaborador vê PG
--   'nenhum'       → não vê PG
--
-- A visibilidade de CMIG continua sempre por administração (cmig_administrators) — decisão do dono.
-- Default 'posse' = ZERO-REGRESSÃO. Só é consultado no ramo CONTA do services/warehouse_scope.py.
-- Idempotente (ignora ORA-01430 se a coluna já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  BEGIN
    EXECUTE IMMEDIATE q'[ALTER TABLE user_profiles ADD (conta_pg_scope VARCHAR2(20) DEFAULT 'posse' NOT NULL)]';
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
END;
/

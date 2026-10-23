-- 159_drop_users_role_column.sql
-- ADR-0035 (Fase 3 / finalização): elimina a coluna users.role.
--
-- O "PERFIL" (users.role) deixou de existir: o escopo/role passou a derivar do
-- Perfil de Acesso (UserProfile.base_role). No código, User.role virou hybrid_property
-- derivada do perfil (commit feat(rbac): fase 3 ...). A coluna ficou VESTIGIAL e, pior,
-- a CHECK CHK_USERS_ROLE (role IN ('ugo','ac','admin','go')) passou a BLOQUEAR a criação
-- de usuário: como o ORM não mapeia mais `role`, o INSERT omite a coluna e o DEFAULT
-- 'dropshipper' viola a CHECK. Dropar a coluna remove de uma vez a CHECK, o NOT NULL e o
-- DEFAULT, destravando a criação de usuário.
--
-- Idempotente: se a coluna já não existir (ORA-00904), ignora.

DECLARE
    e_col_nao_existe EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_nao_existe, -904);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE users DROP COLUMN role';
EXCEPTION
    WHEN e_col_nao_existe THEN NULL;  -- coluna já removida
END;
/

-- profile_id passa a ser obrigatório (todo usuário nasce com Perfil de Acesso).
-- Só aplica se não houver linhas órfãs (backfill 156 já cobriu); idempotente.
DECLARE
    v_orfaos NUMBER;
    v_ja_notnull NUMBER;
    e_ja_notnull EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_ja_notnull, -1442);  -- já é NOT NULL
BEGIN
    SELECT COUNT(*) INTO v_orfaos FROM users WHERE profile_id IS NULL;
    IF v_orfaos = 0 THEN
        BEGIN
            EXECUTE IMMEDIATE 'ALTER TABLE users MODIFY (profile_id NOT NULL)';
        EXCEPTION
            WHEN e_ja_notnull THEN NULL;
        END;
    END IF;
END;
/

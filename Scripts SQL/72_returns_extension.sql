-- 72_returns_extension.sql
-- Fase 2: Campos de validação para devoluções de clientes
-- Idempotente via EXCEPTION WHEN e_col_exists

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE returns ADD return_type VARCHAR2(20) DEFAULT ''customer''';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE returns ADD validation_notes CLOB';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE returns ADD validated_by NUMBER';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE returns ADD validated_at TIMESTAMP';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE returns ADD validation_photos_json CLOB';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Atualiza constraint de status.
-- search_condition é LONG no Oracle — não aceita UPPER() em SQL.
-- Solução: iterar cursor em PL/SQL e fazer o filtro na variável PL/SQL.
DECLARE
    v_search     LONG;
    v_search_sub VARCHAR2(4000);
BEGIN
    FOR r IN (
        SELECT constraint_name, search_condition
          FROM user_constraints
         WHERE table_name = 'RETURNS'
           AND constraint_type = 'C'
    ) LOOP
        v_search     := r.search_condition;
        v_search_sub := SUBSTR(v_search, 1, 4000);
        IF UPPER(v_search_sub) LIKE '%STATUS%' THEN
            BEGIN
                EXECUTE IMMEDIATE 'ALTER TABLE returns DROP CONSTRAINT ' || r.constraint_name;
            EXCEPTION WHEN OTHERS THEN NULL;
            END;
        END IF;
    END LOOP;

    EXECUTE IMMEDIATE q'[ALTER TABLE returns ADD CONSTRAINT chk_return_status CHECK (
        status IN ('analyzing','returned','rejected','awaiting_validation','validated_ok','validated_unfit','awaiting_physical_return')
    )]';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/



COMMIT;

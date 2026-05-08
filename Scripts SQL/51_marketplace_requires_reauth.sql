-- Migration 51: adiciona coluna requires_reauth em marketplace_accounts
-- Idempotente: ignora ORA-01430 (coluna já existe)
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE marketplace_accounts ADD requires_reauth NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -01430 THEN NULL; ELSE RAISE; END IF;
END;
/


COMMIT;
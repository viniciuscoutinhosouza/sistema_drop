-- ============================================================
-- MIG ECOMMERCE – Script 14: Adiciona saldo ao perfil do AC
-- Camada 1 do financeiro: saldo operacional do Gestor de Conta
-- Idempotente: ignora ORA-01430 se coluna já existir
-- ============================================================

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE ac_profiles ADD balance NUMBER(15,2) DEFAULT 0 NOT NULL';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE = -1430 THEN NULL; -- coluna já existe, ok
    ELSE RAISE;
    END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE ac_profiles ADD balance_reserved NUMBER(15,2) DEFAULT 0 NOT NULL';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE = -1430 THEN NULL;
    ELSE RAISE;
    END IF;
END;
/

COMMIT;

-- Validação
SELECT column_name, data_type, data_default
  FROM user_tab_columns
 WHERE table_name = 'AC_PROFILES'
   AND column_name IN ('BALANCE','BALANCE_RESERVED');

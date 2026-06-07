-- 87_separacao_menu_key.sql
-- Adiciona a menu_key `separacao` aos perfis de sistema admin e gl (UGO).
-- Idempotente (MERGE). Tolerante a tabela ausente (-942).

DECLARE
  v_id   NUMBER;
  e_nota EXCEPTION; PRAGMA EXCEPTION_INIT(e_nota, -942);
BEGIN
  FOR p IN (
    SELECT 'admin' AS pname FROM DUAL UNION ALL
    SELECT 'gl'             FROM DUAL
  ) LOOP
    BEGIN
      SELECT id INTO v_id FROM user_profiles WHERE name = p.pname;
    EXCEPTION WHEN NO_DATA_FOUND THEN
      v_id := NULL;
    END;
    IF v_id IS NOT NULL THEN
      MERGE INTO profile_menu_permissions dst
      USING (SELECT v_id AS pid, 'separacao' AS mk FROM DUAL) src
      ON (dst.profile_id = src.pid AND dst.menu_key = src.mk)
      WHEN NOT MATCHED THEN INSERT (profile_id, menu_key) VALUES (src.pid, src.mk);
    END IF;
  END LOOP;
  COMMIT;
EXCEPTION WHEN e_nota THEN NULL;
END;
/

SET SERVEROUTPUT ON
DECLARE v_n NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_n FROM profile_menu_permissions WHERE menu_key = 'separacao';
  DBMS_OUTPUT.PUT_LINE('perfis com separacao=' || v_n || ' (esperado >=1)');
END;
/

-- 142_users_avatar.sql
-- Foto (avatar) do próprio usuário, exibida no menu lateral. URL pública em /static/uploads/
-- user-avatars/<uuid>.<ext> (nome UUID → não enumerável). Idempotente (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);   -- ORA-01430: column already exists

  PROCEDURE add_col(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE users ADD (avatar_url VARCHAR2(500))');
  COMMIT;
END;
/

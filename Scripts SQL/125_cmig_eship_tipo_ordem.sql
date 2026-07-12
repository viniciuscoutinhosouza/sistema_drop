-- 125_cmig_eship_tipo_ordem.sql
-- eShip: `idTipo` e `tipoOrdem` do webServicePostOrdem, por EMPRESA (CMIG).
--
-- O payload que funciona (ver .claude/eSHIP.md) manda, além de codigoArmazemOrigem:
--     "idTipo": 104,
--     "tipoOrdem": "MIG IMPORTACOES"
-- São valores do cadastro da empresa DENTRO do eShip (variam por CMIG), então ficam
-- configuráveis ao lado das demais credenciais eShip da CMIG. Opcionais: só entram no
-- payload quando preenchidos.
--
-- Idempotente: EXCEPTION WHEN e_col_exists (ORA-01430).

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
  add_col('ALTER TABLE cmigs ADD (eship_id_tipo NUMBER)');
  add_col('ALTER TABLE cmigs ADD (eship_tipo_ordem VARCHAR2(100))');
  COMMIT;
END;
/

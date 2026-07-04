-- 121_ibge_municipios.sql — cache do código IBGE de municípios (cidade+UF → código 7 díg.)
--
-- A DC-e exige o código IBGE do município do DESTINATÁRIO (cMun). O endereço do comprador
-- vindo do ML traz só cidade/UF em texto. Esta tabela é o cache (seed sob demanda da API do
-- IBGE, por UF) usado pelo resolvedor `services/fiscal/dce/ibge.py`.
--
-- Idempotente: EXCEPTION WHEN e_exists (-955 tabela).

DECLARE
  e_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);
  PROCEDURE run(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION WHEN e_exists THEN NULL;
  END;
BEGIN
  run('CREATE TABLE ibge_municipios (
        codigo     VARCHAR2(7) PRIMARY KEY,
        uf         VARCHAR2(2) NOT NULL,
        nome       VARCHAR2(150) NOT NULL,
        nome_norm  VARCHAR2(150) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
      )');
  run('CREATE INDEX ix_ibge_uf_norm ON ibge_municipios (uf, nome_norm)');
END;
/

COMMIT;

-- 136_nfe_source_e_inutilizacao.sql
-- Captura COMPLETA da sequência de NF-e do Faturador ML (venda + FULL + devolução + canceladas).
--
-- Contexto: hoje _sync_ml_fiscal_account só persiste notas FULL; a VENDA é pulada, então a série
-- fiscal fica com "furos" (na verdade as vendas nunca são gravadas). Para fechar a sequência sem
-- confundir com a emissão PRÓPRIA (SEFAZ/Focus) e para reconciliar furos legítimos (inutilização):
--   1) coluna `source` em invoices: distingue nota do Faturador ML da emissão própria.
--   2) colunas de cancelamento (o dedup vira upsert de status — cancelada e ativa têm a MESMA chave).
--   3) tabela `nfe_inutilizacoes`: store estruturado das faixas inutilizadas (SEFAZ própria + manual),
--      para a reconciliação NÃO reportar número inutilizado como furo. (Inutilização feita pelo
--      próprio ML não é exposta pela API → esses furos ficam como ALERTA, não prova.)
--
-- Idempotente: EXCEPTION WHEN e_col_exists (ORA-01430) / e_obj_exists (ORA-00955).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);   -- ORA-01430: column already exists
  e_obj_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_obj_exists, -955);    -- ORA-00955: name already used by existing object

  PROCEDURE add_col(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;

  PROCEDURE run_ddl(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_obj_exists THEN NULL;
  END;
BEGIN
  -- 1) origem da nota: 'ml_faturador' (emitida pelo ML) | 'fiscal_own' (SEFAZ/Focus próprio).
  --    NULL = legado (notas já existentes) — leitores tratam como própria.
  add_col('ALTER TABLE invoices ADD (source VARCHAR2(20))');

  -- 2) cancelamento refletido na própria linha (mesma chave de acesso).
  add_col('ALTER TABLE invoices ADD (cancel_protocol VARCHAR2(50))');
  add_col('ALTER TABLE invoices ADD (cancelled_at TIMESTAMP WITH TIME ZONE)');

  -- 3) faixas de numeração INUTILIZADA (fecham a sequência sem serem furo).
  run_ddl('CREATE TABLE nfe_inutilizacoes (
      id             NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cmig_id        NUMBER          NOT NULL,
      serie          NUMBER          NOT NULL,
      nro_ini        NUMBER          NOT NULL,
      nro_fim        NUMBER          NOT NULL,
      justificativa  VARCHAR2(255),
      protocol       VARCHAR2(50),
      inut_date      TIMESTAMP WITH TIME ZONE,
      source         VARCHAR2(20)    DEFAULT ''sefaz_own'',
      created_at     TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT fk_nfeinut_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE
  )');
  run_ddl('CREATE INDEX ix_nfeinut_cmig_serie ON nfe_inutilizacoes (cmig_id, serie)');

  -- Índice p/ a reconciliação varrer a sequência por (cmig, série, número) sem full scan.
  run_ddl('CREATE INDEX ix_inv_cmig_serie_num ON invoices (cmig_id, serie, nfe_number)');

  COMMIT;
END;
/

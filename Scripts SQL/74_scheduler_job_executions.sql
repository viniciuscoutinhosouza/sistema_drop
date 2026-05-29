-- Migration 74: tabela de histórico de execuções de rotinas automatizadas (APScheduler + triggers event-driven).
-- Persiste cada execução de job para a tela de monitoramento (UGO/GO/admin).
-- Retenção: 30 dias (limpeza diária via job prune_job_executions).

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE scheduler_job_executions (
      id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      job_id          VARCHAR2(80)  NOT NULL,
      started_at      TIMESTAMP WITH TIME ZONE NOT NULL,
      finished_at     TIMESTAMP WITH TIME ZONE,
      duration_ms     NUMBER,
      status          VARCHAR2(20)  NOT NULL,
      result_json     CLOB,
      error_message   VARCHAR2(4000),
      triggered_by    VARCHAR2(20)  DEFAULT 'scheduler',
      CONSTRAINT ck_sched_job_exec_status CHECK (status IN ('running','success','failed'))
    )
  ]';
EXCEPTION
  WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_job_exec_job_started ON scheduler_job_executions(job_id, started_at DESC)';
EXCEPTION
  WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_job_exec_started ON scheduler_job_executions(started_at DESC)';
EXCEPTION
  WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

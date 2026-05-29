from sqlalchemy import TIMESTAMP, CheckConstraint, Column, Integer, Numeric, String, Text, text

from database import Base


class SchedulerJobExecution(Base):
    """Histórico de execução de rotinas (APScheduler jobs + triggers event-driven).

    Alimentada pelo wrapper `tasks._job_wrapper.tracked_job` e consumida pela tela
    `/monitoring/jobs`. Retenção: 30 dias (job `prune_job_executions`).
    """

    __tablename__ = "scheduler_job_executions"

    id = Column(Integer, primary_key=True)
    job_id = Column(String(80), nullable=False, index=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("SYSTIMESTAMP"))
    finished_at = Column(TIMESTAMP(timezone=True))
    duration_ms = Column(Numeric)
    status = Column(String(20), nullable=False)  # running | success | failed
    result_json = Column(Text)
    error_message = Column(String(4000))
    triggered_by = Column(String(20), server_default=text("'scheduler'"))  # scheduler | event | manual

    __table_args__ = (
        CheckConstraint("status IN ('running','success','failed')", name="ck_sched_job_exec_status"),
    )

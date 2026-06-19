from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, Numeric, String, Text, text

from database import Base


class CompetitorAnalysis(Base):
    """Estudo de Análise de Concorrência (ML + IA) por produto PG/CMIG.

    Persistido para reaproveitar como contexto/memória em estudos futuros do mesmo
    produto e para o usuário comentar (notes) e excluir/refazer."""

    __tablename__ = "competitor_analyses"

    id = Column(Integer, primary_key=True)
    requester_user_id = Column(Integer, ForeignKey("users.id"))
    product_type = Column(String(10), nullable=False)  # 'pg' | 'cmig'
    product_id = Column(Integer, nullable=False)
    account_id = Column(Integer, ForeignKey("marketplace_accounts.id"))
    desired_margin_pct = Column(Numeric(6, 2))
    status = Column(String(20), nullable=False, default="running")  # running | done | error
    progress_step = Column(String(160))
    user_prompt = Column(Text)   # comentário/prompt do usuário ANTES de iniciar
    result_json = Column(Text)   # estudo final + dados brutos do ML (reutilizável)
    notes = Column(Text)         # anotações do usuário DEPOIS (memória p/ estudos futuros)
    error = Column(String(2000))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    finished_at = Column(TIMESTAMP(timezone=True))

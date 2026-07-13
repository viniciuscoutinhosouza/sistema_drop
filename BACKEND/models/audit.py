from sqlalchemy import TIMESTAMP, Column, Integer, String, Text, text

from database import Base


class AuditEvent(Base):
    """Trilha de ações destrutivas — QUEM apagou o quê, quando e de onde.

    Nasceu do sumiço repetido dos anúncios importados (4 episódios): os DELETEs eram legítimos
    (login válido), mas o sistema não guardava o autor — só sobrava o IP no log do servidor.
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    user_email = Column(String(255))
    action = Column(String(60), nullable=False)       # ex: 'anuncio.delete'
    entity_type = Column(String(40), nullable=False)  # ex: 'product_listing'
    entity_id = Column(String(60))
    details = Column(Text)                            # snapshot (JSON) do que foi apagado
    ip = Column(String(64))
    user_agent = Column(String(400))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

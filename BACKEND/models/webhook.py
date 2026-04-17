from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, text
from database import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True)
    platform = Column(String(20), nullable=False)
    event_id = Column(String(200), nullable=False)
    event_type = Column(String(100))
    payload = Column(String)   # CLOB JSON
    processed = Column(Boolean, nullable=False, default=False)
    error_message = Column(String(1000))
    received_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    processed_at = Column(TIMESTAMP(timezone=True))

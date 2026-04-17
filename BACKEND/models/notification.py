from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey, text
from database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(50))
    title = Column(String(200), nullable=False)
    body = Column(String(1000))
    reference_type = Column(String(50))
    reference_id = Column(Integer)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

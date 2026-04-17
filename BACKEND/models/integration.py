from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey, text
from database import Base


class MarketplaceIntegration(Base):
    __tablename__ = "marketplace_integrations"

    id = Column(Integer, primary_key=True)
    dropshipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String(20), nullable=False)
    description = Column(String(200))
    access_token = Column(String(2000))
    refresh_token = Column(String(2000))
    token_expires_at = Column(TIMESTAMP(timezone=True))
    platform_user_id = Column(String(200))
    platform_username = Column(String(200))
    shop_id = Column(Integer)
    api_key = Column(String(500))
    is_active = Column(Boolean, nullable=False, default=True)
    last_sync_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

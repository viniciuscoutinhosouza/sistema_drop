from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, text, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base


class NFeConfig(Base):
    """Regra de emissão de NF-e por método de envio em uma CM."""
    __tablename__ = "nfe_configs"

    id              = Column(Integer, primary_key=True)
    cm_id           = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    shipping_method = Column(String(100), nullable=False)
    issuer          = Column(String(20), nullable=False)  # marketplace | system
    notes           = Column(String(500))
    created_at      = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at      = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                             onupdate=text("SYSTIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("cm_id", "shipping_method", name="uq_nfecfg"),
    )

    cm = relationship("MarketplaceAccount", back_populates="nfe_configs")

from sqlalchemy import Column, Integer, Boolean, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base


class GO(Base):
    """Gestor Operacional — pessoa física dona de um Galpão (Warehouse)."""
    __tablename__ = "goes"

    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at   = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                          onupdate=text("SYSTIMESTAMP"))

    user       = relationship("User", back_populates="go_profile", foreign_keys=[user_id])
    warehouse  = relationship("Warehouse", foreign_keys=[warehouse_id], post_update=True)
    warehouses = relationship("Warehouse", back_populates="go", foreign_keys="Warehouse.go_id")

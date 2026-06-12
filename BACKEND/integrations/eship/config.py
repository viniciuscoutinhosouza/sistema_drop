"""Model e helpers de configuração do eShip por galpão (warehouse)."""

from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, Integer, String, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import Base


class EShipConfig(Base):
    """Config do eShip por galpão. Opt-in: só usa se is_active=True e com base_url+api_key."""

    __tablename__ = "eship_config"

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False, unique=True)
    base_url = Column(String(500))
    api_key = Column(String(500))
    is_active = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    @property
    def usable(self) -> bool:
        return bool(self.is_active and self.base_url and self.api_key)


async def get_config(db: AsyncSession, warehouse_id: int) -> EShipConfig | None:
    if not warehouse_id:
        return None
    res = await db.execute(
        select(EShipConfig).where(EShipConfig.warehouse_id == warehouse_id)
    )
    return res.scalar_one_or_none()


async def get_active_config(db: AsyncSession, warehouse_id: int) -> EShipConfig | None:
    """Config utilizável (ativa e com credenciais) ou None."""
    cfg = await get_config(db, warehouse_id)
    return cfg if (cfg and cfg.usable) else None

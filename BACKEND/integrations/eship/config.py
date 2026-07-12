"""Config do eShip.

A partir da spec (apikey única por empresa), a fonte de verdade das credenciais é a
CMIG (empresa): `eship_base_url`, `eship_api_key`, `eship_warehouse_code`, `eship_active`.
A tabela `eship_config` por galpão é legada (mantida por compatibilidade).
"""

from dataclasses import dataclass

from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, Integer, String, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import Base
from models.cmig import CMIG


@dataclass
class EShipCreds:
    """Credenciais resolvidas para chamar o eShip (duck-types com EShipConfig:
    o client usa apenas .base_url e .api_key)."""

    base_url: str | None
    api_key: str | None
    warehouse_code: str | None = None
    cnpj: str | None = None
    # Cadastro da empresa no eShip (migration 125) — opcionais no payload da ordem.
    id_tipo: int | None = None       # idTipo
    tipo_ordem: str | None = None    # tipoOrdem

    @property
    def usable(self) -> bool:
        return bool(self.base_url and self.api_key)


def creds_from_cmig(cmig: CMIG) -> EShipCreds | None:
    """Credenciais eShip a partir da CMIG (ativa e com base_url+api_key) ou None."""
    if not cmig or not getattr(cmig, "eship_active", 0):
        return None
    creds = EShipCreds(
        base_url=cmig.eship_base_url,
        api_key=cmig.eship_api_key,
        warehouse_code=cmig.eship_warehouse_code,
        cnpj=cmig.cnpj,
        id_tipo=getattr(cmig, "eship_id_tipo", None),
        tipo_ordem=getattr(cmig, "eship_tipo_ordem", None),
    )
    return creds if creds.usable else None


async def get_cmig_creds(db: AsyncSession, cmig_id: int) -> EShipCreds | None:
    """Carrega a CMIG e devolve as credenciais eShip utilizáveis (ou None)."""
    if not cmig_id:
        return None
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    return creds_from_cmig(cmig) if cmig else None


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

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, text

from database import Base


class AppConfig(Base):
    """Config GLOBAL do sistema em chave/valor (uma linha por chave). Para ajustes simples que
    não têm tabela de domínio própria — ex.: `separation.finish_photos_code` (código que o
    operador bipa para encerrar as fotos no modo Bipagem automática). Global (não por galpão)."""

    __tablename__ = "app_config"

    key = Column(String(100), primary_key=True)
    value = Column(String(1000))
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, Text, text

from database import Base


class GoogleDriveAccount(Base):
    """Conexão OAuth do Google Drive — no máximo UMA ativa por vez (armazenamento de imagens).

    Guarda os tokens: o `refresh_token` fica CIFRADO em repouso (Fernet, services/crypto); o
    `access_token` é curto (1h) e renovado pelo refresh. A raiz é a pasta `Ecommerce_Imagens`
    (criada via API ao conectar); subpastas por área são criadas sob ela sob demanda.
    """

    __tablename__ = "google_drive_accounts"

    id = Column(Integer, primary_key=True)
    email = Column(String(255))
    refresh_token_enc = Column(Text, nullable=False)  # cifrado (Fernet)
    access_token = Column(Text)  # curto (1h) — renovado pelo refresh
    expires_at = Column(TIMESTAMP(timezone=True))
    root_folder_id = Column(String(100))
    root_folder_name = Column(String(255))
    scope = Column(String(300))
    is_active = Column(Integer, nullable=False, default=1)  # 0|1 — uma ativa por vez
    connected_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    last_used_at = Column(TIMESTAMP(timezone=True))
    last_error = Column(String(1000))
    created_by = Column(Integer, ForeignKey("users.id"))

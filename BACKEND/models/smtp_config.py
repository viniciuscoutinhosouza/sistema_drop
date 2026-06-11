from sqlalchemy import TIMESTAMP, Boolean, Column, Integer, String, text

from database import Base


class SMTPConfig(Base):
    """Configuração do servidor de e-mail (SMTP) — singleton.

    Usada para enviar o código OTP de vínculo de conta de marketplace e demais
    e-mails transacionais. Apenas admin edita. A senha é guardada como os demais
    segredos do sistema (tokens) — em texto no banco.
    """

    __tablename__ = "smtp_config"

    id = Column(Integer, primary_key=True)
    host = Column(String(255))
    port = Column(Integer, default=587)
    username = Column(String(255))
    password = Column(String(500))
    use_tls = Column(Boolean, default=True)   # STARTTLS (porta 587)
    use_ssl = Column(Boolean, default=False)  # SSL direto (porta 465)
    from_email = Column(String(255))
    from_name = Column(String(255))
    is_active = Column(Boolean, default=False)
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

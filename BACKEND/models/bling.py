from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, Text, UniqueConstraint, text

from database import Base


class CMIGBlingAccount(Base):
    """Conexão OAuth2 (Bling API v3) de UMA CMIG com a conta Bling dela.

    É por-CMIG (o Bling é o ERP da empresa, não um canal de venda) — espelha o padrão da
    integração Google Drive (ADR-0038): tokens CIFRADOS em repouso (Fernet, `services/crypto`),
    tabela dedicada, renovação pelo refresh. Diferença: aqui há UMA conexão POR CMIG
    (`cmig_id` UNIQUE) e o escopo de acesso deriva da CMIG (`assert_cmig_access`), não é
    admin-global.

    O `access_token`/`refresh_token` do Bling ficam CIFRADOS (coluna `*_enc`). O refresh_token do
    Bling expira em ~30 dias e ROTACIONA a cada refresh — por isso o refresh grava o novo par.
    Tokens podem ser grandes (o Bling migra token opaco → JWT) → colunas CLOB (Text).
    """

    __tablename__ = "cmig_bling_accounts"

    id = Column(Integer, primary_key=True)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    # Credenciais do app Bling CONFIGURÁVEIS por CMIG (migration 181). Opcional: se ausentes, usa o
    # app padrão do .env (BLING_CLIENT_ID/SECRET). client_id não é segredo; o secret fica CIFRADO.
    client_id = Column(String(200))
    client_secret_enc = Column(String(2000))     # cifrado (Fernet) — nunca em claro
    access_token_enc = Column(Text)              # cifrado (Fernet) — curto (~6h)
    refresh_token_enc = Column(Text)             # cifrado (Fernet) — ~30 dias, rotaciona no refresh
    token_expires_at = Column(TIMESTAMP(timezone=True))
    scope = Column(String(500))
    bling_company_id = Column(String(100))       # id da empresa no Bling (do GET /empresas)
    bling_company_name = Column(String(255))     # razão social/nome da empresa no Bling
    connected_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    last_used_at = Column(TIMESTAMP(timezone=True))
    last_error = Column(String(1000))
    connected_by_user_id = Column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        # Uma conexão Bling por CMIG. A reconexão faz UPDATE in-place (upsert), nunca 2ª linha.
        UniqueConstraint("cmig_id", name="uq_bling_cmig"),
    )

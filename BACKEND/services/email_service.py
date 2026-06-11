"""Serviço de e-mail (SMTP) — usa a config singleton em smtp_config.

Usa smtplib da stdlib (sem dependência nova), rodando o envio bloqueante em
asyncio.to_thread para não travar o event loop (mesmo padrão do AsyncSyncSession).
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.smtp_config import SMTPConfig

logger = logging.getLogger(__name__)


async def get_config(db: AsyncSession) -> SMTPConfig | None:
    """Retorna a config SMTP (singleton) ou None."""
    res = await db.execute(select(SMTPConfig).order_by(SMTPConfig.id).limit(1))
    return res.scalar_one_or_none()


def _send_sync(cfg: SMTPConfig, to: str, subject: str, html: str, text: str | None) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    from_addr = cfg.from_email or cfg.username
    msg["From"] = f"{cfg.from_name} <{from_addr}>" if cfg.from_name else from_addr
    msg["To"] = to
    msg.set_content(text or "Seu cliente de e-mail não suporta HTML.")
    msg.add_alternative(html, subtype="html")

    port = int(cfg.port or (465 if cfg.use_ssl else 587))
    ctx = ssl.create_default_context()
    if cfg.use_ssl:
        with smtplib.SMTP_SSL(cfg.host, port, timeout=20, context=ctx) as s:
            if cfg.username:
                s.login(cfg.username, cfg.password or "")
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.host, port, timeout=20) as s:
            s.ehlo()
            if cfg.use_tls:
                s.starttls(context=ctx)
                s.ehlo()
            if cfg.username:
                s.login(cfg.username, cfg.password or "")
            s.send_message(msg)


async def send_email(
    db: AsyncSession, to: str, subject: str, html: str, text: str | None = None
) -> None:
    """Envia um e-mail usando a config ativa. Levanta exceção em erro de envio
    ou se o SMTP não estiver configurado/ativo (útil para o botão "Enviar teste")."""
    cfg = await get_config(db)
    if not cfg or not cfg.is_active:
        raise RuntimeError("Servidor de e-mail não configurado ou inativo.")
    if not cfg.host or not cfg.from_email:
        raise RuntimeError("Configuração SMTP incompleta (host/remetente).")
    await asyncio.to_thread(_send_sync, cfg, to, subject, html, text)


async def send_otp_email(
    db: AsyncSession, to: str, code: str, platform: str, expires_minutes: int = 15
) -> bool:
    """Envia o código OTP por e-mail. Retorna True se enviou; False se o SMTP não
    está configurado ou se o envio falhou (o chamador pode cair no fallback de log).
    Nunca levanta — não deve quebrar o cadastro da conta."""
    plat = {"mercadolivre": "Mercado Livre", "shopee": "Shopee", "bling": "Bling"}.get(
        platform, platform
    )
    subject = f"Seu código de verificação — {plat}"
    html = f"""\
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#2c3e50">Código de verificação</h2>
      <p>Use o código abaixo para confirmar o vínculo da sua conta <strong>{plat}</strong>:</p>
      <div style="font-size:32px;font-weight:bold;letter-spacing:6px;
                  background:#f4f4f4;padding:16px;text-align:center;border-radius:8px;margin:16px 0">
        {code}
      </div>
      <p style="color:#888;font-size:13px">Válido por {expires_minutes} minutos.
      Se você não solicitou, ignore este e-mail.</p>
      <hr style="border:none;border-top:1px solid #eee">
      <p style="color:#aaa;font-size:12px">MIG ECOMMERCE — Sistema Drop</p>
    </div>"""
    text = f"Seu código de verificação ({plat}): {code}\nVálido por {expires_minutes} minutos."
    try:
        await send_email(db, to, subject, html, text)
        return True
    except Exception as e:
        logger.warning("[email] Falha ao enviar OTP para %s: %s", to, e)
        return False

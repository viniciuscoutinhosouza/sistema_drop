"""Configuração do servidor de e-mail (SMTP) — apenas admin.

Tela: Configurações → Servidor de E-mail. Usado para enviar o OTP de vínculo
de conta de marketplace.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.smtp_config import SMTPConfig
from models.user import User
from services import email_service

router = APIRouter()


def _serialize(cfg: SMTPConfig | None) -> dict:
    if not cfg:
        return {
            "host": "",
            "port": 587,
            "username": "",
            "password_set": False,
            "use_tls": True,
            "use_ssl": False,
            "from_email": "",
            "from_name": "",
            "is_active": False,
        }
    return {
        "host": cfg.host or "",
        "port": cfg.port or 587,
        "username": cfg.username or "",
        "password_set": bool(cfg.password),  # nunca devolve a senha em si
        "use_tls": bool(cfg.use_tls),
        "use_ssl": bool(cfg.use_ssl),
        "from_email": cfg.from_email or "",
        "from_name": cfg.from_name or "",
        "is_active": bool(cfg.is_active),
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


async def _get_or_create(db: AsyncSession) -> SMTPConfig:
    cfg = (
        await db.execute(select(SMTPConfig).order_by(SMTPConfig.id).limit(1))
    ).scalar_one_or_none()
    if not cfg:
        cfg = SMTPConfig()
        db.add(cfg)
        await db.flush()
    return cfg


@router.get("")
async def get_email_config(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    cfg = (
        await db.execute(select(SMTPConfig).order_by(SMTPConfig.id).limit(1))
    ).scalar_one_or_none()
    return _serialize(cfg)


@router.put("")
async def update_email_config(
    body: dict,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_or_create(db)

    # Campos simples
    for field in ("host", "username", "from_email", "from_name"):
        if field in body:
            setattr(cfg, field, (body.get(field) or "").strip())
    if "port" in body and body["port"]:
        try:
            cfg.port = int(body["port"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Porta inválida")
    for flag in ("use_tls", "use_ssl", "is_active"):
        if flag in body:
            setattr(cfg, flag, bool(body[flag]))

    # Senha só é atualizada se vier um valor não-vazio (evita apagar ao editar).
    pwd = body.get("password")
    if pwd:
        cfg.password = pwd

    await db.commit()
    await db.refresh(cfg)
    return _serialize(cfg)


@router.post("/test")
async def test_email_config(
    body: dict,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Envia um e-mail de teste para o endereço informado usando a config salva."""
    to = (body.get("to") or "").strip()
    if not to:
        raise HTTPException(status_code=422, detail="Informe o e-mail de destino do teste")
    try:
        await email_service.send_email(
            db,
            to,
            "Teste de configuração de e-mail — Sistema Drop",
            "<p>Se você recebeu este e-mail, o servidor SMTP está configurado "
            "corretamente. ✅</p><p>MIG ECOMMERCE — Sistema Drop</p>",
            "Servidor SMTP configurado corretamente. MIG ECOMMERCE — Sistema Drop",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar: {e}")
    return {"message": f"E-mail de teste enviado para {to}"}

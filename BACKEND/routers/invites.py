"""Convites de colaborador — endpoints PÚBLICOS (sem autenticação).

O convidado acessa /invites/{token} para ver o convite e /invites/{token}/register
para criar seu cadastro (usuário inativo, aguardando liberação do admin geral).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.cmig import CMIG
from models.user import User, UserInvite
from services.auth_service import hash_password

router = APIRouter()


@router.get("/{token}")
async def get_invite(token: str, db: AsyncSession = Depends(get_db)):
    """Valida o token e retorna dados do convite para a tela pública de cadastro."""
    invite = (
        await db.execute(select(UserInvite).where(UserInvite.token == token))
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Convite não encontrado")
    if invite.status == "pending_registration":
        pass
    elif invite.status == "pending_approval":
        raise HTTPException(status_code=409, detail="Cadastro já realizado — aguarde a liberação do administrador.")
    elif invite.status == "active":
        raise HTTPException(status_code=409, detail="Convite já concluído. Faça login normalmente.")
    else:
        raise HTTPException(status_code=410, detail="Convite expirado ou cancelado.")

    empresa = None
    if invite.cmig_id:
        cmig = (await db.execute(select(CMIG).where(CMIG.id == invite.cmig_id))).scalar_one_or_none()
        empresa = (cmig.company_name or cmig.trade_name) if cmig else None
    return {"email": invite.email, "company_name": empresa, "status": invite.status}


@router.post("/{token}/register", status_code=201)
async def register_via_invite(token: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Cria o usuário (AC INATIVO) a partir do convite. Aguarda liberação do admin."""
    invite = (
        await db.execute(select(UserInvite).where(UserInvite.token == token))
    ).scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Convite não encontrado")
    if invite.status != "pending_registration":
        raise HTTPException(status_code=409, detail="Este convite não está mais aberto para cadastro.")

    full_name = (body.get("full_name") or "").strip()
    password = body.get("password") or ""
    whatsapp = (body.get("whatsapp") or "").strip() or None
    if not full_name:
        raise HTTPException(status_code=422, detail="Informe seu nome completo")
    if len(password) < 6:
        raise HTTPException(status_code=422, detail="A senha deve ter ao menos 6 caracteres")

    # E-mail não pode já existir (corrida entre convite e cadastro manual)
    dup = (
        await db.execute(select(User).where(func.lower(User.email) == invite.email.lower()))
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail.")

    # Herda galpão/GO do usuário que convidou (contexto operacional)
    inviter = (
        await db.execute(select(User).where(User.id == invite.invited_by_user_id))
    ).scalar_one_or_none()

    user = User(
        email=invite.email,
        password_hash=hash_password(password),
        full_name=full_name,
        whatsapp=whatsapp,
        role="ac",
        is_active=False,  # aguarda liberação do administrador geral
        warehouse_id=inviter.warehouse_id if inviter else None,
        go_id=inviter.go_id if inviter else None,
    )
    db.add(user)
    await db.flush()

    invite.user_id = user.id
    invite.status = "pending_approval"
    await db.commit()
    return {
        "ok": True,
        "message": "Cadastro realizado! Aguarde a liberação do administrador para acessar o sistema.",
    }

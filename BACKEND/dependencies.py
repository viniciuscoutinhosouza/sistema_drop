from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from services.auth_service import verify_token
from models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = verify_token(token) if token else None
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )
    return user


def require_role(*roles: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissão insuficiente",
            )
        return current_user
    return checker


async def get_active_ac(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Retorna o usuário atual se for um AC ativo com assinatura em dia."""
    from models.user import ACProfile
    from datetime import date

    if current_user.role not in ("ac",):
        raise HTTPException(status_code=403, detail="Acesso apenas para Gestores de Conta (AC)")

    result = await db.execute(
        select(ACProfile).where(ACProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if profile and profile.subscription_status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Mensalidade vencida. Regularize seu plano para continuar.",
        )
    return current_user


async def get_active_ugo(
    current_user: User = Depends(get_current_user),
) -> User:
    """Retorna o usuário atual se for um Operador Logístico (UGO) ativo."""
    if current_user.role not in ("ugo", "admin"):
        raise HTTPException(status_code=403, detail="Acesso apenas para Operadores Logísticos (UGO)")
    return current_user


async def get_ac_or_ugo(
    current_user: User = Depends(get_current_user),
) -> User:
    """Permite acesso tanto para AC quanto para UGO/admin."""
    if current_user.role not in ("ac", "ugo", "admin"):
        raise HTTPException(status_code=403, detail="Acesso não autorizado")
    return current_user

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserProfile
from services.auth_service import verify_token

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


async def _resolve_user_menu_keys(user: User, db: AsyncSession) -> set[str]:
    """Resolve as menu_keys efetivas de um usuário.

    Mesmo algoritmo usado em auth._resolve_user_menu_permissions (login/refresh)
    pra que UI e backend autorizem pelos mesmos critérios:
      1. user.profile_id setado e ativo → usa as menu_keys desse perfil
      2. Fallback: perfil de sistema (is_system=1, is_active=1) com mesmo base_role
      3. Vazio se nada casar
    """
    if user.profile_id:
        r = await db.execute(select(UserProfile).where(UserProfile.id == user.profile_id))
        up = r.scalar_one_or_none()
        if up and up.is_active:
            return {m.menu_key for m in (up.menu_permissions or [])}

    if user.role:
        r = await db.execute(
            select(UserProfile).where(
                UserProfile.base_role == user.role,
                UserProfile.is_system == 1,
                UserProfile.is_active == 1,
            )
        )
        up = r.scalar_one_or_none()
        if up:
            return {m.menu_key for m in (up.menu_permissions or [])}

    return set()


def require_menu_permission(menu_key: str):
    """Autoriza pela menu_key efetiva do usuário (perfil + fallback do role).

    Admin sempre passa, independente do perfil. Para os demais papéis, exige
    que a menu_key esteja na lista resolvida por _resolve_user_menu_keys.
    """
    async def checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.role == "admin":
            return current_user
        keys = await _resolve_user_menu_keys(current_user, db)
        if menu_key not in keys:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sem permissão de menu '{menu_key}'. Solicite ao administrador.",
            )
        return current_user

    return checker


async def get_active_ac(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Retorna o usuário atual se for um AC ativo com assinatura em dia."""

    from models.user import ACProfile

    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Acesso apenas para Gestores de Conta (AC)")

    result = await db.execute(select(ACProfile).where(ACProfile.user_id == current_user.id))
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
        raise HTTPException(
            status_code=403, detail="Acesso apenas para Operadores Logísticos (UGO)"
        )
    return current_user


async def get_ac_or_ugo(
    current_user: User = Depends(get_current_user),
) -> User:
    """Permite acesso tanto para AC quanto para UGO/admin."""
    if current_user.role not in ("ac", "ugo", "admin"):
        raise HTTPException(status_code=403, detail="Acesso não autorizado")
    return current_user


async def get_active_go(
    current_user: User = Depends(get_current_user),
) -> User:
    """Retorna o usuário atual se for um GO ativo."""
    if current_user.role not in ("go", "admin"):
        raise HTTPException(status_code=403, detail="Acesso apenas para Gestores Operacionais (GO)")
    return current_user


async def require_warehouse_scope(
    warehouse_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """Valida se o UGO pertence ao galpão solicitado."""
    if current_user.role == "admin":
        return True
    if current_user.role in ("ugo", "go") and current_user.warehouse_id == warehouse_id:
        return True
    raise HTTPException(status_code=403, detail="Acesso negado a este Galpão")

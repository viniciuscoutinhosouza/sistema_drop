import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models.user import ACProfile, RefreshToken, User, UserProfile
from schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterACRequest,
    RegisterUGORequest,
    TokenResponse,
)
from services.auth_service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory rate limiter: {ip: [datetime, ...]}
_login_attempts: dict[str, list[datetime]] = defaultdict(list)
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(ip: str) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=_RATE_LIMIT_WINDOW)
    attempts = [t for t in _login_attempts[ip] if t > cutoff]
    if len(attempts) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 1 minuto.")
    attempts.append(now)
    _login_attempts[ip] = attempts


@router.post("/token", include_in_schema=False)
async def oauth2_token(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2-compatible login usado pelo Swagger UI."""
    _check_rate_limit(request.client.host if request.client else "unknown")
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada")
    access_token = create_access_token(user.id, user.role)
    return {"access_token": access_token, "token_type": "bearer"}


async def _resolve_user_menu_permissions(user: User, db: AsyncSession) -> tuple[int | None, str | None, list[str]]:
    """Resolve as menu_permissions efetivas de um usuário.

    Ordem:
      1. Se user.profile_id setado → usa esse perfil
      2. Fallback: perfil de sistema com mesmo base_role do usuário
         (usuários antigos sem profile_id herdam do perfil-template do role)
      3. Nenhum casa → retorna lista vazia (frontend cai no fallback hardcoded)

    Returns: (profile_id_efetivo, profile_name, menu_keys)
    """
    profile_id: int | None = user.profile_id
    if profile_id:
        r = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
        up = r.scalar_one_or_none()
        if up and up.is_active:
            keys = sorted([m.menu_key for m in (up.menu_permissions or [])])
            return up.id, up.label, keys

    # Fallback: perfil de sistema com mesmo base_role
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
            keys = sorted([m.menu_key for m in (up.menu_permissions or [])])
            return up.id, up.label, keys

    return None, None, []


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    _check_rate_limit(request.client.host if request.client else "unknown")
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada")

    access_token = create_access_token(user.id, user.role)
    refresh_token_str, refresh_expires = create_refresh_token(user.id)

    db_refresh = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=refresh_expires,
    )
    db.add(db_refresh)
    await db.commit()

    profile_id, profile_name, menu_permissions = await _resolve_user_menu_permissions(user, db)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        dark_mode=user.dark_mode,
        go_id=user.go_id,
        warehouse_id=user.warehouse_id,
        profile_id=profile_id,
        profile_name=profile_name,
        menu_permissions=menu_permissions,
    )


@router.post("/register/ugo", status_code=201)
async def register_ugo(
    body: RegisterUGORequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "go")),
):
    """Cadastra um novo Operador Logístico (UGO). Admin ou GO podem executar."""
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    # GO só pode criar UGO em seus próprios Galpões
    warehouse_id = body.warehouse_id
    go_id = current_user.go_id if current_user.role == "go" else None

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        whatsapp=body.whatsapp,
        role="ugo",
        warehouse_id=warehouse_id,
        go_id=go_id,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as e:
        await db.rollback()
        err_str = str(e).lower()
        if "unique" in err_str or "dup_val" in err_str:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        if "check constraint" in err_str or "ck_" in err_str or "chk_" in err_str:
            logger.exception("Constraint de role ao cadastrar UGO — execute migration 16")
            raise HTTPException(status_code=500, detail="Erro interno ao cadastrar usuário")
        logger.exception("IntegrityError ao cadastrar UGO")
        raise HTTPException(status_code=500, detail="Erro interno ao cadastrar usuário")

    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/register/ac", response_model=TokenResponse, status_code=201)
async def register_ac(
    body: RegisterACRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """Cadastra um novo Gestor de Conta (AC). Apenas UGO ou Admin podem executar."""
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    if body.cpf_cnpj:
        result = await db.execute(select(User).where(User.cpf_cnpj == body.cpf_cnpj))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="CPF/CNPJ já cadastrado")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        whatsapp=body.whatsapp,
        cpf_cnpj=body.cpf_cnpj,
        role="ac",
        warehouse_id=current_user.warehouse_id,  # herda o galpão do UGO que cadastra
        go_id=current_user.go_id,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        err_str = str(e).lower()
        if "unique" in err_str or "dup_val" in err_str:
            raise HTTPException(status_code=400, detail="E-mail ou CPF/CNPJ já cadastrado")
        logger.exception("IntegrityError no flush ao cadastrar AC")
        raise HTTPException(status_code=500, detail="Erro interno ao cadastrar usuário")

    profile = ACProfile(
        user_id=user.id,
        zip_code=body.zip_code,
        street=body.street,
        address_number=body.number,
        complement=body.complement,
        neighborhood=body.neighborhood,
        city=body.city,
        state=body.state,
        plan_id=body.plan_id,
    )
    db.add(profile)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        logger.exception("IntegrityError no commit do perfil AC")
        raise HTTPException(status_code=500, detail="Erro interno ao cadastrar usuário")

    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = verify_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == body.refresh_token,
            RefreshToken.revoked == False,
        )
    )
    db_token = result.scalar_one_or_none()
    if not db_token:
        raise HTTPException(status_code=401, detail="Refresh token revogado ou não encontrado")

    expires_at = db_token.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at and expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Refresh token expirado")

    result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inativo")

    db_token.revoked = True
    access_token = create_access_token(user.id, user.role)
    new_refresh_str, new_refresh_expires = create_refresh_token(user.id)

    db.add(RefreshToken(user_id=user.id, token=new_refresh_str, expires_at=new_refresh_expires))
    await db.commit()

    profile_id_refresh, profile_name_refresh, menu_permissions_refresh = await _resolve_user_menu_permissions(user, db)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_str,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        dark_mode=user.dark_mode,
        go_id=user.go_id,
        warehouse_id=user.warehouse_id,
        profile_id=profile_id_refresh,
        profile_name=profile_name_refresh,
        menu_permissions=menu_permissions_refresh,
    )


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == body.refresh_token))
    db_token = result.scalar_one_or_none()
    if db_token:
        db_token.revoked = True
        await db.commit()


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()

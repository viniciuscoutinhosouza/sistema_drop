from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.user import User, DropshipperProfile, RefreshToken
from schemas.auth import LoginRequest, RegisterRequest, TokenResponse, RefreshRequest, ChangePasswordRequest
from services.auth_service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, verify_token
)
from dependencies import get_current_user
from datetime import datetime, timezone

router = APIRouter()


@router.post("/token", include_in_schema=False)
async def oauth2_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2-compatible login used by Swagger UI Authorize button."""
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada")
    access_token = create_access_token(user.id, user.role)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
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

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        dark_mode=user.dark_mode,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    # Check CPF/CNPJ uniqueness
    result = await db.execute(select(User).where(User.cpf_cnpj == body.cpf_cnpj))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="CPF/CNPJ já cadastrado")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        whatsapp=body.whatsapp,
        cpf_cnpj=body.cpf_cnpj,
        role="dropshipper",
    )
    db.add(user)
    await db.flush()  # Get user.id before committing

    profile = DropshipperProfile(
        user_id=user.id,
        zip_code=body.zip_code,
        street=body.street,
        number=body.number,
        complement=body.complement,
        neighborhood=body.neighborhood,
        city=body.city,
        state=body.state,
    )
    db.add(profile)

    access_token = create_access_token(user.id, user.role)
    refresh_token_str, refresh_expires = create_refresh_token(user.id)

    db_refresh = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=refresh_expires,
    )
    db.add(db_refresh)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        dark_mode=False,
    )


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

    if db_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expirado")

    result = await db.execute(select(User).where(User.id == db_token.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inativo")

    # Revoke old token and issue new pair
    db_token.revoked = True
    access_token = create_access_token(user.id, user.role)
    new_refresh_str, new_refresh_expires = create_refresh_token(user.id)

    new_db_refresh = RefreshToken(
        user_id=user.id,
        token=new_refresh_str,
        expires_at=new_refresh_expires,
    )
    db.add(new_db_refresh)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_str,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        dark_mode=user.dark_mode,
    )


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == body.refresh_token)
    )
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

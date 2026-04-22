from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from database import get_db
from models.user import User, ACProfile, RefreshToken
from schemas.auth import (
    LoginRequest, RegisterUGORequest, RegisterACRequest,
    TokenResponse, RefreshRequest, ChangePasswordRequest,
)
from services.auth_service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, verify_token
)
from dependencies import get_current_user, require_role
from datetime import datetime, timezone

router = APIRouter()


@router.post("/token", include_in_schema=False)
async def oauth2_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2-compatible login usado pelo Swagger UI."""
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
        go_id=user.go_id,
        warehouse_id=user.warehouse_id,
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
            raise HTTPException(
                status_code=500,
                detail="Erro de banco de dados: constraint de role inválida. Execute o script de migração 16_migration_v3_multi_go_cmig.sql."
            )
        raise HTTPException(status_code=500, detail=f"Erro de banco de dados: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"Erro de banco de dados: {str(e)}")

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
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro de banco de dados: {str(e)}")

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

    if db_token.expires_at < datetime.now(timezone.utc):
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

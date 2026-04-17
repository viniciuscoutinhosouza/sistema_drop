from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import get_current_user
from models.user import User, DropshipperProfile
from schemas.user import ProfileOut, ProfileUpdate, AddressSchema, PreferencesUpdate
from services.viacep_service import fetch_address
from services.auth_service import hash_password, verify_password
from schemas.auth import ChangePasswordRequest

router = APIRouter()


@router.get("/me", response_model=ProfileOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DropshipperProfile).where(DropshipperProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    out = ProfileOut(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        whatsapp=current_user.whatsapp,
        cpf_cnpj=current_user.cpf_cnpj,
        role=current_user.role,
        dark_mode=current_user.dark_mode,
        created_at=current_user.created_at,
    )

    if profile:
        out.address = AddressSchema(
            zip_code=profile.zip_code or "",
            street=profile.street or "",
            number=profile.number or "",
            complement=profile.complement or "",
            neighborhood=profile.neighborhood or "",
            city=profile.city or "",
            state=profile.state or "",
        )
        out.subscription_status = profile.subscription_status
        out.subscription_due_date = profile.subscription_due_date
        out.balance = profile.balance

    return out


@router.put("/me", response_model=ProfileOut)
async def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.whatsapp is not None:
        current_user.whatsapp = body.whatsapp
    await db.commit()
    await db.refresh(current_user)
    return await get_me(current_user, db)


@router.put("/me/address")
async def update_address(
    body: AddressSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DropshipperProfile).where(DropshipperProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = DropshipperProfile(user_id=current_user.id)
        db.add(profile)

    profile.zip_code = body.zip_code
    profile.street = body.street
    profile.number = body.number
    profile.complement = body.complement
    profile.neighborhood = body.neighborhood
    profile.city = body.city
    profile.state = body.state
    await db.commit()
    return {"message": "Endereço atualizado com sucesso"}


@router.put("/me/preferences")
async def update_preferences(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.dark_mode = body.dark_mode
    await db.commit()
    return {"dark_mode": current_user.dark_mode}


@router.get("/address/lookup/{cep}")
async def lookup_cep(cep: str):
    """Proxy to ViaCEP – avoids CORS issues from the browser."""
    return await fetch_address(cep)

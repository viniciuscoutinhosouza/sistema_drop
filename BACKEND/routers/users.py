from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import get_current_user, require_role, get_active_ugo
from models.user import User, ACProfile, AccessPlan
from schemas.user import ProfileOut, ProfileUpdate, AddressSchema, PreferencesUpdate
from services.viacep_service import fetch_address
from services.auth_service import hash_password, verify_password
from schemas.auth import ChangePasswordRequest

router = APIRouter()


# ─── Perfil do usuário autenticado ───────────────────────────────────────────

@router.get("/me", response_model=ProfileOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ACProfile).where(ACProfile.user_id == current_user.id)
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
            number=profile.address_number or "",
            complement=profile.complement or "",
            neighborhood=profile.neighborhood or "",
            city=profile.city or "",
            state=profile.state or "",
        )
        out.subscription_status = profile.subscription_status
        out.subscription_due_date = profile.subscription_due_date

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
        select(ACProfile).where(ACProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        profile = ACProfile(user_id=current_user.id)
        db.add(profile)

    profile.zip_code = body.zip_code
    profile.street = body.street
    profile.address_number = body.number
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
    """Proxy para ViaCEP — evita CORS no browser."""
    return await fetch_address(cep)


# ─── Listagem de usuários (UGO/Admin) ────────────────────────────────────────

@router.get("")
async def list_users(
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """Lista usuários. UGO lista apenas ACs; Admin lista todos."""
    query = select(User).where(User.is_active == True)

    if current_user.role == "ugo":
        query = query.where(User.role == "ac")
    elif role:
        query = query.where(User.role == role)

    result = await db.execute(query.order_by(User.full_name))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "whatsapp": u.whatsapp,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    profile_result = await db.execute(select(ACProfile).where(ACProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "whatsapp": user.whatsapp,
        "cpf_cnpj": user.cpf_cnpj,
        "role": user.role,
        "is_active": user.is_active,
        "dark_mode": user.dark_mode,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "profile": {
            "zip_code": profile.zip_code,
            "street": profile.street,
            "number": profile.address_number,
            "complement": profile.complement,
            "neighborhood": profile.neighborhood,
            "city": profile.city,
            "state": profile.state,
            "subscription_status": profile.subscription_status,
            "subscription_due_date": profile.subscription_due_date.isoformat() if profile.subscription_due_date else None,
            "plan_id": profile.plan_id,
        } if profile else None,
    }


@router.put("/{user_id}/deactivate", status_code=204)
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Não é possível desativar o administrador")
    user.is_active = False
    await db.commit()


@router.put("/{user_id}/plan")
async def update_ac_plan(
    user_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """Atualiza o plano de acesso de um AC."""
    result = await db.execute(select(User).where(User.id == user_id, User.role == "ac"))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Gestor de Conta não encontrado")

    plan_id = body.get("plan_id")
    if plan_id:
        plan_result = await db.execute(select(AccessPlan).where(AccessPlan.id == plan_id, AccessPlan.is_active == True))
        if not plan_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Plano não encontrado")

    profile_result = await db.execute(select(ACProfile).where(ACProfile.user_id == user_id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil do AC não encontrado")

    profile.plan_id = plan_id
    await db.commit()
    return {"message": "Plano atualizado com sucesso"}


# ─── Gestão de Planos de Acesso (Admin) ──────────────────────────────────────

@router.get("/plans/access")
async def list_plans(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(
        select(AccessPlan).where(AccessPlan.is_active == True).order_by(AccessPlan.monthly_price)
    )
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "max_accounts": p.max_accounts,
            "monthly_price": float(p.monthly_price),
        }
        for p in plans
    ]


@router.post("/plans/access", status_code=201)
async def create_plan(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    plan = AccessPlan(
        name=body["name"],
        max_accounts=body["max_accounts"],
        monthly_price=body["monthly_price"],
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id, "name": plan.name}


@router.put("/plans/access/{plan_id}")
async def update_plan(
    plan_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(AccessPlan).where(AccessPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano não encontrado")
    for field in ["name", "max_accounts", "monthly_price"]:
        if field in body:
            setattr(plan, field, body[field])
    await db.commit()
    return {"ok": True}

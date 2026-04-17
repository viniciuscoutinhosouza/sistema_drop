import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from dependencies import get_current_user
from models.user import User
from models.integration import MarketplaceIntegration
from services import ml_service, shopee_service, bling_service
from config import get_settings

settings = get_settings()
router = APIRouter()

# In-memory state store for OAuth CSRF protection
# In production, use Redis with TTL
_oauth_states: dict[str, int] = {}


@router.get("")
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketplaceIntegration).where(MarketplaceIntegration.dropshipper_id == current_user.id)
    )
    integrations = result.scalars().all()
    return [
        {
            "id": i.id,
            "platform": i.platform,
            "description": i.description,
            "platform_username": i.platform_username,
            "is_active": i.is_active,
            "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in integrations
    ]


# ─── Mercado Livre ────────────────────────────────────────────────────────────

@router.get("/ml/authorize")
async def ml_authorize(current_user: User = Depends(get_current_user)):
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = current_user.id
    url = ml_service.get_authorization_url(state)
    return {"auth_url": url}


@router.get("/ml/callback")
async def ml_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido ou expirado")

    token_data = await ml_service.exchange_code(code)
    user_info = await ml_service.get_user_info(token_data["access_token"])

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 21600))

    # Upsert integration
    result = await db.execute(
        select(MarketplaceIntegration).where(
            MarketplaceIntegration.dropshipper_id == user_id,
            MarketplaceIntegration.platform == "mercadolivre",
            MarketplaceIntegration.platform_user_id == str(user_info.get("id")),
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.access_token = token_data["access_token"]
        integration.refresh_token = token_data.get("refresh_token")
        integration.token_expires_at = expires_at
        integration.is_active = True
    else:
        integration = MarketplaceIntegration(
            dropshipper_id=user_id,
            platform="mercadolivre",
            description=f"ML – {user_info.get('nickname', '')}",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=expires_at,
            platform_user_id=str(user_info.get("id")),
            platform_username=user_info.get("nickname"),
        )
        db.add(integration)

    await db.commit()
    frontend_url = f"{settings.FRONTEND_URL}/oauth/success?platform=mercadolivre&status=connected"
    return RedirectResponse(frontend_url)


@router.delete("/ml/{integration_id}", status_code=204)
async def ml_disconnect(
    integration_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketplaceIntegration).where(
            MarketplaceIntegration.id == integration_id,
            MarketplaceIntegration.dropshipper_id == current_user.id,
            MarketplaceIntegration.platform == "mercadolivre",
        )
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.is_active = False
        await db.commit()


# ─── Shopee ───────────────────────────────────────────────────────────────────

@router.get("/shopee/authorize")
async def shopee_authorize(current_user: User = Depends(get_current_user)):
    url = shopee_service.get_authorization_url(settings.SHOPEE_REDIRECT_URI)
    return {"auth_url": url}


@router.get("/shopee/callback")
async def shopee_callback(
    code: str,
    shop_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Note: Shopee callback doesn't return state – use shop_id as identifier
    # In production, associate shop_id with a pending auth session from Redis
    token_data = await shopee_service.exchange_code(code, shop_id)

    # We need to know which dropshipper initiated – store state in Redis in production
    # For now, raise error if no pending session found
    raise HTTPException(
        status_code=501,
        detail="Shopee callback: implementar controle de sessão OAuth com Redis para associar shop_id ao dropshipper"
    )


@router.delete("/shopee/{integration_id}", status_code=204)
async def shopee_disconnect(
    integration_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketplaceIntegration).where(
            MarketplaceIntegration.id == integration_id,
            MarketplaceIntegration.dropshipper_id == current_user.id,
            MarketplaceIntegration.platform == "shopee",
        )
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.is_active = False
        await db.commit()


# ─── Bling ────────────────────────────────────────────────────────────────────

@router.post("/bling")
async def bling_connect(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    api_key = body.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key é obrigatório")

    await bling_service.validate_api_key(api_key)

    result = await db.execute(
        select(MarketplaceIntegration).where(
            MarketplaceIntegration.dropshipper_id == current_user.id,
            MarketplaceIntegration.platform == "bling",
        )
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.api_key = api_key
        integration.is_active = True
    else:
        integration = MarketplaceIntegration(
            dropshipper_id=current_user.id,
            platform="bling",
            description=body.get("description", "Bling V3"),
            api_key=api_key,
        )
        db.add(integration)

    await db.commit()
    return {"message": "Bling conectado com sucesso"}


@router.delete("/bling/{integration_id}", status_code=204)
async def bling_disconnect(
    integration_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketplaceIntegration).where(
            MarketplaceIntegration.id == integration_id,
            MarketplaceIntegration.dropshipper_id == current_user.id,
            MarketplaceIntegration.platform == "bling",
        )
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.is_active = False
        await db.commit()

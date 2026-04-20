"""
Gestão de CONTAs de Marketplace (antigo: integrations).

Uma CONTA é identificada unicamente por (platform, email, phone).
Pode ser co-administrada por múltiplos ACs via AccountAdministrator.
"""
import secrets
import random
import string
from datetime import datetime, timezone, timedelta


def _trunc_bytes(s: str, max_bytes: int) -> str:
    """Truncate string so its UTF-8 encoding fits within max_bytes."""
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from dependencies import get_current_user, get_active_ac, require_role
from models.user import User, AccountAdministrator
from models.integration import MarketplaceAccount, AccountBalance, OTPVerification
from models.product import DropshipperProduct, ProductListing
from services import ml_service, shopee_service, bling_service
from config import get_settings

settings = get_settings()
router = APIRouter()

# In-memory state store para CSRF do OAuth (produção: use Redis com TTL)
_oauth_states: dict[str, dict] = {}


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


async def _assert_ac_can_access(account_id: int, user_id: int, db: AsyncSession) -> MarketplaceAccount:
    """Verifica se o usuário é co-administrador da CONTA."""
    result = await db.execute(
        select(MarketplaceAccount)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .where(
            MarketplaceAccount.id == account_id,
            AccountAdministrator.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada ou sem permissão")
    return account


def _serialize_account(acc: MarketplaceAccount, is_owner: bool = False) -> dict:
    return {
        "id": acc.id,
        "platform": acc.platform,
        "description": acc.description,
        "email": acc.email,
        "phone": acc.phone,
        "platform_username": acc.platform_username,
        "is_active": acc.is_active,
        "otp_verified": acc.otp_verified,
        "is_owner": is_owner,
        "last_sync_at": acc.last_sync_at.isoformat() if acc.last_sync_at else None,
        "created_at": acc.created_at.isoformat() if acc.created_at else None,
    }


# ─── Listar CONTAs do AC ──────────────────────────────────────────────────────

@router.get("")
async def list_accounts(
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Lista todas as CONTAs que o AC co-administra."""
    result = await db.execute(
        select(MarketplaceAccount, AccountAdministrator.is_owner)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .where(AccountAdministrator.user_id == current_user.id)
        .order_by(MarketplaceAccount.created_at)
    )
    return [_serialize_account(acc, is_owner) for acc, is_owner in result.all()]


# ─── Criar CONTA com verificação OTP ─────────────────────────────────────────

@router.post("", status_code=201)
async def create_account(
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """
    Cria/registra uma nova CONTA de marketplace.
    Body: platform, description, email, phone
    Após criação, o sistema envia OTP para confirmar o vínculo.
    """
    platform = body.get("platform")
    email = body.get("email", "")
    phone = body.get("phone", "")
    description = body.get("description", "")

    if not platform:
        raise HTTPException(status_code=400, detail="platform é obrigatório")

    # Verificar duplicata pelo identificador único (platform + email + phone)
    dup = await db.execute(
        select(MarketplaceAccount).where(
            MarketplaceAccount.platform == platform,
            MarketplaceAccount.email == email,
            MarketplaceAccount.phone == phone,
        )
    )
    existing = dup.scalar_one_or_none()
    if existing:
        # Conta já existe — verificar se este AC já é co-admin
        admin_check = await db.execute(
            select(AccountAdministrator).where(
                AccountAdministrator.account_id == existing.id,
                AccountAdministrator.user_id == current_user.id,
            )
        )
        if admin_check.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Você já administra esta conta")
        # Adicionar este AC como co-admin (sem OTP duplicado)
        db.add(AccountAdministrator(
            user_id=current_user.id,
            account_id=existing.id,
            is_owner=False,
        ))
        await db.commit()
        return {"id": existing.id, "message": "Conta vinculada como co-administrador"}

    # Nova CONTA
    account = MarketplaceAccount(
        owner_id=current_user.id,
        platform=platform,
        description=description,
        email=email,
        phone=phone,
        otp_verified=False,
    )
    db.add(account)
    await db.flush()

    # Criar saldo operacional zerado
    db.add(AccountBalance(account_id=account.id))

    # Registrar AC como owner e primeiro administrador
    db.add(AccountAdministrator(
        user_id=current_user.id,
        account_id=account.id,
        is_owner=True,
    ))

    # Gerar OTP de verificação
    otp_code = _generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.add(OTPVerification(
        account_id=account.id,
        code=otp_code,
        channel="email",
        destination=email,
        expires_at=expires,
    ))

    await db.commit()

    # DEV: exibe o OTP no log do backend até SMTP estar configurado
    print(f"\n{'='*50}")
    print(f"  OTP para conta '{email}' [{platform}]: {otp_code}")
    print(f"  Válido por 15 minutos.")
    print(f"{'='*50}\n")

    return {
        "id": account.id,
        "message": "Conta criada. Verifique o e-mail/WhatsApp para confirmar o vínculo.",
        "otp_required": True,
    }


@router.post("/{account_id}/verify-otp")
async def verify_otp(
    account_id: int,
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Confirma o vínculo da CONTA via código OTP."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    code = body.get("code", "").strip()

    otp_result = await db.execute(
        select(OTPVerification).where(
            OTPVerification.account_id == account_id,
            OTPVerification.code == code,
            OTPVerification.is_used == False,
        )
    )
    otp = otp_result.scalar_one_or_none()
    if not otp:
        # DEV: mostrar OTPs ativos para diagnóstico
        all_otps = await db.execute(
            select(OTPVerification).where(
                OTPVerification.account_id == account_id,
                OTPVerification.is_used == False,
            )
        )
        active = all_otps.scalars().all()
        if active:
            print(f"\n[OTP DEBUG] Códigos ativos para account_id={account_id}:")
            for o in active:
                print(f"  código={o.code}  expira={o.expires_at}  canal={o.channel}")
            print()
        else:
            print(f"\n[OTP DEBUG] Nenhum OTP ativo para account_id={account_id}\n")
        raise HTTPException(status_code=400, detail="Código OTP inválido")
    expires = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Código OTP expirado")

    otp.is_used = True
    account.otp_verified = True
    await db.commit()
    return {"message": "Conta verificada com sucesso"}


@router.post("/{account_id}/resend-otp")
async def resend_otp(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Gera um novo OTP e invalida os anteriores."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if account.otp_verified:
        raise HTTPException(status_code=400, detail="Conta já verificada")

    # Invalidar OTPs anteriores
    old_otps = await db.execute(
        select(OTPVerification).where(
            OTPVerification.account_id == account_id,
            OTPVerification.is_used == False,
        )
    )
    for old in old_otps.scalars().all():
        old.is_used = True

    otp_code = _generate_otp()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.add(OTPVerification(
        account_id=account_id,
        code=otp_code,
        channel="email",
        destination=account.email or "",
        expires_at=expires,
    ))
    await db.commit()

    print(f"\n{'='*50}")
    print(f"  NOVO OTP para conta '{account.email}' [{account.platform}]: {otp_code}")
    print(f"  Válido por 15 minutos.")
    print(f"{'='*50}\n")

    return {"message": "Novo código OTP gerado. Verifique o log do backend."}


# ─── Co-administração ─────────────────────────────────────────────────────────

@router.post("/{account_id}/admins")
async def add_co_admin(
    account_id: int,
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona outro AC como co-administrador desta CONTA."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)

    target_user_id = body.get("user_id")
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id é obrigatório")

    target_result = await db.execute(
        select(User).where(User.id == target_user_id, User.role == "ac", User.is_active == True)
    )
    if not target_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Gestor de Conta não encontrado")

    dup = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == target_user_id,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Usuário já é administrador desta conta")

    db.add(AccountAdministrator(
        user_id=target_user_id,
        account_id=account_id,
        is_owner=False,
    ))
    await db.commit()
    return {"message": "Co-administrador adicionado com sucesso"}


@router.delete("/{account_id}/admins/{user_id}", status_code=204)
async def remove_co_admin(
    account_id: int,
    user_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Remove um co-administrador desta CONTA (apenas owner pode fazer isso)."""
    # Verificar que o solicitante é o owner
    owner_check = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == current_user.id,
            AccountAdministrator.is_owner == True,
        )
    )
    if not owner_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Apenas o owner pode remover co-administradores")

    result = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == user_id,
            AccountAdministrator.is_owner == False,
        )
    )
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Co-administrador não encontrado")
    await db.delete(admin)
    await db.commit()


# ─── Detalhes e desconexão ────────────────────────────────────────────────────

@router.get("/{account_id}")
async def get_account(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    owner_check = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == current_user.id,
            AccountAdministrator.is_owner == True,
        )
    )
    return _serialize_account(account, is_owner=bool(owner_check.scalar_one_or_none()))


@router.put("/{account_id}")
async def update_account(
    account_id: int,
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if "description" in body:
        account.description = body["description"]
    await db.commit()
    return {"ok": True}


@router.delete("/{account_id}", status_code=204)
async def disconnect_account(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Desativa uma CONTA (apenas owner pode fazer isso)."""
    owner_check = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == current_user.id,
            AccountAdministrator.is_owner == True,
        )
    )
    if not owner_check.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Apenas o owner pode desativar a conta")

    result = await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    account.is_active = False
    await db.commit()


# ─── OAuth – Mercado Livre ────────────────────────────────────────────────────

@router.get("/{account_id}/ml/authorize")
async def ml_authorize(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    await _assert_ac_can_access(account_id, current_user.id, db)
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = {"user_id": current_user.id, "account_id": account_id}
    url = ml_service.get_authorization_url(state)
    return {"auth_url": url}


@router.get("/ml/callback")
async def ml_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    ctx = _oauth_states.pop(state, None)
    if not ctx:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido ou expirado")

    account_id = ctx["account_id"]
    token_data = await ml_service.exchange_code(code)
    user_info = await ml_service.get_user_info(token_data["access_token"])
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 21600))

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    account.access_token = token_data["access_token"]
    account.refresh_token = token_data.get("refresh_token")
    account.token_expires_at = expires_at
    account.platform_user_id = str(user_info.get("id"))
    account.platform_username = user_info.get("nickname")
    account.is_active = True
    await db.commit()

    frontend_url = f"{settings.FRONTEND_URL}/oauth/success?platform=mercadolivre&status=connected"
    return RedirectResponse(frontend_url)


# ─── OAuth – Shopee ───────────────────────────────────────────────────────────

@router.get("/{account_id}/shopee/authorize")
async def shopee_authorize(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    await _assert_ac_can_access(account_id, current_user.id, db)
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = {"user_id": current_user.id, "account_id": account_id}
    redirect_uri_with_state = f"{settings.SHOPEE_REDIRECT_URI}?state={state}"
    url = shopee_service.get_authorization_url(redirect_uri_with_state)
    return {"auth_url": url}


@router.get("/shopee/callback")
async def shopee_callback(
    code: str,
    state: str,
    shop_id: int = Query(None),
    shopid: int = Query(None),
    db: AsyncSession = Depends(get_db),
):
    resolved_shop_id = shop_id or shopid
    if not resolved_shop_id:
        raise HTTPException(status_code=400, detail="shop_id ausente no callback Shopee")

    ctx = _oauth_states.pop(state, None)
    if not ctx:
        raise HTTPException(status_code=400, detail="Estado OAuth inválido ou expirado")

    account_id = ctx["account_id"]
    token_data = await shopee_service.exchange_code(code, resolved_shop_id)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expire_in", 14400))

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    account.access_token = token_data["access_token"]
    account.refresh_token = token_data.get("refresh_token")
    account.token_expires_at = expires_at
    account.platform_user_id = str(resolved_shop_id)
    account.shop_id = resolved_shop_id
    account.is_active = True
    await db.commit()

    frontend_url = f"{settings.FRONTEND_URL}/oauth/success?platform=shopee&status=connected"
    return RedirectResponse(frontend_url)


# ─── Sincronização manual ─────────────────────────────────────────────────────

@router.post("/{account_id}/sync-orders")
async def sync_orders_now(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Dispara sincronização de pedidos imediatamente para esta conta."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if not account.access_token:
        raise HTTPException(status_code=400, detail="Conta sem token de acesso. Faça o OAuth primeiro.")

    from tasks.sync_orders import _sync_ml_integration, _sync_shopee_integration
    if account.platform == "mercadolivre":
        await _sync_ml_integration(db, account)
    elif account.platform == "shopee":
        await _sync_shopee_integration(db, account)
    else:
        raise HTTPException(status_code=400, detail="Sincronização não disponível para esta plataforma.")

    return {"message": "Sincronização de pedidos concluída."}


@router.post("/{account_id}/import-listings")
async def import_listings(
    account_id: int,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    """Importa todos os anúncios ativos desta conta do Mercado Livre."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Importação de anúncios disponível apenas para Mercado Livre.")
    if not account.access_token or not account.platform_user_id:
        raise HTTPException(status_code=400, detail="Conta sem token ou ID. Faça o OAuth primeiro.")

    # 1. Buscar todos os IDs de anúncios ativos
    item_ids = await ml_service.get_seller_item_ids(account.access_token, account.platform_user_id)
    if not item_ids:
        return {"imported": 0, "updated": 0, "message": "Nenhum anúncio ativo encontrado no Mercado Livre."}

    # 2. Buscar detalhes em lote
    items = await ml_service.get_items_bulk(account.access_token, item_ids)

    imported, updated = 0, 0
    for item in items:
        ml_id       = str(item.get("id", ""))
        title       = item.get("title", "")[:500]
        price       = float(item.get("price") or 0)
        category    = item.get("category_id", "")
        listing_type = item.get("listing_type_id", "")
        thumbnail   = item.get("thumbnail", "")
        pictures    = item.get("pictures", [])

        # 3. Verificar se produto já existe pelo ml_item_id
        res = await db.execute(
            select(DropshipperProduct).where(
                DropshipperProduct.dropshipper_id == current_user.id,
                DropshipperProduct.ml_item_id == ml_id,
            )
        )
        product = res.scalar_one_or_none()

        if not product:
            product = DropshipperProduct(
                dropshipper_id=current_user.id,
                title=title,
                title_ml=_trunc_bytes(title, 60),
                sale_price_ml=price,
                ml_item_id=ml_id,
                ml_category_id=category,
                ml_listing_type=listing_type,
                status="active",
            )
            db.add(product)
            await db.flush()
            imported += 1
        else:
            product.title_ml = _trunc_bytes(title, 60)
            product.sale_price_ml = price
            product.ml_category_id = category
            updated += 1

        # 4. Criar ou atualizar ProductListing
        res2 = await db.execute(
            select(ProductListing).where(
                ProductListing.product_id == product.id,
                ProductListing.account_id == account_id,
            )
        )
        listing = res2.scalar_one_or_none()
        if not listing:
            db.add(ProductListing(
                product_id=product.id,
                account_id=account_id,
                platform_item_id=ml_id,
                sale_price=price,
                category_id=category,
                listing_type=listing_type,
                status="published",
                published_at=datetime.now(timezone.utc),
                last_sync_at=datetime.now(timezone.utc),
            ))
        else:
            listing.sale_price = price
            listing.platform_item_id = ml_id
            listing.status = "published"
            listing.last_sync_at = datetime.now(timezone.utc)

    await db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "total": len(items),
        "message": f"{imported} anúncios importados, {updated} atualizados.",
    }


# ─── Bling ────────────────────────────────────────────────────────────────────

@router.post("/{account_id}/bling/connect")
async def bling_connect(
    account_id: int,
    body: dict,
    current_user: User = Depends(get_active_ac),
    db: AsyncSession = Depends(get_db),
):
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    api_key = body.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key é obrigatório")
    await bling_service.validate_api_key(api_key)
    account.api_key = api_key
    account.is_active = True
    await db.commit()
    return {"message": "Bling conectado com sucesso"}

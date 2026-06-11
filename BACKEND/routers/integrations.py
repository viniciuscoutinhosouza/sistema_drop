"""
Gestão de CONTAs de Marketplace (antigo: integrations).

Uma CONTA é identificada unicamente por (platform, email, phone).
Pode ser co-administrada por múltiplos ACs via AccountAdministrator.
"""

import random
import secrets
import string
from datetime import UTC, datetime, timedelta


def _trunc_bytes(s: str, max_bytes: int) -> str:
    """Truncate string so its UTF-8 encoding fits within max_bytes."""
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.cmig import CMIGAdministrator
from models.integration import AccountBalance, MarketplaceAccount, OTPVerification
from models.product import DropshipperProduct, ProductListing
from models.user import AccountAdministrator, User
from services import bling_service, ml_service, shopee_service

settings = get_settings()
router = APIRouter()

# In-memory state store para CSRF do OAuth (produção: use Redis com TTL)
_oauth_states: dict[str, dict] = {}


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


async def _assert_ac_can_access(
    account_id: int, user_id: int, db: AsyncSession
) -> MarketplaceAccount:
    """Verifica se o usuário pode acessar a CONTA.

    Aceita dois caminhos:
    1. Usuário é AccountAdministrator direto da conta.
    2. Usuário é CMIGAdministrator de uma CMIG vinculada à conta.
    """
    result = await db.execute(
        select(MarketplaceAccount)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .where(
            MarketplaceAccount.id == account_id,
            AccountAdministrator.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if account:
        return account

    # Fallback: acesso via CMIGAdministrator → conta vinculada à CMIG do usuário
    result2 = await db.execute(
        select(MarketplaceAccount)
        .join(CMIGAdministrator, MarketplaceAccount.cmig_id == CMIGAdministrator.cmig_id)
        .where(
            MarketplaceAccount.id == account_id,
            CMIGAdministrator.user_id == user_id,
        )
    )
    account = result2.scalar_one_or_none()
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
        "is_official_store": bool(acc.is_official_store),
        "otp_verified": acc.otp_verified,
        "is_owner": is_owner,
        "cmig_id": acc.cmig_id,
        "requires_reauth": bool(acc.requires_reauth),
        "last_sync_at": acc.last_sync_at.isoformat() if acc.last_sync_at else None,
        "power_seller_status": acc.power_seller_status,
        "level_id": acc.level_id,
        "reputation_cached_at": acc.reputation_cached_at.isoformat()
        if acc.reputation_cached_at
        else None,
        "has_flex": acc.effective_has_flex,
        "has_full": acc.effective_has_full,
        "has_flex_detected": bool(acc.has_flex),
        "has_full_detected": bool(acc.has_full),
        "has_flex_override": acc.has_flex_override,
        "has_full_override": acc.has_full_override,
        "shipping_modes_checked_at": acc.shipping_modes_checked_at.isoformat()
        if acc.shipping_modes_checked_at
        else None,
        "created_at": acc.created_at.isoformat() if acc.created_at else None,
    }


# ─── Listar CONTAs do AC ──────────────────────────────────────────────────────


@router.get("")
async def list_accounts(
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    """Lista as CONTAs visíveis ao usuário. Admin vê todas; AC vê as que
    co-administra ou que pertencem às suas CMIGs."""
    # Super Admin: vê TODAS as contas (incluindo as vinculadas a qualquer CMIG).
    if current_user.role == "admin":
        result = await db.execute(
            select(MarketplaceAccount).order_by(MarketplaceAccount.created_at)
        )
        return [_serialize_account(acc, True) for acc in result.scalars().all()]

    # Contas com vínculo direto via AccountAdministrator
    result = await db.execute(
        select(MarketplaceAccount, AccountAdministrator.is_owner)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .where(AccountAdministrator.user_id == current_user.id)
        .order_by(MarketplaceAccount.created_at)
    )
    accounts: dict[int, tuple[MarketplaceAccount, bool]] = {
        acc.id: (acc, is_owner) for acc, is_owner in result.all()
    }

    # Contas vinculadas às CMIGs que o usuário administra (colaborador CMIG)
    cmig_ids_result = await db.execute(
        select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == current_user.id)
    )
    cmig_ids = [row[0] for row in cmig_ids_result.all()]
    if cmig_ids:
        already_loaded = list(accounts.keys())
        q = select(MarketplaceAccount).where(MarketplaceAccount.cmig_id.in_(cmig_ids))
        if already_loaded:
            q = q.where(MarketplaceAccount.id.notin_(already_loaded))
        result2 = await db.execute(q.order_by(MarketplaceAccount.created_at))
        for acc in result2.scalars().all():
            accounts[acc.id] = (acc, False)

    return [_serialize_account(acc, is_owner) for acc, is_owner in accounts.values()]


# ─── Criar CONTA com verificação OTP ─────────────────────────────────────────


@router.post("", status_code=201)
async def create_account(
    body: dict,
    current_user: User = Depends(require_menu_permission("integrations")),
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
        db.add(
            AccountAdministrator(
                user_id=current_user.id,
                account_id=existing.id,
                is_owner=False,
            )
        )
        await db.commit()
        return {"id": existing.id, "message": "Conta vinculada como co-administrador"}

    # Nova CONTA — inativa até completar OAuth
    account = MarketplaceAccount(
        owner_id=current_user.id,
        platform=platform,
        description=description,
        email=email,
        phone=phone,
        cmig_id=body.get("cmig_id") or None,
        otp_verified=False,
        is_active=False,
    )
    db.add(account)
    await db.flush()

    # Criar saldo operacional zerado
    db.add(AccountBalance(account_id=account.id))

    # Registrar AC como owner e primeiro administrador
    db.add(
        AccountAdministrator(
            user_id=current_user.id,
            account_id=account.id,
            is_owner=True,
        )
    )

    # Gerar OTP de verificação
    otp_code = _generate_otp()
    expires = datetime.now(UTC) + timedelta(minutes=15)
    db.add(
        OTPVerification(
            account_id=account.id,
            code=otp_code,
            channel="email",
            destination=email,
            expires_at=expires,
        )
    )

    await db.commit()

    # DEV: exibe o OTP no log do backend até SMTP estar configurado
    print(f"\n{'=' * 50}")
    print(f"  OTP para conta '{email}' [{platform}]: {otp_code}")
    print("  Válido por 15 minutos.")
    print(f"{'=' * 50}\n")

    return {
        "id": account.id,
        "message": "Conta criada. Verifique o e-mail/WhatsApp para confirmar o vínculo.",
        "otp_required": True,
    }


@router.post("/{account_id}/verify-otp")
async def verify_otp(
    account_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("integrations")),
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
    expires = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Código OTP expirado")

    otp.is_used = True
    account.otp_verified = True
    await db.commit()
    return {"message": "Conta verificada com sucesso"}


@router.post("/{account_id}/resend-otp")
async def resend_otp(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
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
    expires = datetime.now(UTC) + timedelta(minutes=15)
    db.add(
        OTPVerification(
            account_id=account_id,
            code=otp_code,
            channel="email",
            destination=account.email or "",
            expires_at=expires,
        )
    )
    await db.commit()

    print(f"\n{'=' * 50}")
    print(f"  NOVO OTP para conta '{account.email}' [{account.platform}]: {otp_code}")
    print("  Válido por 15 minutos.")
    print(f"{'=' * 50}\n")

    return {"message": "Novo código OTP gerado. Verifique o log do backend."}


# ─── Co-administração ─────────────────────────────────────────────────────────


async def _assert_owner_or_admin(
    account_id: int, user: User, db: AsyncSession
) -> MarketplaceAccount:
    """Garante que o usuário é o owner da conta OU admin da plataforma.
    Retorna a conta se autorizado; caso contrário 403/404."""
    acc_q = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = acc_q.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    if user.role == "admin":
        return account
    owner_q = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == user.id,
            AccountAdministrator.is_owner == True,
        )
    )
    if not owner_q.scalar_one_or_none():
        raise HTTPException(
            status_code=403, detail="Apenas o proprietário da conta pode realizar esta ação"
        )
    return account


@router.get("/{account_id}/admins")
async def list_account_admins(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista colaboradores desta conta (acessível ao owner, co-admins e admin)."""
    # Acesso a leitura: qualquer co-admin da conta OU admin da plataforma
    if current_user.role != "admin":
        await _assert_ac_can_access(account_id, current_user.id, db)

    result = await db.execute(
        select(AccountAdministrator, User)
        .join(User, AccountAdministrator.user_id == User.id)
        .where(AccountAdministrator.account_id == account_id)
        .order_by(AccountAdministrator.is_owner.desc(), User.full_name)
    )
    return [
        {
            "user_id": admin.user_id,
            "is_owner": admin.is_owner,
            "full_name": user.full_name,
            "email": user.email,
        }
        for admin, user in result.all()
    ]


@router.post("/{account_id}/admins")
async def add_co_admin(
    account_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona outro AC como co-administrador desta CONTA (owner ou admin)."""
    await _assert_owner_or_admin(account_id, current_user, db)

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

    db.add(
        AccountAdministrator(
            user_id=target_user_id,
            account_id=account_id,
            is_owner=False,
        )
    )
    await db.commit()
    return {"message": "Co-administrador adicionado com sucesso"}


@router.delete("/{account_id}/admins/{user_id}", status_code=204)
async def remove_co_admin(
    account_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove um co-administrador desta CONTA (apenas owner ou admin)."""
    await _assert_owner_or_admin(account_id, current_user, db)

    result = await db.execute(
        select(AccountAdministrator).where(
            AccountAdministrator.account_id == account_id,
            AccountAdministrator.user_id == user_id,
            AccountAdministrator.is_owner == False,
        )
    )
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(
            status_code=404, detail="Co-administrador não encontrado ou é o proprietário"
        )
    db.delete(admin)
    await db.commit()


# ─── Detalhes e desconexão ────────────────────────────────────────────────────


@router.get("/{account_id}")
async def get_account(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
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


# ─── Capacidades de envio (Flex, Full) ────────────────────────────────────────

SHIPPING_CAPS_TTL_HOURS = 24


async def _refresh_shipping_capabilities(
    account: MarketplaceAccount, db: AsyncSession
) -> MarketplaceAccount:
    """Re-detecta has_flex/has_full chamando a API ML e atualiza o registro.

    Why isolado: chamado tanto pelo GET (com lógica de cache) quanto pelo POST refresh.
    """
    from routers.anuncios import _get_valid_token  # evita import circular

    if account.platform != "mercadolivre":
        return account
    if not account.platform_user_id:
        return account

    access_token = await _get_valid_token(account, db)
    caps = await ml_service.detect_shipping_capabilities(access_token, account.platform_user_id)
    account.has_flex = caps.get("has_flex", False)
    account.has_full = caps.get("has_full", False)
    account.shipping_modes_checked_at = datetime.now(UTC)
    await db.commit()
    return account


@router.get("/{account_id}/shipping-capabilities")
async def get_shipping_capabilities(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna capacidades de envio (Flex, Full) detectadas + override manual.

    Auto-redetecta se o cache expirou (TTL 24h). Usar POST .../refresh para forçar.
    """
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if account.platform != "mercadolivre":
        return {
            "has_flex": False,
            "has_full": False,
            "has_flex_override": None,
            "has_full_override": None,
            "shipping_modes_checked_at": None,
            "stale": False,
        }

    checked_at = account.shipping_modes_checked_at
    if checked_at and checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    stale = (
        checked_at is None
        or (datetime.now(UTC) - checked_at) > timedelta(hours=SHIPPING_CAPS_TTL_HOURS)
    )

    if stale:
        try:
            await _refresh_shipping_capabilities(account, db)
        except Exception:
            pass  # falha de detecção não bloqueia leitura — devolve último valor conhecido

    return {
        "has_flex": account.effective_has_flex,
        "has_full": account.effective_has_full,
        "has_flex_detected": bool(account.has_flex),
        "has_full_detected": bool(account.has_full),
        "has_flex_override": account.has_flex_override,
        "has_full_override": account.has_full_override,
        "shipping_modes_checked_at": account.shipping_modes_checked_at.isoformat()
        if account.shipping_modes_checked_at
        else None,
    }


@router.post("/{account_id}/shipping-capabilities/refresh")
async def refresh_shipping_capabilities(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    """Força redetecção das capacidades agora (ignora cache)."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    await _refresh_shipping_capabilities(account, db)
    return {
        "has_flex": account.effective_has_flex,
        "has_full": account.effective_has_full,
        "has_flex_detected": bool(account.has_flex),
        "has_full_detected": bool(account.has_full),
        "shipping_modes_checked_at": account.shipping_modes_checked_at.isoformat()
        if account.shipping_modes_checked_at
        else None,
    }


@router.put("/{account_id}/shipping-capabilities")
async def set_shipping_capabilities_override(
    account_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    """Override manual: admin força has_flex/has_full ignorando a auto-detecção.

    Body: {"has_flex_override": true|false|null, "has_full_override": true|false|null}
    null limpa o override (volta a usar o valor detectado).
    """
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if "has_flex_override" in body:
        v = body["has_flex_override"]
        account.has_flex_override = bool(v) if v is not None else None
    if "has_full_override" in body:
        v = body["has_full_override"]
        account.has_full_override = bool(v) if v is not None else None
    await db.commit()
    return {
        "has_flex": account.effective_has_flex,
        "has_full": account.effective_has_full,
        "has_flex_override": account.has_flex_override,
        "has_full_override": account.has_full_override,
    }


@router.put("/{account_id}")
async def update_account(
    account_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if "description" in body:
        account.description = body["description"]
    if "cmig_id" in body:
        account.cmig_id = body["cmig_id"] or None
    if "is_official_store" in body:
        account.is_official_store = bool(body["is_official_store"])
    await db.commit()
    return {"ok": True}


@router.delete("/{account_id}", status_code=204)
async def disconnect_account(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
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

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    account.is_active = False
    await db.commit()


# ─── OAuth – Mercado Livre ────────────────────────────────────────────────────


@router.get("/{account_id}/ml/authorize")
async def ml_authorize(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
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
    expires_at = datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 21600))

    seller_id = str(user_info.get("id") or "")
    token_nick = user_info.get("nickname") or ""
    token_email = (user_info.get("email") or "").lower().strip()

    result = await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # ── Isolamento: garante que o vendedor autorizado é o DESTA conta ──
    # A tela de autorização do ML reaproveita a sessão logada no navegador; sem
    # esta checagem, autorizar com outra conta ML aberta no browser vincularia o
    # token ao vendedor errado (CMIG "misturada" com a conta logada).
    account_email = (account.email or "").lower().strip()
    mismatch = None
    if account.platform_user_id and seller_id and account.platform_user_id != seller_id:
        mismatch = (
            f"Esperado o vendedor ID {account.platform_user_id}, mas você autorizou "
            f"'{token_nick or token_email or seller_id}'."
        )
    elif account_email and token_email and account_email != token_email:
        mismatch = (
            f"Esperado o e-mail {account_email}, mas você autorizou '{token_email}'."
        )

    if mismatch:
        # NÃO sobrescreve a conta. Redireciona com instrução clara.
        from urllib.parse import quote

        detail = quote(
            f"{mismatch} Saia do Mercado Livre no navegador (ou use uma aba anônima) "
            "e reconecte a conta correta."
        )
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/oauth/success"
            f"?platform=mercadolivre&status=wrong_account&detail={detail}"
        )

    account.access_token = token_data["access_token"]
    account.refresh_token = token_data.get("refresh_token")
    account.token_expires_at = expires_at
    account.platform_user_id = seller_id
    account.platform_username = token_nick
    account.is_active = True
    account.requires_reauth = False
    await db.commit()

    from urllib.parse import quote

    connected = quote(token_nick or token_email or seller_id)
    frontend_url = (
        f"{settings.FRONTEND_URL}/oauth/success"
        f"?platform=mercadolivre&status=connected&seller={connected}"
    )
    return RedirectResponse(frontend_url)


# ─── OAuth – Shopee ───────────────────────────────────────────────────────────


@router.get("/{account_id}/shopee/authorize")
async def shopee_authorize(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
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
    expires_at = datetime.now(UTC) + timedelta(seconds=token_data.get("expire_in", 14400))

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
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    """Dispara sincronização de pedidos imediatamente para esta conta."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if not account.access_token:
        raise HTTPException(
            status_code=400, detail="Conta sem token de acesso. Faça o OAuth primeiro."
        )

    from tasks.sync_orders import _sync_ml_integration, _sync_shopee_integration

    if account.platform == "mercadolivre":
        await _sync_ml_integration(db, account)
    elif account.platform == "shopee":
        await _sync_shopee_integration(db, account)
    else:
        raise HTTPException(
            status_code=400, detail="Sincronização não disponível para esta plataforma."
        )

    return {"message": "Sincronização de pedidos concluída."}


@router.post("/{account_id}/import-listings")
async def import_listings(
    account_id: int,
    current_user: User = Depends(require_menu_permission("integrations")),
    db: AsyncSession = Depends(get_db),
):
    """Importa todos os anúncios ativos desta conta do Mercado Livre."""
    account = await _assert_ac_can_access(account_id, current_user.id, db)
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Importação de anúncios disponível apenas para Mercado Livre."
        )
    if not account.access_token or not account.platform_user_id:
        raise HTTPException(status_code=400, detail="Conta sem token ou ID. Faça o OAuth primeiro.")

    # 1. Buscar todos os IDs de anúncios ativos
    item_ids = await ml_service.get_seller_item_ids(account.access_token, account.platform_user_id)
    if not item_ids:
        return {
            "imported": 0,
            "updated": 0,
            "message": "Nenhum anúncio ativo encontrado no Mercado Livre.",
        }

    # 2. Buscar detalhes em lote
    items = await ml_service.get_items_bulk(account.access_token, item_ids)

    imported, updated = 0, 0
    for item in items:
        ml_id = str(item.get("id", ""))
        title = item.get("title", "")[:500]
        price = float(item.get("price") or 0)
        category = item.get("category_id", "")
        listing_type = item.get("listing_type_id", "")

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
            db.add(
                ProductListing(
                    product_id=product.id,
                    account_id=account_id,
                    platform_item_id=ml_id,
                    sale_price=price,
                    category_id=category,
                    listing_type=listing_type,
                    status="published",
                    published_at=datetime.now(UTC),
                    last_sync_at=datetime.now(UTC),
                )
            )
        else:
            listing.sale_price = price
            listing.platform_item_id = ml_id
            listing.status = "published"
            listing.last_sync_at = datetime.now(UTC)

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
    current_user: User = Depends(require_menu_permission("integrations")),
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

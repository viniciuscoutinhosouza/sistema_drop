"""Ponto ÚNICO de obtenção/renovação de access_token da Shopee.

Espelha `services/ml_auth.py`. O refresh token da Shopee **rotaciona** a cada renovação
(o antigo morre), então dois refreshes concorrentes com o mesmo refresh_token invalidam um
ao outro → a conta cairia em `requires_reauth`. Antes o refresh Shopee era inline e SEM lock
(`tasks/sync_tokens.py`). Aqui coordenamos:

  1. Lock por account_id (PM2 roda 1 worker → asyncio.Lock em processo basta).
  2. Re-leitura da conta DENTRO do lock antes de renovar.
  3. access_token da Shopee dura ~4h; renovamos com margem.
  4. Falha de autorização (refresh inválido/revogado) → marca `requires_reauth`.

NÃO edita nem depende de `ml_auth` — é o irmão Shopee.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.integration import MarketplaceAccount
from services import shopee_service

logger = logging.getLogger(__name__)

# access_token da Shopee: ~4h. Default de expiração quando o retorno não traz `expire_in`.
_SHOPEE_TOKEN_TTL = 4 * 3600

_locks: dict[int, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _get_account_lock(account_id: int) -> asyncio.Lock:
    async with _locks_guard:
        lock = _locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            _locks[account_id] = lock
        return lock


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _token_still_valid(account: MarketplaceAccount, margin_seconds: int) -> bool:
    exp = _aware(account.token_expires_at)
    return bool(
        account.access_token and exp and exp > datetime.now(UTC) + timedelta(seconds=margin_seconds)
    )


async def get_valid_shopee_token(
    account: MarketplaceAccount, db: AsyncSession, *, margin_seconds: int = 300
) -> str:
    """Retorna um access_token válido da conta Shopee, renovando de forma coordenada.

    margin_seconds: renova se o token vencer dentro dessa margem (default 5 min; o job proativo
    passa 3600). Levanta 400 se a conta não é Shopee, 401 se precisa reautorizar.
    """
    if account.platform != "shopee":
        raise HTTPException(status_code=400, detail="Operação disponível apenas para Shopee")

    if _token_still_valid(account, margin_seconds):
        return account.access_token

    lock = await _get_account_lock(account.id)
    async with lock:
        try:
            await db.refresh(account)
        except Exception:  # objeto pode não estar persistente nesta sessão
            pass

        if _token_still_valid(account, margin_seconds):
            return account.access_token

        if not account.refresh_token or not account.shop_id:
            raise HTTPException(
                status_code=401,
                detail="Token da Shopee expirado. Reconecte a loja em Integrações.",
            )

        try:
            data = await shopee_service.refresh_shopee_token(
                account.refresh_token, account.shop_id
            )
        except HTTPException as exc:
            # Talvez outro processo já tenha renovado: relê e checa antes de desativar.
            try:
                await db.refresh(account)
            except Exception:
                pass
            if _token_still_valid(account, margin_seconds=0):
                return account.access_token
            account.requires_reauth = True
            await db.commit()
            acc_label = account.description or account.platform_username or f"loja #{account.id}"
            raise HTTPException(
                status_code=401,
                detail=(
                    f'A loja Shopee "{acc_label}" perdeu a autorização ({exc.detail}). '
                    "Vá em Integrações e reconecte a loja."
                ),
            ) from exc

        account.access_token = data["access_token"]
        account.refresh_token = data.get("refresh_token", account.refresh_token)
        account.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=data.get("expire_in", _SHOPEE_TOKEN_TTL)
        )
        account.requires_reauth = False
        await db.commit()
        return account.access_token

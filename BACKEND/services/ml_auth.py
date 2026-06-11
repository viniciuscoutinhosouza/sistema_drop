"""Ponto ÚNICO de obtenção/renovação de access_token do Mercado Livre.

Por que centralizar: o refresh token do ML é de USO ÚNICO — cada renovação
gera um novo e invalida o anterior. Antes o refresh estava espalhado (job
sync_tokens + anuncios + stock + simulator + DRE), todos sem coordenação, e
duas renovações concorrentes com o mesmo refresh_token causavam `invalid_grant`
→ a conta era marcada requires_reauth → "perdia a conexão".

Esta implementação resolve isso com:
  1. Lock por account_id (PM2 roda 1 worker → asyncio.Lock em processo basta).
  2. Re-leitura da conta no banco DENTRO do lock antes de renovar — se outro
     caminho já renovou, usa o token novo e NÃO renova de novo.
  3. Recuperação no invalid_grant: relê o banco; se já há token válido, usa-o
     em vez de desativar a conta.
  4. Retry só em erro de conexão (não em invalid_grant nem read-timeout, que
     poderiam ter gasto o refresh token de uso único).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.integration import MarketplaceAccount
from services import ml_service

logger = logging.getLogger(__name__)

# Um lock por conta, criados sob demanda. _locks_guard protege o dict.
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
    """Garante datetime tz-aware (assume UTC se vier naive do Oracle)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _token_still_valid(account: MarketplaceAccount, margin_seconds: int) -> bool:
    exp = _aware(account.token_expires_at)
    return bool(
        account.access_token and exp and exp > datetime.now(UTC) + timedelta(seconds=margin_seconds)
    )


async def get_valid_token(
    account: MarketplaceAccount, db: AsyncSession, *, margin_seconds: int = 300
) -> str:
    """Retorna um access_token válido da conta ML, renovando de forma coordenada.

    margin_seconds: renova se o token vencer dentro dessa margem (default 5 min).
    O job de refresh proativo chama com margin_seconds=3600 (1 hora).
    """
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Operação disponível apenas para Mercado Livre"
        )

    # Caminho rápido sem lock: token claramente válido.
    if _token_still_valid(account, margin_seconds):
        return account.access_token

    lock = await _get_account_lock(account.id)
    async with lock:
        # Re-ler a conta DENTRO do lock — outro caminho pode ter renovado enquanto
        # esperávamos o lock (ou o job rodou em paralelo).
        try:
            await db.refresh(account)
        except Exception:  # objeto pode não estar persistente nesta sessão
            pass

        if _token_still_valid(account, margin_seconds):
            return account.access_token

        if not account.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Token do Mercado Livre expirado. Reconecte a conta em Integrações.",
            )

        try:
            token_data = await _refresh_with_retry(account.refresh_token)
        except HTTPException as exc:
            if exc.status_code == 401 and "invalid_grant" in (exc.detail or "").lower():
                # Talvez outro processo já tenha renovado: relê e checa antes de desativar.
                try:
                    await db.refresh(account)
                except Exception:
                    pass
                if _token_still_valid(account, margin_seconds=0):
                    return account.access_token
                account.requires_reauth = True
                await db.commit()
                acc_label = (
                    account.description or account.platform_username or f"conta #{account.id}"
                )
                raise HTTPException(
                    status_code=401,
                    detail=(
                        f'A conta do Mercado Livre "{acc_label}" perdeu a autorização '
                        "(invalid_grant). Vá em Integrações e reconecte a conta."
                    ),
                ) from exc
            raise

        account.access_token = token_data["access_token"]
        account.refresh_token = token_data.get("refresh_token", account.refresh_token)
        account.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=token_data.get("expires_in", 21600)
        )
        account.requires_reauth = False
        await db.commit()
        return account.access_token


async def _refresh_with_retry(refresh_token: str, attempts: int = 2) -> dict:
    """Renova o token. Só retenta em ERRO DE CONEXÃO (request não chegou ao ML).

    NÃO retenta em invalid_grant (definitivo) nem em read-timeout (o ML pode já
    ter rotacionado o token — retentar gastaria o refresh token de uso único).
    """
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return await ml_service.refresh_ml_token(refresh_token)
        except HTTPException:
            raise  # invalid_grant ou erro de API do ML — não retentar
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
            last_exc = e
            if i < attempts - 1:
                await asyncio.sleep(0.5)
        except httpx.HTTPError as e:
            # read-timeout / outros: não retentar (pode ter gasto o refresh token)
            raise HTTPException(
                status_code=502, detail=f"Erro de rede ao renovar token ML: {e}"
            ) from e
    raise HTTPException(
        status_code=502, detail=f"Falha de conexão ao renovar token ML: {last_exc}"
    )

"""Helper compartilhado para obter um access_token válido de uma conta ML.

Extraído do padrão duplicado em routers/anuncios.py, stock.py e simulator.py.
Faz refresh proativo quando o token está expirado e marca requires_reauth
quando o ML revoga o refresh_token (invalid_grant).
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.integration import MarketplaceAccount
from services import ml_service


async def get_valid_token(account: MarketplaceAccount, db: AsyncSession) -> str:
    """Retorna o access_token da conta; tenta refresh se expirado.

    Levanta HTTPException(401) com 'invalid_grant' no detail quando o ML
    revogou a autorização (a conta é marcada requires_reauth).
    """
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Operação disponível apenas para Mercado Livre"
        )

    now = datetime.now(UTC)
    expires = account.token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)

    token_expired = expires and expires <= now

    if token_expired:
        if not account.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Token do Mercado Livre expirado. Reconecte a conta em Integrações.",
            )
        try:
            token_data = await ml_service.refresh_ml_token(account.refresh_token)
        except HTTPException as exc:
            if exc.status_code == 401 and "invalid_grant" in (exc.detail or "").lower():
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
        account.token_expires_at = now + timedelta(seconds=token_data.get("expires_in", 21600))
        await db.commit()

    if not account.access_token:
        raise HTTPException(
            status_code=401,
            detail="Conta sem token de acesso. Conecte a conta do Mercado Livre em Integrações.",
        )

    return account.access_token

"""
Controle de acesso compartilhado da Central de Atendimento (mensagens + reclamações).
Define quais contas de marketplace o usuário pode ver: admin = todas ativas;
ac = contas das CMIGs que administra; demais papéis = 403.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG, CMIGAdministrator
from models.integration import MarketplaceAccount
from models.user import User


async def get_accessible_cmig_ids(db: AsyncSession, user: User) -> list[int]:
    """IDs das CMIGs que o usuário pode acessar (admin = todas; ac = as que administra)."""
    if user.role == "admin":
        result = await db.execute(select(CMIG.id))
        return [r[0] for r in result.all()]
    if user.role == "ac":
        result = await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
        return [r[0] for r in result.all()]
    return []


async def get_accessible_account_ids(db: AsyncSession, user: User) -> list[int]:
    """IDs das contas de marketplace que o usuário pode acessar no Atendimento."""
    if user.role == "admin":
        result = await db.execute(
            select(MarketplaceAccount.id).where(MarketplaceAccount.is_active == True)  # noqa: E712
        )
        return [r[0] for r in result.all()]
    if user.role == "ac":
        result = await db.execute(
            select(MarketplaceAccount.id)
            .join(CMIG, MarketplaceAccount.cmig_id == CMIG.id)
            .join(CMIGAdministrator, CMIGAdministrator.cmig_id == CMIG.id)
            .where(CMIGAdministrator.user_id == user.id)
        )
        return [r[0] for r in result.all()]
    raise HTTPException(
        status_code=403, detail="Acesso à central de atendimento apenas para AC e admin."
    )

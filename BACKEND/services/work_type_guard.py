"""Enforcement do tipo de trabalho do Galpão (Dropship × MultiLojas) — ponto ÚNICO.

Regra (por `warehouse.work_type` do galpão da CMIG da conta):
- `dropship`   → a conta vende produtos do Produto Geral (PG) + a própria CMIG.
- `multilojas` → a conta só vende a PRÓPRIA CMIG; publicar produto do PG é BLOQUEADO (o PG é base).

Compartilhado por TODOS os caminhos de publicação (anúncios ML e listings ML/Shopee), para não
deixar brecha: qualquer publicação de produto PG passa por aqui.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG
from models.integration import MarketplaceAccount
from models.warehouse import Warehouse


async def assert_pg_allowed_for_account(
    account: MarketplaceAccount, is_pg_publish, db: AsyncSession
) -> None:
    """Levanta 403 se a conta (galpão MultiLojas) tentar publicar um produto do PG.

    `is_pg_publish` = verdadeiro quando a publicação é de um produto do Produto Geral. Não age para
    dropship, conta sem CMIG, ou publicação de produto CMIG."""
    if not is_pg_publish or not account.cmig_id:
        return
    work_type = (
        await db.execute(
            select(Warehouse.work_type)
            .join(CMIG, CMIG.warehouse_id == Warehouse.id)
            .where(CMIG.id == account.cmig_id)
        )
    ).scalar_one_or_none()
    if work_type == "multilojas":
        raise HTTPException(
            status_code=403,
            detail="Galpão MultiLojas: esta conta só pode vender produtos da própria CMIG. "
                   "Cadastre o produto na CMIG — o Produto Geral (PG) é apenas base.",
        )

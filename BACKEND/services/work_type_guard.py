"""Enforcement do tipo de trabalho do Galpão (Dropship × MultiLojas) — adaptador por conta.

A regra de GRUPO de produto (PG × CMIG) vive em UM ponto único: `services/product_mode.py`
(`assert_product_group_allowed`), que combina `warehouse.work_type` (multilojas) com
`cmig.product_mode` por AND. Este módulo é só o ADAPTADOR usado pelos caminhos de publicação de
anúncio/listing: resolve a CMIG e o Galpão a partir da conta e delega — a regra NÃO é duplicada.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.cmig import CMIG
from models.integration import MarketplaceAccount
from services.product_mode import assert_product_group_allowed


async def assert_pg_allowed_for_account(
    account: MarketplaceAccount, is_pg_publish, db: AsyncSession, *, is_full: bool = False
) -> None:
    """Enforcement de grupo de produto na publicação de anúncio/listing a partir da conta.

    `is_pg_publish` = verdadeiro quando a publicação é de um produto do Produto Geral (PG); falso
    quando é um produto CMIG. `is_full` isenta (ADR-0010: FULL é sempre CMIG). Não age para conta
    sem CMIG. Delega ao ponto único `product_mode.assert_product_group_allowed`."""
    if not account.cmig_id:
        return
    cmig = (
        await db.execute(
            select(CMIG)
            .options(selectinload(CMIG.warehouse))
            .where(CMIG.id == account.cmig_id)
        )
    ).scalar_one_or_none()
    if cmig is None:
        return
    assert_product_group_allowed(
        cmig,
        cmig.warehouse,
        is_pg=bool(is_pg_publish),
        is_cmig=not bool(is_pg_publish),
        is_full=is_full,
    )

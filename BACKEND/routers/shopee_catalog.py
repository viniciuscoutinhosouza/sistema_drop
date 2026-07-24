"""Catálogo Shopee (Fase 6): categorias, atributos, marcas — leitura para a publicação.

Só folha (has_children=false) publica. Atributos vêm de get_attribute_tree (get_attributes está
offline). Marca 0 = "Sem marca". Ramo 100% Shopee. RBAC por posse da conta (owner/admin/AC).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.integration import MarketplaceAccount
from models.user import AccountAdministrator, User
from services import shopee_service
from services.shopee_auth import get_valid_shopee_token

router = APIRouter()


async def _shopee_account(account_id: int, user: User, db: AsyncSession):
    """Resolve a conta Shopee com RBAC de posse (owner/admin/administrador da conta) + token."""
    acc = (await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
    )).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    if acc.platform != "shopee":
        raise HTTPException(status_code=400, detail="Conta não é Shopee")
    if user.role != "admin" and acc.owner_id != user.id:
        adm = (await db.execute(
            select(AccountAdministrator).where(
                AccountAdministrator.account_id == account_id,
                AccountAdministrator.user_id == user.id,
            )
        )).scalar_one_or_none()
        if not adm:
            raise HTTPException(status_code=403, detail="Sem acesso a esta conta")
    token = await get_valid_shopee_token(acc, db)
    return acc, token


@router.get("/categories")
async def categories(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Árvore de categorias BR. Cada item traz has_children (folha=false, só folha publica)."""
    acc, token = await _shopee_account(account_id, current_user, db)
    cats = await shopee_service.get_category(token, acc.shop_id)
    return {"total": len(cats), "categorias": cats}


@router.get("/categories/{category_id}/attributes")
async def category_attributes(
    category_id: int,
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atributos da categoria (get_attribute_tree). `mandatory=true` = obrigatório no add_item."""
    acc, token = await _shopee_account(account_id, current_user, db)
    attrs = await shopee_service.get_attribute_tree(token, acc.shop_id, category_id)
    return {"category_id": category_id, "atributos": attrs}


@router.get("/categories/{category_id}/brands")
async def category_brands(
    category_id: int,
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Marcas da categoria (brand_id 0 = 'Sem marca'). `is_mandatory` diz se a marca é obrigatória."""
    acc, token = await _shopee_account(account_id, current_user, db)
    return await shopee_service.get_brand_list(token, acc.shop_id, category_id)


@router.get("/category-recommend")
async def category_recommend(
    account_id: int,
    item_name: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sugestão de category_id a partir do nome do item (validar folha em /categories)."""
    acc, token = await _shopee_account(account_id, current_user, db)
    ids = await shopee_service.category_recommend(token, acc.shop_id, item_name)
    return {"item_name": item_name, "category_ids": ids}

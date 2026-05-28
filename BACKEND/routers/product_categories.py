"""CRUD de categorias de marketplace cadastradas em produtos CMIG/PG.

Permite cadastrar múltiplas categorias (Mercado Livre, Shopee, ...) por produto,
cada uma com seu conjunto de atributos pré-preenchidos. Ao publicar um anúncio,
o usuário pode escolher uma categoria já cadastrada (com atributos prontos) ou
uma categoria nova como hoje.

Endpoints:
- GET    /api/v1/product-categories/catalog/{pid}     — lista do produto PG
- GET    /api/v1/product-categories/cmig/{pid}        — lista do produto CMIG
- POST   /api/v1/product-categories                   — cria
- PUT    /api/v1/product-categories/{id}              — atualiza atributos / nome
- DELETE /api/v1/product-categories/{id}              — remove
"""
import json as _json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.cmig import CMIGProduct
from models.product import CatalogProduct, ProductMarketplaceCategory
from models.user import User

router = APIRouter()

ALLOWED_MARKETPLACES = ("mercado_livre", "shopee")


def _serialize(pmc: ProductMarketplaceCategory) -> dict:
    return {
        "id": pmc.id,
        "catalog_product_id": pmc.catalog_product_id,
        "cmig_product_id": pmc.cmig_product_id,
        "marketplace": pmc.marketplace,
        "category_id": pmc.category_id,
        "category_name": pmc.category_name,
        "category_path_json": pmc.category_path_json,
        "attributes_json": pmc.attributes_json,
        "created_at": pmc.created_at.isoformat() if pmc.created_at else None,
        "updated_at": pmc.updated_at.isoformat() if pmc.updated_at else None,
    }


async def _list_for_owner(
    db: AsyncSession,
    *,
    catalog_product_id: int | None = None,
    cmig_product_id: int | None = None,
    marketplace: str | None = None,
) -> list[dict]:
    stmt = select(ProductMarketplaceCategory)
    if catalog_product_id:
        stmt = stmt.where(ProductMarketplaceCategory.catalog_product_id == catalog_product_id)
    elif cmig_product_id:
        stmt = stmt.where(ProductMarketplaceCategory.cmig_product_id == cmig_product_id)
    else:
        return []
    if marketplace:
        stmt = stmt.where(ProductMarketplaceCategory.marketplace == marketplace)
    stmt = stmt.order_by(ProductMarketplaceCategory.marketplace, ProductMarketplaceCategory.id)
    result = await db.execute(stmt)
    return [_serialize(pmc) for pmc in result.scalars().all()]


@router.get("/catalog/{pid}")
async def list_categories_for_catalog(
    pid: int,
    marketplace: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista categorias de marketplace cadastradas num produto PG.

    Filtro opcional por marketplace (`?marketplace=mercado_livre|shopee`).
    """
    prod = (await db.execute(select(CatalogProduct).where(CatalogProduct.id == pid))).scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Produto PG não encontrado")
    return await _list_for_owner(db, catalog_product_id=pid, marketplace=marketplace)


@router.get("/cmig/{pid}")
async def list_categories_for_cmig(
    pid: int,
    marketplace: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista categorias de marketplace cadastradas num produto CMIG.

    Filtro opcional por marketplace (`?marketplace=mercado_livre|shopee`).
    """
    prod = (await db.execute(select(CMIGProduct).where(CMIGProduct.id == pid))).scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    return await _list_for_owner(db, cmig_product_id=pid, marketplace=marketplace)


def _validate_body(body: dict) -> tuple[int | None, int | None, str, str]:
    """Extrai e valida campos obrigatórios; retorna (catalog_id, cmig_id, marketplace, category_id)."""
    catalog_id = body.get("catalog_product_id")
    cmig_id = body.get("cmig_product_id")
    if bool(catalog_id) == bool(cmig_id):
        raise HTTPException(
            status_code=400,
            detail="Informe exatamente um de catalog_product_id ou cmig_product_id",
        )
    marketplace = (body.get("marketplace") or "").strip()
    if marketplace not in ALLOWED_MARKETPLACES:
        raise HTTPException(
            status_code=400,
            detail=f"marketplace deve ser um de: {', '.join(ALLOWED_MARKETPLACES)}",
        )
    category_id = (body.get("category_id") or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="category_id é obrigatório")
    return catalog_id, cmig_id, marketplace, category_id


def _normalize_json_field(value) -> str | None:
    """Aceita dict/list (serializa) ou string já-JSON (passa direto). None → None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _json.dumps(value, ensure_ascii=False)


@router.post("")
async def create_category(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cadastra categoria de marketplace num produto.

    Body:
    - catalog_product_id OU cmig_product_id (obrigatório, exclusivos)
    - marketplace: 'mercado_livre' | 'shopee'
    - category_id: ID da categoria no marketplace
    - category_name (opcional)
    - category_path_json (opcional, lista ou string JSON)
    - attributes_json (opcional, lista ou string JSON)
    """
    catalog_id, cmig_id, marketplace, category_id = _validate_body(body)

    # Verifica duplicata explicitamente para devolver 409 amigável (em vez de IntegrityError do Oracle)
    dup_stmt = select(ProductMarketplaceCategory).where(
        ProductMarketplaceCategory.marketplace == marketplace,
        ProductMarketplaceCategory.category_id == category_id,
    )
    if catalog_id:
        dup_stmt = dup_stmt.where(ProductMarketplaceCategory.catalog_product_id == catalog_id)
    else:
        dup_stmt = dup_stmt.where(ProductMarketplaceCategory.cmig_product_id == cmig_id)
    dup = (await db.execute(dup_stmt)).scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=409,
            detail="Esta categoria já está cadastrada neste produto para este marketplace",
        )

    pmc = ProductMarketplaceCategory(
        catalog_product_id=catalog_id,
        cmig_product_id=cmig_id,
        marketplace=marketplace,
        category_id=category_id,
        category_name=body.get("category_name"),
        category_path_json=_normalize_json_field(body.get("category_path_json")),
        attributes_json=_normalize_json_field(body.get("attributes_json")),
    )
    db.add(pmc)
    await db.commit()
    await db.refresh(pmc)
    return _serialize(pmc)


@router.put("/{pmc_id}")
async def update_category(
    pmc_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza nome/path/atributos de uma categoria cadastrada.

    Categoria-id e owner (catalog/cmig) NÃO são editáveis — deleta e cria de novo.
    """
    pmc = (
        await db.execute(
            select(ProductMarketplaceCategory).where(ProductMarketplaceCategory.id == pmc_id)
        )
    ).scalar_one_or_none()
    if not pmc:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    if "category_name" in body:
        pmc.category_name = body["category_name"]
    if "category_path_json" in body:
        pmc.category_path_json = _normalize_json_field(body["category_path_json"])
    if "attributes_json" in body:
        pmc.attributes_json = _normalize_json_field(body["attributes_json"])

    await db.commit()
    await db.refresh(pmc)
    return _serialize(pmc)


@router.delete("/{pmc_id}")
async def delete_category(
    pmc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pmc = (
        await db.execute(
            select(ProductMarketplaceCategory).where(ProductMarketplaceCategory.id == pmc_id)
        )
    ).scalar_one_or_none()
    if not pmc:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    db.delete(pmc)
    await db.commit()
    return {"ok": True}

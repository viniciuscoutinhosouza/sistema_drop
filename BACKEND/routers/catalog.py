from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.cmig import CMIG, CMIGProduct
from models.product import CatalogProduct, CatalogProductImage, Category, ProductListing
from models.user import User
from services.warehouse_scope import sellable_pg_warehouse_ids, warehouse_ids_for

router = APIRouter()


def _pg_stock(p: CatalogProduct) -> int:
    """Estoque a exibir/publicar. Produto COMPOSTO não tem estoque próprio: o disponível é
    MIN(floor(estoque_componente / qtd)) — mesmo cálculo da tela PG e do push de anúncio
    (`stock_calculator.composite_stock`). Sem isto o catálogo mostrava 0 no kit e o
    `isSoldOut()` do frontend bloqueava a publicação."""
    if getattr(p, "is_composite", False):
        from services.fiscal.stock_calculator import kit_available

        return kit_available(p)   # montadas (retorno do FULL) + montáveis dos componentes
    return int(p.stock_quantity or 0)


@router.get("/published")
async def list_published_by_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anúncios já publicados na conta, agrupados por produto PG e por produto CMIG.

    Usado no Catálogo para marcar (ícone) os produtos já publicados na conta/CMIG
    selecionada e abrir o modal de métricas (visitas 7d, vendas, conversão).
    """
    # Valida que o usuário tem acesso a esta conta (evita vazar métricas entre contas).
    from routers.anuncios import _get_account_or_403

    await _get_account_or_403(account_id, current_user, db)

    rows = (
        await db.execute(
            select(ProductListing)
            .options(
                selectinload(ProductListing.catalog_product),
                selectinload(ProductListing.cmig_product),
            )
            .where(
                ProductListing.account_id == account_id,
                ProductListing.platform_item_id.isnot(None),
            )
        )
    ).scalars().all()

    pg: dict[int, list] = {}
    cmig: dict[int, list] = {}
    for l in rows:
        title = l.title_override
        if not title and l.catalog_product:
            title = l.catalog_product.title
        if not title and l.cmig_product:
            title = l.cmig_product.title
        visits = int(l.visits_7d or 0)
        sold = int(l.sold_quantity or 0)
        item = {
            "listing_id": l.id,
            "platform_item_id": l.platform_item_id,
            "permalink": l.permalink,
            "thumbnail": l.thumbnail,
            "title": title or l.sku or l.platform_item_id,
            "visits_7d": visits,
            "sold_quantity": sold,
            "conversion": round(sold / visits * 100, 2) if visits > 0 else None,
            "status": l.status,
        }
        if l.catalog_product_id:
            pg.setdefault(l.catalog_product_id, []).append(item)
        if l.cmig_product_id:
            cmig.setdefault(l.cmig_product_id, []).append(item)

    return {"pg": pg, "cmig": cmig}


@router.get("")
async def list_catalog(
    search: str = Query(None),
    category_id: int = Query(None),
    sort: str = Query("newest", regex="^(newest|cheapest|expensive|bestseller)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(16, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(CatalogProduct).where(CatalogProduct.is_active == True)

    # Isolamento por galpão (ADR-0026) + multilojas não vende PG (ADR-0024): PG só do(s) galpão(ões)
    # do usuário, excluindo multilojas. Ponto único (services/warehouse_scope). Fecha o vazamento de
    # PG do MIG para usuário `ac` de outro galpão — o filtro anterior só cobria `role == "go"`.
    pg_wh_ids = await sellable_pg_warehouse_ids(current_user, db)
    if pg_wh_ids is not None:  # não-admin
        if not pg_wh_ids:  # sem galpão vendável (inclui multilojas puro) → fail-closed
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        query = query.where(CatalogProduct.warehouse_id.in_(pg_wh_ids))

    if search:
        query = query.where(
            or_(
                CatalogProduct.title.ilike(f"%{search}%"),
                CatalogProduct.sku.ilike(f"%{search}%"),
            )
        )
    if category_id:
        query = query.where(CatalogProduct.category_id == category_id)

    # Estoque positivo primeiro, zerados por último (depois aplica o sort escolhido).
    # Kit (is_composite) NUNCA tem stock_quantity > 0 — o estoque vive nos componentes e é
    # derivado na leitura. Sem tratá-lo aqui, todo kit cairia no fim da lista como "esgotado".
    stock_order = case(
        (CatalogProduct.is_composite == True, 0),  # noqa: E712
        (CatalogProduct.stock_quantity > 0, 0),
        else_=1,
    )
    if sort == "cheapest":
        query = query.order_by(stock_order, CatalogProduct.cost_price.asc())
    elif sort == "expensive":
        query = query.order_by(stock_order, CatalogProduct.cost_price.desc())
    else:
        query = query.order_by(stock_order, CatalogProduct.created_at.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()

    items = []
    for p in products:
        img_result = await db.execute(
            select(CatalogProductImage)
            .where(CatalogProductImage.product_id == p.id)
            .order_by(CatalogProductImage.is_primary.desc(), CatalogProductImage.sort_order)
            .limit(1)
        )
        img = img_result.scalar_one_or_none()
        items.append(
            {
                "id": p.id,
                "sku": p.sku,
                "title": p.title,
                "cost_price": float(p.cost_price),
                "suggested_price": float(p.suggested_price) if p.suggested_price else None,
                "stock_quantity": _pg_stock(p),
                "is_composite": p.is_composite,
                "brand": p.brand,
                "model": p.model,
                "ean": p.ean,
                "category_id": p.category_id,
                "image_url": img.url if img else "",
            }
        )

    return {"items": items, "total": total, "page": page, "page_size": page_size}


# Isolamento de categorias por GALPÃO (migration 145): admin gerencia/vê todas; demais só os galpões
# a que pertencem (ADR-0026). Fail-closed: quem não resolve nenhum galpão não vê nem cria/edita.
def _is_admin(user: User) -> bool:
    return user.role == "admin"


async def _load_category(category_id: int, db: AsyncSession) -> Category:
    cat = (
        await db.execute(select(Category).where(Category.id == category_id))
    ).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return cat


def _assert_owned(cat: Category, user: User, wh_ids: set[int] | None) -> None:
    """403 se a categoria não é de um galpão do usuário. Admin bypassa. NULL nunca é possuível por
    não-admin (endurecimento anti-IDOR)."""
    if _is_admin(user):
        return
    if cat.warehouse_id is None or (wh_ids is not None and cat.warehouse_id not in wh_ids):
        raise HTTPException(status_code=403, detail="Categoria pertence a outro galpão")


async def _is_descendant(node_id: int, ancestor_id: int, db: AsyncSession) -> bool:
    """True se `node_id` está na subárvore de `ancestor_id` (sobe pelos parent_id). Anti-ciclo."""
    seen: set[int] = set()
    cur_id = node_id
    while cur_id is not None and cur_id not in seen:
        if cur_id == ancestor_id:
            return True
        seen.add(cur_id)
        cur_id = (
            await db.execute(select(Category.parent_id).where(Category.id == cur_id))
        ).scalar_one_or_none()
    return False


@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wh_ids = await warehouse_ids_for(current_user, db)
    q = select(Category).order_by(Category.name)
    if wh_ids is not None:  # não-admin
        if not wh_ids:
            return []  # fail-closed
        q = q.where(Category.warehouse_id.in_(wh_ids))
    result = await db.execute(q)
    return [
        {"id": c.id, "name": c.name, "parent_id": c.parent_id, "warehouse_id": c.warehouse_id}
        for c in result.scalars().all()
    ]


@router.post("/categories", status_code=201)
async def create_category(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("catalog")),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name é obrigatório")
    parent_id = body.get("parent_id")
    admin = _is_admin(current_user)
    wh_ids = await warehouse_ids_for(current_user, db)

    # Subcategoria HERDA o galpão do pai (fonte única); raiz = galpão do usuário. Valida posse do pai.
    if parent_id is not None:
        parent = await _load_category(parent_id, db)
        _assert_owned(parent, current_user, wh_ids)
        warehouse_id = parent.warehouse_id
    elif admin:
        warehouse_id = body.get("warehouse_id")  # admin escolhe (ou None = global)
    elif wh_ids and len(wh_ids) == 1:
        warehouse_id = next(iter(wh_ids))
    elif wh_ids and body.get("warehouse_id") in wh_ids:
        warehouse_id = body.get("warehouse_id")
    else:
        raise HTTPException(
            status_code=422, detail="Usuário sem galpão definido não pode criar categoria"
        )

    dup = await db.execute(
        select(Category).where(
            and_(
                func.lower(Category.name) == name.lower(),
                Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id,
                Category.warehouse_id == warehouse_id,
            )
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Já existe uma categoria com esse nome no mesmo nível"
        )

    cat = Category(name=name, parent_id=parent_id, warehouse_id=warehouse_id)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id, "warehouse_id": cat.warehouse_id}


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("catalog")),
):
    wh_ids = await warehouse_ids_for(current_user, db)
    cat = await _load_category(category_id, db)
    _assert_owned(cat, current_user, wh_ids)

    if "name" in body:
        new_name = (body["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=422, detail="name não pode ser vazio")
        cat.name = new_name
    if "parent_id" in body:
        new_parent = body["parent_id"]
        if new_parent == category_id:
            raise HTTPException(status_code=422, detail="Categoria não pode ser pai dela mesma")
        if new_parent is not None:
            parent = await _load_category(new_parent, db)
            _assert_owned(parent, current_user, wh_ids)
            if await _is_descendant(new_parent, category_id, db):
                raise HTTPException(
                    status_code=422, detail="Movimento criaria um ciclo na árvore de categorias"
                )
            cat.warehouse_id = parent.warehouse_id  # mantém a árvore no mesmo galpão
        cat.parent_id = new_parent

    await db.commit()
    return {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id, "warehouse_id": cat.warehouse_id}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("catalog")),
):
    wh_ids = await warehouse_ids_for(current_user, db)
    cat = await _load_category(category_id, db)
    _assert_owned(cat, current_user, wh_ids)

    pg_count = (
        await db.execute(
            select(func.count())
            .select_from(CatalogProduct)
            .where(CatalogProduct.category_id == category_id)
        )
    ).scalar() or 0
    cmig_count = (
        await db.execute(
            select(func.count())
            .select_from(CMIGProduct)
            .where(CMIGProduct.category_id == category_id)
        )
    ).scalar() or 0
    children_count = (
        await db.execute(
            select(func.count()).select_from(Category).where(Category.parent_id == category_id)
        )
    ).scalar() or 0

    if pg_count or cmig_count or children_count:
        raise HTTPException(
            status_code=409,
            detail=f"Categoria em uso: {pg_count} produtos PG, {cmig_count} produtos CMIG, {children_count} subcategorias",
        )

    db.delete(cat)
    await db.commit()
    return {"detail": "Categoria excluída"}


@router.get("/{product_id}")
async def get_catalog_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CatalogProduct).where(
            CatalogProduct.id == product_id, CatalogProduct.is_active == True
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Isolamento por galpão (ADR-0026): não vaza o detalhe (custo/NCM/dimensões) de PG de outro
    # galpão pelo id. Fora do escopo → 404 (não confirma existência). Admin (wh_ids None) vê tudo.
    wh_ids = await warehouse_ids_for(current_user, db)
    if wh_ids is not None and product.warehouse_id not in wh_ids:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    images_result = await db.execute(
        select(CatalogProductImage)
        .where(CatalogProductImage.product_id == product_id)
        .order_by(CatalogProductImage.is_primary.desc(), CatalogProductImage.sort_order)
    )
    images = [{"url": i.url, "is_primary": i.is_primary} for i in images_result.scalars().all()]

    return {
        "id": product.id,
        "sku": product.sku,
        "title": product.title,
        "description": product.description,
        "cost_price": float(product.cost_price),
        "suggested_price": float(product.suggested_price) if product.suggested_price else None,
        "weight_kg": float(product.weight_kg) if product.weight_kg else None,
        "height_cm": float(product.height_cm) if product.height_cm else None,
        "width_cm": float(product.width_cm) if product.width_cm else None,
        "length_cm": float(product.length_cm) if product.length_cm else None,
        "ncm": product.ncm,
        "brand": product.brand,
        "model": product.model,
        "stock_quantity": _pg_stock(product),
        "is_composite": product.is_composite,
        "images": images,
    }

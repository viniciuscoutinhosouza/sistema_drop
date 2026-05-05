from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update as _sa_update
from sqlalchemy.orm import selectinload
import os as _os, shutil as _shutil, uuid as _uuid_mod
from database import get_db
from dependencies import get_current_user
from models.user import User
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct, CMIGProductImage, CMIGProductVariant
from models.warehouse import Warehouse
from models.product import CatalogProduct, CatalogProductImage, CatalogProductVariant, ProductListing
from models.order import OrderItem
from models.integration import MarketplaceAccount
from models.nfe_config import NFeConfig
from schemas.cmig import (
    CMIGCreate, CMIGUpdate, CMIGOut, CMIGAdminAdd,
    CMIGProductCreate, CMIGProductUpdate, CMIGProductLinkPG, CMIGProductOut,
    NFeConfigCreate, NFeConfigUpdate, NFeConfigOut,
)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_cmig_or_404(cmig_id: int, db: AsyncSession) -> CMIG:
    result = await db.execute(select(CMIG).where(CMIG.id == cmig_id))
    cmig = result.scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    return cmig


async def _check_cmig_access(cmig: CMIG, user: User, db: AsyncSession, require_owner: bool = False):
    """Valida se o usuário pode acessar a CMIG."""
    if user.role == "admin":
        return
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        if require_owner:
            raise HTTPException(status_code=403, detail="Apenas o AC proprietário pode realizar esta ação")
        return
    if user.role == "ac":
        result = await db.execute(
            select(CMIGAdministrator).where(
                and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig.id)
            )
        )
        admin = result.scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        if require_owner and not admin.is_owner:
            raise HTTPException(status_code=403, detail="Apenas o AC proprietário pode realizar esta ação")
        return
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


# ── CMIG CRUD ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CMIGOut])
async def list_cmigs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "admin":
        result = await db.execute(select(CMIG))
    elif current_user.role == "ugo":
        result = await db.execute(
            select(CMIG).where(CMIG.warehouse_id == current_user.warehouse_id)
        )
    elif current_user.role == "ac":
        subq = select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == current_user.id)
        result = await db.execute(select(CMIG).where(CMIG.id.in_(subq)))
    else:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    return result.scalars().all()


@router.post("", status_code=201, response_model=CMIGOut)
async def create_cmig(
    body: CMIGCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC pode criar CMIG")

    dup = await db.execute(select(CMIG).where(CMIG.cnpj == body.cnpj))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="CNPJ já cadastrado")

    # Validar galpão
    wh = await db.execute(select(Warehouse).where(Warehouse.id == body.warehouse_id))
    if not wh.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    cmig = CMIG(
        owner_ac_id=current_user.id,
        **body.model_dump(),
    )
    db.add(cmig)
    await db.flush()

    # Registrar como administrador proprietário
    admin_entry = CMIGAdministrator(user_id=current_user.id, cmig_id=cmig.id, is_owner=True)
    db.add(admin_entry)
    await db.commit()
    await db.refresh(cmig)
    return cmig


@router.get("/{cmig_id}", response_model=CMIGOut)
async def get_cmig(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    return cmig


@router.put("/{cmig_id}", response_model=CMIGOut)
async def update_cmig(
    cmig_id: int,
    body: CMIGUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(cmig, field, value)

    await db.commit()
    await db.refresh(cmig)
    return cmig


# ── Co-administração ───────────────────────────────────────────────────────────

@router.post("/{cmig_id}/admins", status_code=201)
async def add_cmig_admin(
    cmig_id: int,
    body: CMIGAdminAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db, require_owner=True)

    dup = await db.execute(
        select(CMIGAdministrator).where(
            and_(CMIGAdministrator.user_id == body.user_id, CMIGAdministrator.cmig_id == cmig_id)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Usuário já é administrador desta CMIG")

    entry = CMIGAdministrator(user_id=body.user_id, cmig_id=cmig_id, is_owner=False)
    db.add(entry)
    await db.commit()
    return {"detail": "Co-administrador adicionado com sucesso"}


@router.delete("/{cmig_id}/admins/{user_id}", status_code=204)
async def remove_cmig_admin(
    cmig_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db, require_owner=True)

    result = await db.execute(
        select(CMIGAdministrator).where(
            and_(CMIGAdministrator.user_id == user_id, CMIGAdministrator.cmig_id == cmig_id)
        )
    )
    entry = result.scalar_one_or_none()
    if not entry or entry.is_owner:
        raise HTTPException(status_code=404, detail="Co-administrador não encontrado ou é o proprietário")

    db.delete(entry)
    await db.commit()


# ── Produtos CMIG ──────────────────────────────────────────────────────────────

@router.get("/{cmig_id}/products", response_model=list[CMIGProductOut])
async def list_cmig_products(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.images))
        .where(CMIGProduct.cmig_id == cmig_id)
    )
    return result.scalars().all()


@router.get("/{cmig_id}/products/{product_id}", response_model=CMIGProductOut)
async def get_cmig_product(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.images))
        .where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    return product


@router.post("/{cmig_id}/products", status_code=201, response_model=CMIGProductOut)
async def create_cmig_product(
    cmig_id: int,
    body: CMIGProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    if current_user.role == "ugo":
        raise HTTPException(status_code=403, detail="UGO não pode criar Produtos CMIG. Use importação de PG.")

    dup = await db.execute(
        select(CMIGProduct).where(
            and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.sku_cmig == body.sku_cmig)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU CMIG já cadastrado nesta CMIG")

    product = CMIGProduct(cmig_id=cmig_id, **body.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.put("/{cmig_id}/products/{product_id}", response_model=CMIGProductOut)
async def update_cmig_product(
    cmig_id: int,
    product_id: int,
    body: CMIGProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    payload = body.model_dump(exclude_none=True)
    images = payload.pop("images", None)

    for field, value in payload.items():
        setattr(product, field, value)

    # Sincronizar imagens se fornecidas (substitui o conteúdo da tabela)
    if images is not None:
        from sqlalchemy import delete as _sa_delete
        await db.execute(_sa_delete(CMIGProductImage).where(CMIGProductImage.cmig_product_id == product_id))
        for i, img in enumerate(images):
            url = img.get("url") if isinstance(img, dict) else str(img)
            if url:
                db.add(CMIGProductImage(
                    cmig_product_id=product_id,
                    url=url,
                    sort_order=i,
                    is_primary=(i == 0),
                ))

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{cmig_id}/products/{product_id}")
async def delete_cmig_product(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    # Verificar pedidos internos via PG vinculado
    has_sales = False
    if product.pg_product_id:
        r = await db.execute(
            select(func.count()).select_from(OrderItem)
            .where(OrderItem.catalog_product_id == product.pg_product_id)
        )
        has_sales = (r.scalar() or 0) > 0

    if has_sales:
        product.is_active = False
        await db.commit()
        return {"action": "deactivated", "message": "Produto desativado pois possui pedidos registrados."}

    # Sem vendas — limpar FK em ProductListing antes de deletar
    await db.execute(
        _sa_update(ProductListing)
        .where(ProductListing.cmig_product_id == product_id)
        .values(cmig_product_id=None)
    )

    db.delete(product)
    await db.commit()
    return {"action": "deleted", "message": "Produto excluído com sucesso."}


@router.post("/{cmig_id}/products/{product_id}/photos")
async def upload_cmig_product_photo(
    cmig_id: int,
    product_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    await _get_cmig_product_or_404(product_id, cmig_id, db)

    ext = _os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido. Use JPG, PNG, WEBP ou GIF.")

    filename = f"{_uuid_mod.uuid4().hex}{ext}"
    dest_dir = "static/uploads/cmig-products"
    _os.makedirs(dest_dir, exist_ok=True)
    with open(f"{dest_dir}/{filename}", "wb") as out:
        _shutil.copyfileobj(file.file, out)

    return {"url": f"/static/uploads/cmig-products/{filename}"}


@router.post("/{cmig_id}/products/{product_id}/link-pg")
async def link_cmig_product_to_pg(
    cmig_id: int,
    product_id: int,
    body: CMIGProductLinkPG,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AC vincula um Produto CMIG a um PG existente (vínculo de similaridade)."""
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    pg = await db.execute(select(CatalogProduct).where(CatalogProduct.id == body.pg_product_id))
    if not pg.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Produto PG não encontrado")

    product.pg_product_id = body.pg_product_id
    await db.commit()
    return {"detail": "Produto CMIG vinculado ao PG com sucesso"}


@router.post("/{cmig_id}/products/{product_id}/import-to-pg", status_code=201)
async def import_cmig_product_to_pg(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """UGO importa um Produto CMIG para o PG do seu Galpão (um a um)."""
    import secrets as _secrets
    import json as _json_imp

    if current_user.role not in ("ugo", "admin"):
        raise HTTPException(status_code=403, detail="Apenas UGO pode importar Produtos CMIG para o PG")

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.variants), selectinload(CMIGProduct.images))
        .where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    cp = result.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    if cp.pg_product_id:
        raise HTTPException(status_code=409, detail="Produto CMIG já está vinculado a um PG")

    sku_pg = f"PG-{cp.sku_cmig}-{_secrets.token_hex(3).upper()}"

    pg = CatalogProduct(
        warehouse_id=current_user.warehouse_id,
        sku=sku_pg,
        title=cp.title,
        description=cp.description or "",
        cost_price=cp.cost_price or 0,
        suggested_price=cp.suggested_price,
        model=cp.model,
        ean=cp.ean,
        weight_kg=cp.weight_kg,
        height_cm=cp.height_cm,
        width_cm=cp.width_cm,
        length_cm=cp.length_cm,
        ncm=cp.ncm,
        cest=cp.cest,
        brand=cp.brand,
        origin=cp.origin or 0,
        category_id=cp.category_id,
        video_id=cp.video_id,
        attributes_json=cp.attributes_json,
        stock_quantity=cp.stock_quantity or 0,
        is_active=True,
    )
    db.add(pg)
    await db.flush()

    # Importar fotos: prefere a tabela cmig_product_images; fallback p/ pictures_json (legado)
    photos_imported = 0
    if cp.images:
        for i, img in enumerate(cp.images):
            db.add(CatalogProductImage(
                product_id=pg.id,
                url=img.url,
                sort_order=img.sort_order if img.sort_order is not None else i,
                is_primary=bool(img.is_primary) or (i == 0),
            ))
            photos_imported += 1
    elif cp.pictures_json:
        try:
            pics = _json_imp.loads(cp.pictures_json)
            for i, pic in enumerate(pics):
                url = pic.get("url") if isinstance(pic, dict) else str(pic)
                if url:
                    db.add(CatalogProductImage(
                        product_id=pg.id,
                        url=url,
                        sort_order=i,
                        is_primary=(i == 0),
                    ))
                    photos_imported += 1
        except Exception:
            pass

    # Importar variantes → CatalogProductVariant
    variants_imported = 0
    for i, v in enumerate(cp.variants or []):
        var_sku = f"PG-{v.sku}-{_secrets.token_hex(2).upper()}"
        db.add(CatalogProductVariant(
            product_id=pg.id,
            sku=var_sku,
            variant_name=v.variant_name,
            color=v.color,
            size_label=v.size_label,
            voltage=v.voltage,
            stock_quantity=v.stock_quantity or 0,
            price_modifier=v.price_modifier or 0,
            attributes_json=v.attributes_json,
        ))
        variants_imported += 1

    cp.pg_product_id = pg.id
    await db.commit()
    await db.refresh(pg)
    return {
        "detail": "Produto importado para o PG com sucesso",
        "pg_product_id": pg.id,
        "sku": sku_pg,
        "photos_imported": photos_imported,
        "variants_imported": variants_imported,
        "brand": pg.brand,
        "model": pg.model,
        "ean": pg.ean,
    }


@router.post("/{cmig_id}/products/{product_id}/sync-pg")
async def sync_pg_from_cmig(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza os campos do PG vinculado com os dados atuais do Produto CMIG."""
    if current_user.role not in ("ugo", "admin"):
        raise HTTPException(status_code=403, detail="Apenas UGO pode sincronizar Produtos CMIG com PG")

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    cp = result.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    if not cp.pg_product_id:
        raise HTTPException(status_code=400, detail="Produto CMIG não está vinculado a um PG")

    pg_result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == cp.pg_product_id))
    pg = pg_result.scalar_one_or_none()
    if not pg:
        raise HTTPException(status_code=404, detail="Produto PG vinculado não encontrado")

    if cp.brand is not None:
        pg.brand = cp.brand
    if cp.model is not None:
        pg.model = cp.model
    if cp.ean is not None:
        pg.ean = cp.ean
    if cp.ncm is not None:
        pg.ncm = cp.ncm
    if cp.cest is not None:
        pg.cest = cp.cest
    if cp.weight_kg is not None:
        pg.weight_kg = cp.weight_kg
    if cp.height_cm is not None:
        pg.height_cm = cp.height_cm
    if cp.width_cm is not None:
        pg.width_cm = cp.width_cm
    if cp.length_cm is not None:
        pg.length_cm = cp.length_cm
    if cp.origin is not None:
        pg.origin = cp.origin
    if cp.category_id is not None:
        pg.category_id = cp.category_id
    if cp.video_id is not None:
        pg.video_id = cp.video_id
    if cp.attributes_json is not None:
        pg.attributes_json = cp.attributes_json

    await db.commit()
    return {
        "detail": "Produto PG atualizado com dados do CMIG",
        "pg_product_id": pg.id,
        "brand": cp.brand,
        "model": cp.model,
        "ean": cp.ean,
        "ncm": cp.ncm,
        "cest": cp.cest,
    }


# ── Variantes de Produtos CMIG ─────────────────────────────────────────────────

async def _get_cmig_product_or_404(product_id: int, cmig_id: int, db: AsyncSession) -> CMIGProduct:
    result = await db.execute(
        select(CMIGProduct).where(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    return product


@router.get("/{cmig_id}/products/{product_id}/variants")
async def list_cmig_product_variants(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    await _get_cmig_product_or_404(product_id, cmig_id, db)

    result = await db.execute(
        select(CMIGProductVariant).where(CMIGProductVariant.cmig_product_id == product_id)
    )
    variants = result.scalars().all()
    return [_serialize_variant(v) for v in variants]


@router.post("/{cmig_id}/products/{product_id}/variants", status_code=201)
async def create_cmig_product_variant(
    cmig_id: int,
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    await _get_cmig_product_or_404(product_id, cmig_id, db)

    sku = (body.get("sku") or "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="sku é obrigatório")

    dup = await db.execute(select(CMIGProductVariant).where(CMIGProductVariant.sku == sku))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU de variante já cadastrado")

    variant = CMIGProductVariant(
        cmig_product_id=product_id,
        sku=sku,
        variant_name=body.get("variant_name"),
        color=body.get("color"),
        size_label=body.get("size_label") or body.get("size"),
        voltage=body.get("voltage"),
        stock_quantity=int(body.get("stock_quantity", 0)),
        price_modifier=body.get("price_modifier", 0),
        suggested_price=body.get("suggested_price"),
        attributes_json=body.get("attributes_json"),
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.put("/{cmig_id}/products/{product_id}/variants/{variant_id}")
async def update_cmig_product_variant(
    cmig_id: int,
    product_id: int,
    variant_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProductVariant).where(
            CMIGProductVariant.id == variant_id,
            CMIGProductVariant.cmig_product_id == product_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada")

    for field in ("variant_name", "color", "size_label", "voltage", "stock_quantity", "price_modifier", "suggested_price", "attributes_json"):
        if field in body:
            setattr(variant, field, body[field])

    await db.commit()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.delete("/{cmig_id}/products/{product_id}/variants/{variant_id}", status_code=204)
async def delete_cmig_product_variant(
    cmig_id: int,
    product_id: int,
    variant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProductVariant).where(
            CMIGProductVariant.id == variant_id,
            CMIGProductVariant.cmig_product_id == product_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada")

    db.delete(variant)
    await db.commit()


def _serialize_variant(v: CMIGProductVariant) -> dict:
    return {
        "id": v.id,
        "cmig_product_id": v.cmig_product_id,
        "sku": v.sku,
        "variant_name": v.variant_name,
        "color": v.color,
        "size_label": v.size_label,
        "voltage": v.voltage,
        "stock_quantity": v.stock_quantity,
        "price_modifier": float(v.price_modifier) if v.price_modifier is not None else 0,
        "suggested_price": float(v.suggested_price) if v.suggested_price is not None else None,
        "attributes_json": v.attributes_json,
    }


# ── Configuração NF-e ──────────────────────────────────────────────────────────

@router.get("/{cmig_id}/nfe-configs/{cm_id}", response_model=list[NFeConfigOut])
async def list_nfe_configs(
    cmig_id: int,
    cm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(select(NFeConfig).where(NFeConfig.cm_id == cm_id))
    return result.scalars().all()


@router.post("/{cmig_id}/nfe-configs/{cm_id}", status_code=201, response_model=NFeConfigOut)
async def create_nfe_config(
    cmig_id: int,
    cm_id: int,
    body: NFeConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    if body.issuer not in ("marketplace", "system"):
        raise HTTPException(status_code=422, detail="issuer deve ser 'marketplace' ou 'system'")

    dup = await db.execute(
        select(NFeConfig).where(and_(NFeConfig.cm_id == cm_id, NFeConfig.shipping_method == body.shipping_method))
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Regra NF-e já existe para este método de envio")

    config = NFeConfig(cm_id=cm_id, **body.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/{cmig_id}/nfe-configs/{cm_id}/{config_id}", response_model=NFeConfigOut)
async def update_nfe_config(
    cmig_id: int,
    cm_id: int,
    config_id: int,
    body: NFeConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(NFeConfig).where(and_(NFeConfig.id == config_id, NFeConfig.cm_id == cm_id))
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração NF-e não encontrada")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(config, field, value)

    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/{cmig_id}/nfe-configs/{cm_id}/{config_id}", status_code=204)
async def delete_nfe_config(
    cmig_id: int,
    cm_id: int,
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(NFeConfig).where(and_(NFeConfig.id == config_id, NFeConfig.cm_id == cm_id))
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração NF-e não encontrada")

    db.delete(config)
    await db.commit()

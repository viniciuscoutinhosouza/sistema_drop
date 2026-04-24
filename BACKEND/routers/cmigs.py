from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database import get_db
from dependencies import get_current_user
from models.user import User
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct, CMIGProductImage, CMIGProductVariant
from models.warehouse import Warehouse
from models.product import CatalogProduct
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

    await db.delete(entry)
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

    result = await db.execute(select(CMIGProduct).where(CMIGProduct.cmig_id == cmig_id))
    return result.scalars().all()


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

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{cmig_id}/products/{product_id}", status_code=204)
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

    await db.delete(product)
    await db.commit()


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
    if current_user.role not in ("ugo", "admin"):
        raise HTTPException(status_code=403, detail="Apenas UGO pode importar Produtos CMIG para o PG")

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    cp = result.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    if cp.pg_product_id:
        raise HTTPException(status_code=409, detail="Produto CMIG já está vinculado a um PG")

    # Gerar SKU único para o PG
    import secrets
    sku_pg = f"PG-{cp.sku_cmig}-{secrets.token_hex(3).upper()}"

    pg = CatalogProduct(
        sku=sku_pg,
        title=cp.title,
        description=cp.description or "",
        cost_price=cp.cost_price or 0,
        weight_kg=cp.weight_kg,
        height_cm=cp.height_cm,
        width_cm=cp.width_cm,
        length_cm=cp.length_cm,
        ncm=cp.ncm,
        cest=cp.cest,
        brand=cp.brand,
        origin=cp.origin or 0,
        stock_quantity=0,
        is_active=True,
    )
    db.add(pg)
    await db.flush()

    cp.pg_product_id = pg.id
    await db.commit()
    await db.refresh(pg)
    return {"detail": "Produto importado para o PG com sucesso", "pg_product_id": pg.id, "sku": sku_pg}


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

    for field in ("variant_name", "color", "size_label", "voltage", "stock_quantity", "price_modifier", "attributes_json"):
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

    await db.delete(variant)
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

    await db.delete(config)
    await db.commit()

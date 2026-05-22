import os as _os
import shutil as _shutil
import uuid as _uuid
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _time

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import and_, func, select
from sqlalchemy import delete as _sa_delete
from sqlalchemy import update as _sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user, require_role
from models.cmig import CMIGProduct
from models.order import OrderItem
from models.product import (
    CatalogProduct,
    CatalogProductComponent,
    CatalogProductImage,
    CatalogProductVariant,
    ProductListing,
)
from models.user import User
from services.stock_history import replay_stock_events_for_pg_product

router = APIRouter()


def _norm_ncm(v):
    if not v:
        return v
    return v.replace(".", "").replace("-", "")[:8] or None


def _norm_cest(v):
    if not v:
        return v
    return v.replace(".", "").replace("-", "")[:7] or None


def _calculate_pg_composite_stock(components) -> int:
    """Retorna MIN(floor(estoque_comp / qtd)) para todos os componentes do PG composto."""
    if not components:
        return 0
    stocks = []
    for comp in components:
        qty = max(comp.quantity, 1)
        if comp.component:
            stocks.append(comp.component.stock_quantity // qty)
    return min(stocks) if stocks else 0


def _serialize_product(p: CatalogProduct, include_components: bool = False) -> dict:
    thumbnail = None
    if p.images:
        thumbnail = sorted(p.images, key=lambda i: i.sort_order)[0].url
    stock = _calculate_pg_composite_stock(p.components) if p.is_composite else p.stock_quantity
    result = {
        "id": p.id,
        "sku": p.sku,
        "title": p.title,
        "description": p.description,
        "cost_price": float(p.cost_price) if p.cost_price is not None else 0,
        "suggested_price": float(p.suggested_price) if p.suggested_price else None,
        "stock_quantity": stock,
        "weight_kg": float(p.weight_kg) if p.weight_kg else None,
        "height_cm": float(p.height_cm) if p.height_cm else None,
        "width_cm": float(p.width_cm) if p.width_cm else None,
        "length_cm": float(p.length_cm) if p.length_cm else None,
        "ncm": p.ncm,
        "cest": p.cest,
        "brand": p.brand,
        "model": p.model,
        "ean": p.ean,
        "origin": p.origin,
        "category_id": p.category_id,
        "category_name": p.category_name,
        "video_id": p.video_id,
        "attributes_json": p.attributes_json,
        "is_composite": p.is_composite,
        "is_active": p.is_active,
        "thumbnail": thumbnail,
        "images": [
            {"id": i.id, "url": i.url, "sort_order": i.sort_order, "is_primary": i.is_primary}
            for i in sorted(p.images, key=lambda i: i.sort_order)
        ],
        "components": [],
    }
    if include_components and p.is_composite:
        for comp in p.components:
            if comp.component:
                qty = max(comp.quantity, 1)
                result["components"].append(
                    {
                        "id": comp.id,
                        "product_id": comp.component_id,
                        "title": comp.component.title,
                        "sku": comp.component.sku,
                        "stock_quantity": comp.component.stock_quantity,
                        "quantity": comp.quantity,
                        "contribution": comp.component.stock_quantity // qty,
                    }
                )
    return result


def _serialize_variant(v: CatalogProductVariant) -> dict:
    return {
        "id": v.id,
        "product_id": v.product_id,
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


@router.get("")
async def list_supplier_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin", "ac")),
):
    if current_user.role == "ugo" and current_user.warehouse_id:
        stmt = (
            select(CatalogProduct)
            .options(selectinload(CatalogProduct.images))
            .where(CatalogProduct.warehouse_id == current_user.warehouse_id)
            .order_by(CatalogProduct.created_at.desc())
        )
    elif current_user.role == "ac" and current_user.warehouse_id:
        stmt = (
            select(CatalogProduct)
            .options(selectinload(CatalogProduct.images))
            .where(
                and_(
                    CatalogProduct.warehouse_id == current_user.warehouse_id,
                    CatalogProduct.is_active == True,
                )
            )
            .order_by(CatalogProduct.created_at.desc())
        )
    else:
        stmt = (
            select(CatalogProduct)
            .options(selectinload(CatalogProduct.images))
            .order_by(CatalogProduct.created_at.desc())
        )

    result = await db.execute(stmt)
    return [_serialize_product(p) for p in result.scalars().all()]


@router.get("/{product_id}")
async def get_supplier_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin", "ac")),
):
    result = await db.execute(
        select(CatalogProduct)
        .options(selectinload(CatalogProduct.images), selectinload(CatalogProduct.variants))
        .where(CatalogProduct.id == product_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    data = _serialize_product(p, include_components=True)
    data["variants"] = [_serialize_variant(v) for v in sorted(p.variants, key=lambda v: v.id)]
    return data


@router.post("", status_code=201)
async def create_product(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    is_composite = bool(body.get("is_composite", False))
    product = CatalogProduct(
        warehouse_id=current_user.warehouse_id,
        sku=body["sku"],
        title=body["title"],
        description=body.get("description"),
        cost_price=body["cost_price"],
        suggested_price=body.get("suggested_price"),
        model=body.get("model"),
        ean=body.get("ean"),
        weight_kg=body.get("weight_kg"),
        height_cm=body.get("height_cm"),
        width_cm=body.get("width_cm"),
        length_cm=body.get("length_cm"),
        ncm=_norm_ncm(body.get("ncm")),
        cest=_norm_cest(body.get("cest")),
        brand=body.get("brand"),
        origin=body.get("origin", 0),
        category_id=body.get("category_id"),
        video_id=body.get("video_id"),
        attributes_json=body.get("attributes_json"),
        is_composite=is_composite,
        # stock_quantity é gerenciado por eventos de NF-e/pedido (entrada/saída)
    )
    db.add(product)
    await db.flush()

    for i, img in enumerate(body.get("images", [])):
        url = img.get("url") if isinstance(img, dict) else str(img)
        if url:
            db.add(
                CatalogProductImage(
                    product_id=product.id, url=url, sort_order=i, is_primary=(i == 0)
                )
            )

    if is_composite:
        for comp in body.get("components", []):
            comp_id = comp.get("component_id")
            if not comp_id:
                continue
            db.add(
                CatalogProductComponent(
                    composite_id=product.id,
                    component_id=comp_id,
                    quantity=max(int(comp.get("quantity", 1)), 1),
                )
            )

    await db.commit()
    return {"id": product.id, "sku": product.sku}


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Mudança de SKU + cascata pra CMIGs vinculados e anúncios
    cascade_summary = {"cmigs_updated": 0, "listings_updated": 0}
    new_sku = body.get("sku")
    cascade_linked = bool(body.get("cascade_sku_to_linked"))
    if new_sku is not None:
        new_sku = str(new_sku).strip()
        if not new_sku:
            raise HTTPException(status_code=422, detail="SKU não pode ser vazio")
        if new_sku != product.sku:
            dup = (
                await db.execute(
                    select(CatalogProduct).where(
                        and_(CatalogProduct.sku == new_sku, CatalogProduct.id != product_id)
                    )
                )
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=409, detail=f"SKU '{new_sku}' já em uso")
            product.sku = new_sku

            if cascade_linked:
                # Propaga para CMIGs vinculados (1 PG pode ter N CMIGs)
                linked_cmigs = (
                    await db.execute(
                        select(CMIGProduct).where(CMIGProduct.pg_product_id == product_id)
                    )
                ).scalars().all()
                for cp in linked_cmigs:
                    if cp.sku_cmig != new_sku:
                        cp_dup = (
                            await db.execute(
                                select(CMIGProduct).where(
                                    and_(
                                        CMIGProduct.cmig_id == cp.cmig_id,
                                        CMIGProduct.sku_cmig == new_sku,
                                        CMIGProduct.id != cp.id,
                                    )
                                )
                            )
                        ).scalar_one_or_none()
                        if cp_dup:
                            raise HTTPException(
                                status_code=409,
                                detail=f"Cascata abortada: SKU '{new_sku}' já em uso no CMIG #{cp.cmig_id} (produto #{cp_dup.id})",
                            )
                        cp.sku_cmig = new_sku
                        cascade_summary["cmigs_updated"] += 1

                # Propaga para anúncios
                lst_result = await db.execute(
                    _sa_update(ProductListing)
                    .where(ProductListing.catalog_product_id == product_id)
                    .values(sku=new_sku)
                )
                cascade_summary["listings_updated"] = lst_result.rowcount or 0

    # stock_quantity intencionalmente fora — atualizado por eventos de NF-e/pedido
    for field in [
        "title",
        "description",
        "cost_price",
        "suggested_price",
        "model",
        "ean",
        "weight_kg",
        "height_cm",
        "width_cm",
        "length_cm",
        "ncm",
        "cest",
        "brand",
        "origin",
        "is_active",
        "category_id",
        "video_id",
        "attributes_json",
    ]:
        if field in body:
            val = body[field]
            if field == "ncm":
                val = _norm_ncm(val)
            elif field == "cest":
                val = _norm_cest(val)
            setattr(product, field, val)

    # Sincronizar imagens se fornecidas
    if "images" in body:
        await db.execute(
            _sa_delete(CatalogProductImage).where(CatalogProductImage.product_id == product_id)
        )
        for i, img in enumerate(body["images"]):
            url = img.get("url") if isinstance(img, dict) else str(img)
            if url:
                db.add(
                    CatalogProductImage(
                        product_id=product_id, url=url, sort_order=i, is_primary=(i == 0)
                    )
                )

    # Substituir componentes se produto composto e components fornecidos
    if product.is_composite and "components" in body:
        await db.execute(
            _sa_delete(CatalogProductComponent).where(
                CatalogProductComponent.composite_id == product_id
            )
        )
        for comp in body["components"]:
            comp_id = comp.get("component_id")
            if not comp_id:
                continue
            db.add(
                CatalogProductComponent(
                    composite_id=product_id,
                    component_id=comp_id,
                    quantity=max(int(comp.get("quantity", 1)), 1),
                )
            )

    await db.commit()
    response = {"ok": True}
    if cascade_summary["cmigs_updated"] or cascade_summary["listings_updated"]:
        response["_cascade"] = cascade_summary
    return response


@router.post("/{product_id}/duplicate", status_code=201)
async def duplicate_product(
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """Duplica um produto PG com o SKU informado pelo usuário."""
    result = await db.execute(
        select(CatalogProduct)
        .options(
            selectinload(CatalogProduct.images),
            selectinload(CatalogProduct.variants),
            selectinload(CatalogProduct.components),
        )
        .where(CatalogProduct.id == product_id)
    )
    src = result.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    new_sku = (body.get("sku") or "").strip()
    if not new_sku:
        raise HTTPException(status_code=422, detail="SKU é obrigatório para duplicar o produto")
    if (
        await db.execute(select(CatalogProduct).where(CatalogProduct.sku == new_sku))
    ).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"SKU '{new_sku}' já está em uso")

    copy = CatalogProduct(
        warehouse_id=src.warehouse_id,
        sku=new_sku,
        title=f"{src.title} (Cópia)",
        description=src.description,
        cost_price=src.cost_price,
        suggested_price=src.suggested_price,
        model=src.model,
        ean=src.ean,
        weight_kg=src.weight_kg,
        height_cm=src.height_cm,
        width_cm=src.width_cm,
        length_cm=src.length_cm,
        ncm=src.ncm,
        cest=src.cest,
        brand=src.brand,
        origin=src.origin,
        category_id=src.category_id,
        video_id=src.video_id,
        attributes_json=src.attributes_json,
        is_composite=src.is_composite,
    )
    db.add(copy)
    await db.flush()

    for i, img in enumerate(sorted(src.images, key=lambda x: x.sort_order)):
        db.add(
            CatalogProductImage(product_id=copy.id, url=img.url, sort_order=i, is_primary=(i == 0))
        )

    for v in src.variants:
        v_sku = f"{v.sku}-copia"
        v_suffix = 2
        while (
            await db.execute(
                select(CatalogProductVariant).where(CatalogProductVariant.sku == v_sku)
            )
        ).scalar_one_or_none():
            v_sku = f"{v.sku}-copia-{v_suffix}"
            v_suffix += 1
        db.add(
            CatalogProductVariant(
                product_id=copy.id,
                sku=v_sku,
                variant_name=v.variant_name,
                color=v.color,
                size_label=v.size_label,
                voltage=v.voltage,
                price_modifier=v.price_modifier,
                suggested_price=v.suggested_price,
                attributes_json=v.attributes_json,
            )
        )

    if src.is_composite:
        for comp in src.components:
            db.add(
                CatalogProductComponent(
                    composite_id=copy.id,
                    component_id=comp.component_id,
                    quantity=comp.quantity,
                )
            )

    await db.commit()
    return {"id": copy.id, "sku": copy.sku}


@router.post("/{product_id}/photos")
async def upload_product_photo(
    product_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    ext = _os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(
            status_code=400, detail="Tipo de arquivo não permitido. Use JPG, PNG, WEBP ou GIF."
        )

    filename = f"{_uuid.uuid4().hex}{ext}"
    dest_dir = "static/uploads/pg-products"
    _os.makedirs(dest_dir, exist_ok=True)
    with open(f"{dest_dir}/{filename}", "wb") as out:
        _shutil.copyfileobj(file.file, out)

    return {"url": f"/static/uploads/pg-products/{filename}"}


@router.put("/{product_id}/stock")
async def update_stock(
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """DEPRECATED: edição manual de `stock_quantity` é desencorajada no modelo
    canônico (event-sourced). Para ajustes, crie uma NFe de entrada/saída.
    Mantido pra compat. Quando chamado, sobrescreve o cache — próximo recompute
    pode restaurar pro valor calculado dos eventos."""
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    product.stock_quantity = body["stock_quantity"]
    await db.commit()
    return {"ok": True, "stock_quantity": product.stock_quantity}


@router.post("/{product_id}/recalculate-stock")
async def recalculate_pg_product_stock(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalcula `stock_quantity` do PG a partir dos eventos canônicos
    (NFes diretas PG + overflow de pedidos dos CMIGs vinculados)."""
    from services.fiscal.stock_calculator import recompute_pg_product_stock as _recompute

    product = (
        await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto PG não encontrado")
    old = int(product.stock_quantity or 0)
    new = await _recompute(product_id, db)
    await db.commit()
    return {"old_stock": old, "new_stock": new, "delta": (new or 0) - old}


@router.post("/recalculate-all-stock")
async def recalculate_all_stock(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """ADMIN: recalcula `stock_quantity` de TODOS os CMIGProducts e CatalogProducts.
    Usar após deploy de mudanças que afetam a fórmula de cálculo, ou pra corrigir
    drift do cache."""
    from services.fiscal.stock_calculator import recompute_all_stock

    result = await recompute_all_stock(db)
    await db.commit()
    return result


@router.get("/{product_id}/stock-movements")
async def get_pg_product_stock_movements(
    product_id: int,
    start_date: _date | None = Query(None, description="Início do período (inclusivo)"),
    end_date: _date | None = Query(None, description="Fim do período (inclusivo)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico de movimentação de estoque do CatalogProduct (PG).

    Agrega NFes dos CMIGProducts vinculados (via `CMIGProduct.pg_product_id`)
    + pedidos overflow (quando o estoque CMIG projetado zerou e a saída foi
    pra PG). O estoque PG (`CatalogProduct.stock_quantity`) é manual e
    independente — exibido como saldo de referência.
    """
    product = (
        await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    current_balance_pg = int(product.stock_quantity or 0)

    events, linked_cmigs = await replay_stock_events_for_pg_product(product, db)
    linked_cmig_count = len(linked_cmigs)

    if not events:
        return {
            "product_id": product.id,
            "product_sku": product.sku,
            "product_title": product.title,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "initial_balance": 0,
            "final_balance": 0,
            "current_balance_pg": current_balance_pg,
            "reserved_in_pending_orders_pg": 0,
            "current_balance_available": current_balance_pg,
            "period_in_nfe": 0,
            "period_out_nfe": 0,
            "period_out_orders": 0,
            "period_net_nfe": 0,
            "linked_cmig_count": linked_cmig_count,
            "movements": [],
        }

    end_dt = _datetime.combine(end_date, _time.max) if end_date is not None else None
    start_dt = _datetime.combine(start_date, _time.min) if start_date is not None else None

    def in_period(d) -> bool:
        if start_dt is not None and d < start_dt:
            return False
        if end_dt is not None and d > end_dt:
            return False
        return True

    # Para PG, "initial/final balance" representa o saldo agregado NFe-only
    # dos CMIGs vinculados. Não é o saldo PG (que é manual e separado).
    # Calculamos como sum cumulativo de NFe-in/out dos linked CMIGs.
    initial_balance = 0
    final_balance = 0
    for e in events:
        if start_dt is not None and e.date < start_dt:
            if e.source == "nfe_in":
                initial_balance += e.qty
            elif e.source == "nfe_out":
                initial_balance -= e.qty
        if end_dt is None or e.date <= end_dt:
            if e.source == "nfe_in":
                final_balance += e.qty
            elif e.source == "nfe_out":
                final_balance -= e.qty

    nfe_in_period = 0
    nfe_out_period = 0
    period_out_orders_reserved_pg = 0    # handling + ready_to_ship com overflow no período
    period_out_orders_definitive_pg = 0  # shipped + delivered com overflow no período
    # Reservado PG (estado atual): overflow de pedidos handling/ready_to_ship
    reserved_in_pending_orders_pg = 0
    # Movimentado em pedidos sem NFe (estado atual): overflow shipped/delivered sem NFe
    moved_in_orders_no_nfe_pg = 0
    for e in events:
        if e.source == "order" and e.qty_to_pg > 0:
            if e.is_reserved:
                reserved_in_pending_orders_pg += e.qty_to_pg
            elif e.is_definitive and not e.order_invoice_finalized:
                moved_in_orders_no_nfe_pg += e.qty_to_pg
        if not in_period(e.date):
            continue
        if e.source == "nfe_in":
            nfe_in_period += e.qty
        elif e.source == "nfe_out":
            nfe_out_period += e.qty
        elif e.source == "order" and e.qty_to_pg > 0:
            if e.is_reserved:
                period_out_orders_reserved_pg += e.qty_to_pg
            elif e.is_definitive:
                period_out_orders_definitive_pg += e.qty_to_pg

    # Walk cronológico de TODOS eventos pra computar running_available agregado (overflow PG)
    visible_events: list[dict] = []
    running_nfe_agg = 0  # acumulado de NFe-in/out dos CMIGs vinculados
    running_pending_pg = 0  # overflow PG de pedidos sem NFe finalizada
    # Inicializar running_nfe_agg com saldo antes do primeiro evento (mesma referência usada em initial_balance)
    for e in events:
        if e.source == "nfe_in":
            running_nfe_agg += e.qty
        elif e.source == "nfe_out":
            running_nfe_agg -= e.qty
        elif e.source == "order" and e.qty_to_pg > 0 and not e.order_invoice_finalized:
            running_pending_pg += e.qty_to_pg
        if not in_period(e.date):
            continue
        if e.source == "order" and e.qty_to_pg <= 0:
            continue
        d = e.to_dict()
        d["running_balance"] = running_nfe_agg
        d["running_available"] = running_nfe_agg - running_pending_pg
        visible_events.append(d)

    current_balance_available = (
        current_balance_pg - reserved_in_pending_orders_pg - moved_in_orders_no_nfe_pg
    )

    # Exibição em ordem descendente (mais recente primeiro)
    visible_events.reverse()

    return {
        "product_id": product.id,
        "product_sku": product.sku,
        "product_title": product.title,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "initial_balance": initial_balance,
        "final_balance": final_balance,
        "current_balance_pg": current_balance_pg,
        "reserved_in_pending_orders_pg": reserved_in_pending_orders_pg,
        "moved_in_orders_no_nfe_pg": moved_in_orders_no_nfe_pg,
        "current_balance_available": current_balance_available,
        "period_in_nfe": nfe_in_period,
        "period_out_nfe": nfe_out_period,
        "period_out_orders_reserved": period_out_orders_reserved_pg,
        "period_out_orders_definitive": period_out_orders_definitive_pg,
        "period_out_orders": period_out_orders_reserved_pg + period_out_orders_definitive_pg,
        "period_net_nfe": nfe_in_period - nfe_out_period,
        "linked_cmig_count": linked_cmig_count,
        "movements": visible_events,
    }


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Única fonte confiável de venda interna: order_items
    r = await db.execute(
        select(func.count())
        .select_from(OrderItem)
        .where(OrderItem.catalog_product_id == product_id)
    )
    has_sales = (r.scalar() or 0) > 0

    if has_sales:
        product.is_active = False
        await db.commit()
        return {
            "action": "deactivated",
            "message": "Produto desativado pois possui pedidos registrados.",
        }

    # Sem vendas — limpar FKs que apontam para este produto antes de deletar
    await db.execute(
        _sa_update(CMIGProduct)
        .where(CMIGProduct.pg_product_id == product_id)
        .values(pg_product_id=None)
    )
    await db.execute(
        _sa_update(ProductListing)
        .where(ProductListing.catalog_product_id == product_id)
        .values(catalog_product_id=None)
    )

    db.delete(product)
    await db.commit()
    return {"action": "deleted", "message": "Produto excluído com sucesso."}


# ── Variantes ──────────────────────────────────────────────────────────────────


@router.get("/{product_id}/variants")
async def list_variants(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin", "ac")),
):
    result = await db.execute(
        select(CatalogProductVariant).where(CatalogProductVariant.product_id == product_id)
    )
    return [_serialize_variant(v) for v in result.scalars().all()]


@router.post("/{product_id}/variants", status_code=201)
async def create_variant(
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    sku = (body.get("sku") or "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="sku é obrigatório")

    dup = await db.execute(select(CatalogProductVariant).where(CatalogProductVariant.sku == sku))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU de variante já cadastrado")

    variant = CatalogProductVariant(
        product_id=product_id,
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


@router.put("/{product_id}/variants/{variant_id}")
async def update_variant(
    product_id: int,
    variant_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(
        select(CatalogProductVariant).where(
            CatalogProductVariant.id == variant_id,
            CatalogProductVariant.product_id == product_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada")

    for field in (
        "variant_name",
        "color",
        "size_label",
        "voltage",
        "stock_quantity",
        "price_modifier",
        "suggested_price",
        "attributes_json",
    ):
        if field in body:
            setattr(variant, field, body[field])

    await db.commit()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.delete("/{product_id}/variants/{variant_id}", status_code=204)
async def delete_variant(
    product_id: int,
    variant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ugo", "admin")),
):
    result = await db.execute(
        select(CatalogProductVariant).where(
            CatalogProductVariant.id == variant_id,
            CatalogProductVariant.product_id == product_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada")
    db.delete(variant)
    await db.commit()

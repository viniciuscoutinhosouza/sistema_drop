import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, task_db
from dependencies import get_current_user, require_role
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.fiscal import Invoice
from models.full_stock import FullStock
from models.integration import MarketplaceAccount
from models.product import CatalogProduct
from models.stock_movement import StockMovement
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
async def stock_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = Query(None),
    scope: str = Query(None, regex="^(pg|cmig)$"),
    warehouse_id: int = Query(None),
    cmig_id: int = Query(None),
    sort_by: str = Query("name", regex="^(sku|name|physical|available)$"),
    sort_dir: str = Query("asc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    # AC só enxerga produtos das CMIGs em que é administrador
    ac_cmig_ids: list[int] | None = None
    if current_user.role == "ac":
        scope = "cmig"
        rows = await db.execute(
            select(CMIGAdministrator.cmig_id).where(
                CMIGAdministrator.user_id == current_user.id
            )
        )
        ac_cmig_ids = [r[0] for r in rows.all()]
        if not ac_cmig_ids:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        if cmig_id is not None and cmig_id not in ac_cmig_ids:
            raise HTTPException(status_code=403, detail="CMIG fora do escopo do usuário")

    items: list[dict] = []

    # Pré-computa IDs de produtos com estoque FULL > 0 dentro do escopo da view.
    # Necessário para incluir produtos que só vivem no Full (sem nenhuma unidade
    # local) — sem isto eles seriam filtrados pelo WHERE de stock local abaixo.
    full_pg_ids: set[int] = set()
    full_cmig_ids: set[int] = set()
    full_scope_account_ids: list[int] | None = None  # restringe full_stock por escopo

    full_id_q = (
        select(FullStock.product_type, FullStock.product_id, MarketplaceAccount.id)
        .join(MarketplaceAccount, MarketplaceAccount.id == FullStock.marketplace_account_id)
        .where(FullStock.qty > 0)
    )
    if cmig_id is not None:
        full_id_q = full_id_q.where(MarketplaceAccount.cmig_id == cmig_id)
    elif ac_cmig_ids:
        full_id_q = full_id_q.where(MarketplaceAccount.cmig_id.in_(ac_cmig_ids))

    full_id_rows = (await db.execute(full_id_q)).all()
    scoped_accts: set[int] = set()
    for r in full_id_rows:
        scoped_accts.add(r.id)
        if r.product_type == "pg":
            full_pg_ids.add(r.product_id)
        elif r.product_type == "cmig":
            full_cmig_ids.add(r.product_id)
    if cmig_id is not None or ac_cmig_ids:
        full_scope_account_ids = list(scoped_accts)

    # ----- PG -----
    if scope in (None, "pg"):
        q_pg = select(
            CatalogProduct.id,
            CatalogProduct.sku,
            CatalogProduct.ean,
            CatalogProduct.title,
            CatalogProduct.warehouse_id,
            CatalogProduct.stock_quantity,
            CatalogProduct.reserved_quantity,
            CatalogProduct.awaiting_return_quantity,
            CatalogProduct.pending_validation_quantity,
            CatalogProduct.unfit_quantity,
        )
        local_pg_filter = (
            (CatalogProduct.stock_quantity > 0)
            | (CatalogProduct.reserved_quantity > 0)
            | (CatalogProduct.awaiting_return_quantity > 0)
            | (CatalogProduct.pending_validation_quantity > 0)
            | (CatalogProduct.unfit_quantity > 0)
        )
        if full_pg_ids:
            q_pg = q_pg.where(local_pg_filter | CatalogProduct.id.in_(full_pg_ids))
        else:
            q_pg = q_pg.where(local_pg_filter)
        if search:
            term = f"%{search}%"
            q_pg = q_pg.where(
                or_(
                    CatalogProduct.title.ilike(term),
                    CatalogProduct.sku.ilike(term),
                    CatalogProduct.ean.ilike(term),
                )
            )
        if warehouse_id is not None:
            q_pg = q_pg.where(CatalogProduct.warehouse_id == warehouse_id)

        for row in (await db.execute(q_pg)).all():
            physical = int(row.stock_quantity or 0)
            reserved = int(row.reserved_quantity or 0)
            items.append({
                "product_type": "pg",
                "product_id": row.id,
                "sku": row.sku,
                "ean": row.ean,
                "name": row.title,
                "warehouse_id": row.warehouse_id,
                "cmig_id": None,
                "physical": physical,
                "reserved": reserved,
                "available": max(0, physical - reserved),
                "awaiting_return": int(row.awaiting_return_quantity or 0),
                "pending_validation": int(row.pending_validation_quantity or 0),
                "unfit": int(row.unfit_quantity or 0),
            })

    # ----- CMIG -----
    if scope in (None, "cmig"):
        q_cmig = (
            select(
                CMIGProduct.id,
                CMIGProduct.sku_cmig,
                CMIGProduct.ean,
                CMIGProduct.title,
                CMIGProduct.cmig_id,
                CMIG.warehouse_id,
                CMIGProduct.stock_quantity,
                CMIGProduct.reserved_quantity,
                CMIGProduct.awaiting_return_quantity,
                CMIGProduct.pending_validation_quantity,
                CMIGProduct.unfit_quantity,
            )
            .join(CMIG, CMIG.id == CMIGProduct.cmig_id)
        )
        local_cmig_filter = (
            (CMIGProduct.stock_quantity > 0)
            | (CMIGProduct.reserved_quantity > 0)
            | (CMIGProduct.awaiting_return_quantity > 0)
            | (CMIGProduct.pending_validation_quantity > 0)
            | (CMIGProduct.unfit_quantity > 0)
        )
        if full_cmig_ids:
            q_cmig = q_cmig.where(local_cmig_filter | CMIGProduct.id.in_(full_cmig_ids))
        else:
            q_cmig = q_cmig.where(local_cmig_filter)
        if search:
            term = f"%{search}%"
            q_cmig = q_cmig.where(
                or_(
                    CMIGProduct.title.ilike(term),
                    CMIGProduct.sku_cmig.ilike(term),
                    CMIGProduct.ean.ilike(term),
                )
            )
        if warehouse_id is not None:
            q_cmig = q_cmig.where(CMIG.warehouse_id == warehouse_id)
        if cmig_id is not None:
            q_cmig = q_cmig.where(CMIGProduct.cmig_id == cmig_id)
        elif ac_cmig_ids:
            q_cmig = q_cmig.where(CMIGProduct.cmig_id.in_(ac_cmig_ids))

        for row in (await db.execute(q_cmig)).all():
            physical = int(row.stock_quantity or 0)
            reserved = int(row.reserved_quantity or 0)
            items.append({
                "product_type": "cmig",
                "product_id": row.id,
                "sku": row.sku_cmig,
                "ean": row.ean,
                "name": row.title,
                "warehouse_id": row.warehouse_id,
                "cmig_id": row.cmig_id,
                "physical": physical,
                "reserved": reserved,
                "available": max(0, physical - reserved),
                "awaiting_return": int(row.awaiting_return_quantity or 0),
                "pending_validation": int(row.pending_validation_quantity or 0),
                "unfit": int(row.unfit_quantity or 0),
            })

    # Agrupa full_stock por (product_type, product_id), respeitando o escopo
    # de CMIG do usuário/filtro (evita vazar FULL de outras CMIGs).
    full_q = select(
        FullStock.product_type,
        FullStock.product_id,
        FullStock.marketplace_account_id,
        FullStock.qty,
    )
    if full_scope_account_ids is not None:
        if not full_scope_account_ids:
            full_rows = []
        else:
            full_q = full_q.where(
                FullStock.marketplace_account_id.in_(full_scope_account_ids)
            )
            full_rows = (await db.execute(full_q)).all()
    else:
        full_rows = (await db.execute(full_q)).all()
    full_map: dict[tuple, dict] = {}
    for fr in full_rows:
        key = (fr.product_type, fr.product_id)
        if key not in full_map:
            full_map[key] = {}
        full_map[key][fr.marketplace_account_id] = int(fr.qty or 0)

    for item in items:
        key = (item["product_type"], item["product_id"])
        acct_map = full_map.get(key, {})
        item["full_stock"] = acct_map
        item["full_stock_total"] = sum(acct_map.values())

    sort_keys = {
        "sku": lambda i: (i.get("sku") or "").lower(),
        "name": lambda i: (i.get("name") or "").lower(),
        "physical": lambda i: i["physical"],
        "available": lambda i: i["available"],
    }
    items.sort(key=sort_keys[sort_by], reverse=(sort_dir == "desc"))

    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start: start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/cmig/{cmig_id}/sync-full")
async def sync_full_stock_for_cmig(
    cmig_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-lê o estoque FULL no Mercado Livre para todos os anúncios fulfillment da CMIG
    e regrava `full_stock` (e `listing.qty_full`) com o valor canônico do ML.

    - AC: precisa ser administrador da CMIG.
    - UGO/admin/GO: liberado.
    - Itera as contas ML da CMIG. Para cada conta, pega listings publicados com
      `logistic_type='fulfillment'` ou `is_full=true`, busca em lote em /items
      e usa `available_quantity` como verdade absoluta do ML.
    - `full_stock` é zerado antes para essa CMIG (linhas das contas dela) e
      reconstruído com a soma por (product_type, product_id, account_id).
    """
    from services import ml_service
    from models.integration import MarketplaceAccount
    from models.product import ProductListing

    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    cmig = (
        await db.execute(select(CMIG).where(CMIG.id == cmig_id))
    ).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")

    if current_user.role == "ac":
        allowed = await db.execute(
            select(CMIGAdministrator.id).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == cmig_id,
            )
        )
        if allowed.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="CMIG fora do escopo do usuário")

    accounts = (
        await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.cmig_id == cmig_id,
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,
            )
        )
    ).scalars().all()

    summary = {
        "cmig_id": cmig_id,
        "accounts_processed": 0,
        "accounts_skipped": 0,
        "listings_synced": 0,
        "listings_errors": 0,
        "unique_pools": 0,        # N pools de estoque distintos no ML
        "duplicate_listings": 0,  # listings que compartilham pool (não somam de novo)
        "errors": [],
    }

    # Reseta full_stock das contas da CMIG (mantemos só as linhas que reconstruirmos)
    account_ids = [a.id for a in accounts]
    if account_ids:
        await db.execute(
            update(FullStock)
            .where(FullStock.marketplace_account_id.in_(account_ids))
            .values(qty=0)
        )

    for account in accounts:
        try:
            access_token = await _ensure_token(account, db)
        except HTTPException as exc:
            summary["accounts_skipped"] += 1
            summary["errors"].append({
                "account_id": account.id,
                "stage": "token",
                "error": exc.detail,
            })
            continue

        listings = (
            await db.execute(
                select(ProductListing).where(
                    ProductListing.account_id == account.id,
                    ProductListing.status == "published",
                    ProductListing.platform_item_id.isnot(None),
                    or_(
                        ProductListing.logistic_type == "fulfillment",
                        ProductListing.is_full == True,
                    ),
                )
            )
        ).scalars().all()

        if not listings:
            summary["accounts_processed"] += 1
            continue

        item_ids = [lst.platform_item_id for lst in listings if lst.platform_item_id]
        try:
            ml_items = await ml_service.get_items_bulk(access_token, item_ids)
        except Exception as exc:
            summary["accounts_skipped"] += 1
            summary["errors"].append({
                "account_id": account.id,
                "stage": "ml_fetch",
                "error": str(exc),
            })
            continue

        ml_by_id = {it.get("id"): it for it in ml_items if it.get("id")}

        # Deduplica por pool de estoque do ML:
        #   - listings com mesmo `user_product_id` compartilham o MESMO pool no galpão
        #     ML (catálogo, family/optin) — devem ser contados UMA vez por pool.
        #   - listings sem `user_product_id` (não-catálogo) são pools independentes,
        #     cada MLB é seu próprio pool → chave fallback é o platform_item_id.
        # seen_pools mapeia (product_type, product_id, pool_key) → qty
        seen_pools: dict[tuple[str, int, str], int] = {}

        for lst in listings:
            ml_item = ml_by_id.get(lst.platform_item_id)
            if not ml_item:
                summary["listings_errors"] += 1
                summary["errors"].append({
                    "account_id": account.id,
                    "listing_id": lst.id,
                    "platform_item_id": lst.platform_item_id,
                    "stage": "ml_item_missing",
                    "error": "Item não retornou em /items (pode ter sido pausado/removido).",
                })
                continue

            available_qty = int(ml_item.get("available_quantity") or 0)
            user_product_id = ml_item.get("user_product_id")
            pool_key = (
                f"UP:{user_product_id}" if user_product_id
                else f"MLB:{lst.platform_item_id}"
            )

            lst.qty_full = available_qty

            if lst.cmig_product_id:
                ptype, pid = "cmig", lst.cmig_product_id
            elif lst.catalog_product_id:
                ptype, pid = "pg", lst.catalog_product_id
            else:
                # listing sem produto vinculado: qty_full atualizado mas sem agregar
                summary["listings_synced"] += 1
                continue

            k = (ptype, pid, pool_key)
            if k in seen_pools:
                summary["duplicate_listings"] += 1
            else:
                seen_pools[k] = available_qty
            summary["listings_synced"] += 1

        # Soma pools únicos por (product_type, product_id) dentro da conta
        agg: dict[tuple[str, int], int] = {}
        for (ptype, pid, _pool_key), qty in seen_pools.items():
            agg[(ptype, pid)] = agg.get((ptype, pid), 0) + qty
        summary["unique_pools"] += len(seen_pools)

        # Upsert full_stock para essa conta
        for (ptype, pid), qty in agg.items():
            existing = (
                await db.execute(
                    select(FullStock).where(
                        FullStock.product_type == ptype,
                        FullStock.product_id == pid,
                        FullStock.marketplace_account_id == account.id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.qty = qty
            else:
                db.add(
                    FullStock(
                        product_type=ptype,
                        product_id=pid,
                        marketplace_account_id=account.id,
                        qty=qty,
                    )
                )

        summary["accounts_processed"] += 1

    await db.commit()
    return summary


async def _ensure_token(account, db: AsyncSession) -> str:
    """Retorna access_token válido, fazendo refresh se necessário."""
    from datetime import datetime, timedelta, timezone
    from services import ml_service

    now = datetime.now(timezone.utc)
    expires = account.token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= now:
        if not account.refresh_token:
            raise HTTPException(
                status_code=401,
                detail=f"Conta {account.id} sem refresh_token — reconecte em Integrações.",
            )
        try:
            token_data = await ml_service.refresh_ml_token(account.refresh_token)
        except HTTPException as exc:
            if exc.status_code == 401 and "invalid_grant" in (exc.detail or "").lower():
                account.requires_reauth = True
                await db.commit()
            raise
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data.get("refresh_token", account.refresh_token)
        account.token_expires_at = now + timedelta(seconds=token_data.get("expires_in", 21600))
        await db.commit()
    return account.access_token


@router.post("/recompute-all")
async def recompute_all_stock_endpoint(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("ugo", "admin")),
):
    """Recalcula stock_quantity de TODOS os produtos a partir dos eventos (NF-e + pedidos).

    Executar após zerar o estoque (SQL 74) para reconstruir os valores canônicos.
    Roda em background — retorna imediatamente.
    """
    async def _run():
        from services.fiscal.stock_calculator import recompute_all_stock
        from services.stock_reservation_service import recompute_reservations_from_movements
        async with task_db() as db:
            # Reativa stock_updated nas NF-e de entrada já finalizadas/autorizadas,
            # pois o replay usa essa flag para incluir a NF-e nos eventos de estoque.
            await db.execute(
                update(Invoice)
                .where(
                    Invoice.direction == "in",
                    Invoice.status.in_(("finalized", "authorized")),
                )
                .values(stock_updated=True)
            )
            await db.commit()
            result = await recompute_all_stock(db)
            await db.commit()
            logger.info("recompute_all_stock: %s", result)
        # Recomputa reserved_quantity em sessão separada (após commit do stock_quantity)
        async with task_db() as db2:
            res_result = await recompute_reservations_from_movements(db2)
            logger.info("recompute_reservations: %s", res_result)

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Recompute iniciado em background"}


@router.post("/recompute-reservations")
async def recompute_reservations_endpoint(
    current_user: User = Depends(require_role("ugo", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Reconstrói reserved_quantity de todos os produtos a partir dos stock_movements.

    Use após executar SQL 74 (zero_all_stock) para restaurar as reservas ativas
    sem precisar refazer o recompute completo de estoque físico.
    """
    from services.stock_reservation_service import recompute_reservations_from_movements
    result = await recompute_reservations_from_movements(db)
    return {"ok": True, **result}


@router.get("/snapshots")
async def stock_snapshots(
    product_type: str | None = Query(None, regex="^(pg|cmig)$"),
    product_id: int | None = Query(None),
    cmig_id: int | None = Query(None),
    from_date: str | None = Query(None, description="YYYY-MM-DD inclusive"),
    to_date: str | None = Query(None, description="YYYY-MM-DD inclusive"),
    limit: int = Query(500, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Histórico diário de estoque (Fase 2 — trilha contábil).

    Lê de `stock_snapshots`, populado por job APScheduler 02:30 UTC.
    Filtros opcionais por produto, CMIG, e janela de datas. Permite responder
    'qual era meu estoque em 31/12?' para fechamento contábil.
    """
    from datetime import date as _date
    from models.stock_snapshot import StockSnapshot

    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    q = select(StockSnapshot).order_by(
        StockSnapshot.snapshot_date.desc(), StockSnapshot.id.desc()
    )

    # AC só vê snapshots de produtos CMIG das CMIGs que administra
    if current_user.role == "ac":
        ac_cmig_rows = await db.execute(
            select(CMIGAdministrator.cmig_id).where(
                CMIGAdministrator.user_id == current_user.id
            )
        )
        ac_cmig_ids = [r[0] for r in ac_cmig_rows.all()]
        if not ac_cmig_ids:
            return {"items": [], "count": 0}
        q = q.where(StockSnapshot.cmig_id.in_(ac_cmig_ids))
        q = q.where(StockSnapshot.product_type == "cmig")

    if product_type:
        q = q.where(StockSnapshot.product_type == product_type)
    if product_id:
        q = q.where(StockSnapshot.product_id == product_id)
    if cmig_id is not None:
        q = q.where(StockSnapshot.cmig_id == cmig_id)
    if from_date:
        try:
            q = q.where(StockSnapshot.snapshot_date >= _date.fromisoformat(from_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="from_date inválido (use YYYY-MM-DD)")
    if to_date:
        try:
            q = q.where(StockSnapshot.snapshot_date <= _date.fromisoformat(to_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="to_date inválido (use YYYY-MM-DD)")

    q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return {
        "items": [
            {
                "id": s.id,
                "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
                "product_type": s.product_type,
                "product_id": s.product_id,
                "cmig_id": s.cmig_id,
                "sku": s.sku,
                "physical": int(s.physical or 0),
                "reserved": int(s.reserved or 0),
                "available": int(s.available or 0),
                "awaiting_return": int(s.awaiting_return or 0),
                "pending_validation": int(s.pending_validation or 0),
                "unfit": int(s.unfit or 0),
                "full_qty": int(s.full_qty or 0),
                "full_reserved": int(s.full_reserved or 0),
                "drift_detected": bool(s.drift_detected),
                "drift_details": s.drift_details,
            }
            for s in rows
        ],
        "count": len(rows),
    }


@router.get("/card/{product_type}/{product_id}")
async def stock_card(
    product_type: str,
    product_id: int,
    account_id: int | None = Query(None, description="Filtra FULL por conta ML; None agrega todas"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Card canônico LIVE de estoque para um produto.

    Fonte da verdade única usada por todas as telas (Anúncios, Pedidos, Controle de
    Estoque). Retorna físico, reservado, disponível tanto Local quanto FULL, e
    detalhamento FULL por conta ML.
    """
    if product_type not in ("pg", "cmig"):
        raise HTTPException(status_code=400, detail="product_type deve ser 'pg' ou 'cmig'")
    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    # AC só vê produtos CMIG das CMIGs que administra
    if current_user.role == "ac":
        if product_type == "pg":
            raise HTTPException(status_code=403, detail="AC acessa apenas produtos CMIG")
        cmig_row = await db.execute(
            select(CMIGProduct.cmig_id).where(CMIGProduct.id == product_id)
        )
        owner_cmig_id = cmig_row.scalar_one_or_none()
        if owner_cmig_id is None:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        allowed = await db.execute(
            select(CMIGAdministrator.id).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == owner_cmig_id,
            )
        )
        if allowed.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="CMIG fora do escopo do usuário")

    from services.stock_view import get_stock_card
    return await get_stock_card(db, product_type, product_id, account_id=account_id)


@router.get("/{product_type}/{product_id}/movements")
async def product_movements(
    product_type: str,
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    # AC só vê movimentos de produtos de CMIGs que administra
    if current_user.role == "ac":
        if product_type != "cmig":
            raise HTTPException(status_code=403, detail="AC acessa apenas produtos CMIG")
        cmig_row = await db.execute(
            select(CMIGProduct.cmig_id).where(CMIGProduct.id == product_id)
        )
        owner_cmig_id = cmig_row.scalar_one_or_none()
        if owner_cmig_id is None:
            raise HTTPException(status_code=404, detail="Produto não encontrado")
        allowed = await db.execute(
            select(CMIGAdministrator.id).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == owner_cmig_id,
            )
        )
        if allowed.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="CMIG fora do escopo do usuário")

    q = (
        select(StockMovement)
        .where(
            StockMovement.product_type == product_type,
            StockMovement.product_id == product_id,
        )
        .order_by(StockMovement.created_at.desc())
    )
    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "items": [
            {
                "id": m.id,
                "movement_type": m.movement_type,
                "qty": m.qty,
                "field_affected": m.field_affected,
                "delta": m.delta,
                "order_id": m.order_id,
                "return_id": m.return_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

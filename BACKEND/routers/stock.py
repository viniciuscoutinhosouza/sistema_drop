import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, task_db
from dependencies import get_current_user, require_menu_permission
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.fiscal import Invoice
from models.full_stock import FullStock
from models.integration import MarketplaceAccount
from models.product import CatalogProduct
from models.stock_movement import StockMovement
from models.user import User
from services.datetime_br import now_br

logger = logging.getLogger(__name__)
router = APIRouter()

# Teto defensivo do export: evita PDF/planilha gigante (e worker preso) quando admin/ugo
# exporta sem filtro. Acima disso, trunca e avisa no subtítulo.
_MAX_EXPORT_ROWS = 5000


async def _collect_stock_items(
    db: AsyncSession,
    current_user: User,
    *,
    search: str | None = None,
    scope: str | None = None,
    warehouse_id: int | None = None,
    cmig_id: int | None = None,
    show_zeroed: bool = False,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> list[dict]:
    """Lista COMPLETA (sem paginação) de itens de estoque no escopo do usuário.

    Fonte única do Controle de Estoque: usada pela tela (paginada) e pelo export. Aplica o
    MESMO controle de acesso (roles; AC escopado às suas CMIGs) e o MESMO escopo de FULL por
    conta — não vazar FULL de outras contas/CMIGs.
    """
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
            return []
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
        if show_zeroed:
            pass  # mostra todos os PG (inclui zerados)
        elif full_pg_ids:
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
                "cmig_name": None,
                "is_full_mirror": False,
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
                CMIGProduct.is_full_mirror,
                CMIG.trade_name,
                CMIG.company_name,
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
        if show_zeroed:
            pass  # mostra todos os CMIG (inclui zerados)
        elif full_cmig_ids:
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
                "cmig_name": row.trade_name or row.company_name or f"CMIG {row.cmig_id}",
                "is_full_mirror": bool(row.is_full_mirror),
                "physical": physical,
                "reserved": reserved,
                "available": max(0, physical - reserved),
                "awaiting_return": int(row.awaiting_return_quantity or 0),
                "pending_validation": int(row.pending_validation_quantity or 0),
                "unfit": int(row.unfit_quantity or 0),
            })

    # FULL por (product_type, product_id) — reusa o SSOT load_full_per_account_map,
    # que segue o vínculo pg_product_id (FULL do CMIG espelho aparece no card do PG).
    # Mantém paridade com o card/anúncios/pedidos. Escopo de conta evita vazar FULL.
    from services.stock_view import load_full_per_account_map

    if full_scope_account_ids is not None and not full_scope_account_ids:
        full_map = {}  # escopo CMIG sem contas → nenhum FULL (evita carregar tudo)
    else:
        # follow_pg_link=False: o FULL aparece SÓ na linha do produto CMIG (FULL é do
        # CMIG). Sem isso, o mesmo FULL apareceria na linha PG e na CMIG (duplicado).
        full_map = await load_full_per_account_map(
            db,
            pg_ids=[it["product_id"] for it in items if it["product_type"] == "pg"],
            cmig_ids=[it["product_id"] for it in items if it["product_type"] == "cmig"],
            account_ids=full_scope_account_ids,
            follow_pg_link=False,
        )
    for item in items:
        acct_map = full_map.get((item["product_type"], item["product_id"]), {})
        item["full_stock"] = {acct: int(d.get("qty", 0) or 0) for acct, d in acct_map.items()}
        item["full_stock_total"] = sum(item["full_stock"].values())

    sort_keys = {
        "sku": lambda i: (i.get("sku") or "").lower(),
        "name": lambda i: (i.get("name") or "").lower(),
        "physical": lambda i: i["physical"],
        "available": lambda i: i["available"],
    }
    items.sort(key=sort_keys[sort_by], reverse=(sort_dir == "desc"))
    return items


@router.get("/summary")
async def stock_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str = Query(None),
    scope: str = Query(None, regex="^(pg|cmig)$"),
    warehouse_id: int = Query(None),
    cmig_id: int = Query(None),
    show_zeroed: bool = Query(False),  # incluir produtos zerados (local e full)
    sort_by: str = Query("name", regex="^(sku|name|physical|available)$"),
    sort_dir: str = Query("asc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await _collect_stock_items(
        db, current_user, search=search, scope=scope, warehouse_id=warehouse_id,
        cmig_id=cmig_id, show_zeroed=show_zeroed, sort_by=sort_by, sort_dir=sort_dir,
    )
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start: start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _tipo_label(item: dict) -> str:
    if item.get("product_type") == "pg":
        return "PG"
    name = item.get("cmig_name")
    return f"CMIG · {name}" if name else "CMIG"


@router.get("/summary/export")
async def stock_summary_export(
    format: str = Query("xlsx", pattern="^(pdf|xlsx)$"),
    search: str = Query(None),
    scope: str = Query(None, regex="^(pg|cmig)$"),
    warehouse_id: int = Query(None),
    cmig_id: int = Query(None),
    show_zeroed: bool = Query(False),
    sort_by: str = Query("name", regex="^(sku|name|physical|available)$"),
    sort_dir: str = Query("asc", regex="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporta o Controle de Estoque (os mesmos itens/filtros da tela) em PDF ou Excel."""
    from services import stock_export

    items = await _collect_stock_items(
        db, current_user, search=search, scope=scope, warehouse_id=warehouse_id,
        cmig_id=cmig_id, show_zeroed=show_zeroed, sort_by=sort_by, sort_dir=sort_dir,
    )
    total = len(items)
    truncated = total > _MAX_EXPORT_ROWS
    if truncated:
        items = items[:_MAX_EXPORT_ROWS]
    for it in items:
        it["tipo_label"] = _tipo_label(it)

    scope_label = {"pg": "Galpão (PG)", "cmig": "CMIG"}.get(scope, "Todos")
    parts = [scope_label]
    if search:
        parts.append(f"busca: {search}")
    if show_zeroed:
        parts.append("incluindo zerados")
    parts.append(
        f"{len(items)} de {total} produto(s) — teto de {_MAX_EXPORT_ROWS}, refine os filtros"
        if truncated else f"{total} produto(s)"
    )
    subtitle = " · ".join(parts)

    stamp = now_br().strftime("%Y%m%d_%H%M")
    # Render (reportlab/openpyxl) é CPU-bound e síncrono → fora do event loop.
    if format == "pdf":
        content = await asyncio.to_thread(stock_export.build_pdf, items, subtitle)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="controle-estoque_{stamp}.pdf"'},
        )
    content = await asyncio.to_thread(stock_export.build_xlsx, items, subtitle)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="controle-estoque_{stamp}.xlsx"'},
    )


@router.post("/cmig/{cmig_id}/sync-full")
async def sync_full_stock_for_cmig(
    cmig_id: int,
    background_tasks: BackgroundTasks,
    resync_on_drift: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CONFERÊNCIA do estoque FULL contra o Mercado Livre (ADR-0010).

    O `qty` do FULL é canônico via NF-e (remessas REAIS − vendas enviadas − retornos),
    mantido em `full_stock` por produto **CMIG**. Este endpoint NÃO sobrescreve o `qty`:
    ele lê o `available_quantity` do ML e COMPARA com o nosso disponível
    (qty − reserved) por produto CMIG/conta, reportando divergências (`drift`).
    Quando há divergência e `resync_on_drift`, dispara em background a re-sincronização
    das NF-e do mês corrente (que ajusta o `qty`). FULL é sempre do CMIG: anúncios
    só-PG resolvem o CMIGProduct espelho (auto-criado se necessário).
    """
    from datetime import datetime

    from models.integration import MarketplaceAccount
    from models.product import ProductListing
    from services import ml_service
    from services.datetime_br import BR_TZ
    from services.full_stock_service import resolve_full_cmig_product

    if current_user.role not in ("ugo", "admin", "ac", "go"):
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
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
                MarketplaceAccount.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    summary = {
        "cmig_id": cmig_id,
        "accounts_processed": 0,
        "accounts_skipped": 0,
        "listings_checked": 0,
        "unique_pools": 0,
        "drift": [],          # [{account_id, cmig_product_id, ml_available, sistema_available, diff}]
        "resync_triggered": False,
        "errors": [],
    }

    drift_accounts: set[int] = set()

    for account in accounts:
        try:
            access_token = await _ensure_token(account, db)
        except HTTPException as exc:
            summary["accounts_skipped"] += 1
            summary["errors"].append({"account_id": account.id, "stage": "token", "error": exc.detail})
            continue

        listings = (
            await db.execute(
                select(ProductListing).where(
                    ProductListing.account_id == account.id,
                    ProductListing.status == "published",
                    ProductListing.platform_item_id.isnot(None),
                    or_(
                        ProductListing.logistic_type == "fulfillment",
                        ProductListing.is_full == True,  # noqa: E712
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
        except Exception as exc:  # noqa: BLE001
            summary["accounts_skipped"] += 1
            summary["errors"].append({"account_id": account.id, "stage": "ml_fetch", "error": str(exc)})
            continue
        ml_by_id = {it.get("id"): it for it in ml_items if it.get("id")}

        # available_quantity do ML por pool → produto CMIG (FULL é sempre do CMIG).
        seen_pools: dict[tuple[int, str], int] = {}
        for lst in listings:
            ml_item = ml_by_id.get(lst.platform_item_id)
            if not ml_item:
                summary["errors"].append({
                    "account_id": account.id, "listing_id": lst.id,
                    "platform_item_id": lst.platform_item_id, "stage": "ml_item_missing",
                    "error": "Item não retornou em /items (pausado/removido?).",
                })
                continue
            available_qty = int(ml_item.get("available_quantity") or 0)
            user_product_id = ml_item.get("user_product_id")
            pool_key = f"UP:{user_product_id}" if user_product_id else f"MLB:{lst.platform_item_id}"
            lst.qty_full = available_qty  # snapshot p/ referência

            cp = await resolve_full_cmig_product(
                db, cmig_id=cmig_id,
                cmig_product_id=lst.cmig_product_id,
                catalog_product_id=lst.catalog_product_id,
                ml_item_id=lst.platform_item_id, account_id=account.id,
                create=True,
            )
            if not cp:
                continue
            summary["listings_checked"] += 1
            k = (cp.id, pool_key)
            if k not in seen_pools:
                seen_pools[k] = available_qty

        ml_by_cmig: dict[int, int] = {}
        for (cmig_pid, _pool), qty in seen_pools.items():
            ml_by_cmig[cmig_pid] = ml_by_cmig.get(cmig_pid, 0) + qty
        summary["unique_pools"] += len(seen_pools)

        # Compara ML vs sistema (qty − reserved) por produto CMIG.
        for cmig_pid, ml_avail in ml_by_cmig.items():
            row = (
                await db.execute(
                    select(FullStock.qty, FullStock.reserved_qty).where(
                        FullStock.product_type == "cmig",
                        FullStock.product_id == cmig_pid,
                        FullStock.marketplace_account_id == account.id,
                    )
                )
            ).first()
            sis_avail = max(0, int(row[0] or 0) - int(row[1] or 0)) if row else 0
            if ml_avail != sis_avail:
                summary["drift"].append({
                    "account_id": account.id, "cmig_product_id": cmig_pid,
                    "ml_available": ml_avail, "sistema_available": sis_avail,
                    "diff": ml_avail - sis_avail,
                })
                drift_accounts.add(account.id)

        summary["accounts_processed"] += 1

    await db.commit()

    # Divergência → re-sincroniza as NF-e do mês corrente em background (ajusta o qty).
    if resync_on_drift and drift_accounts:
        now_brt = datetime.now(BR_TZ)
        for acc_id in drift_accounts:
            background_tasks.add_task(
                _resync_account_month, acc_id, cmig_id, now_brt.year, now_brt.month, current_user.id
            )
        summary["resync_triggered"] = True

    return summary


async def _resync_account_month(account_id: int, cmig_id: int, year: int, month: int, user_id: int):
    """Wrapper para disparar a re-sync de NF-e de uma conta/mês em background."""
    from routers.invoices import _sync_ml_fiscal_account

    try:
        await _sync_ml_fiscal_account(account_id, cmig_id, year, month, user_id)
    except Exception:  # noqa: BLE001
        logger.exception("[sync-full] re-sync NF-e falhou (conta %s %s/%s)", account_id, month, year)


@router.post("/migrate-full-pg-to-cmig")
async def migrate_full_pg_to_cmig(
    dry_run: bool = Query(True),
    current_user: User = Depends(require_menu_permission("estoque")),
    db: AsyncSession = Depends(get_db),
):
    """Migração one-off (ADR-0010): converte `full_stock` product_type='pg' → 'cmig'.

    FULL é sempre do CMIG. Auto-cria o CMIGProduct espelho quando faltar; agrega por
    (cmig_product, conta) preservando `reserved_qty`; faz merge na linha CMIG existente
    ou converte a linha PG in place. `dry_run=True` (default) só relata (rollback);
    `dry_run=False` aplica. Idempotente (rerodar não acha mais linhas PG)."""
    from services.full_stock_service import _cmig_id_for_account, resolve_full_cmig_product

    pg_rows = (
        await db.execute(select(FullStock).where(FullStock.product_type == "pg"))
    ).scalars().all()
    report: dict = {
        "dry_run": dry_run, "pg_rows": len(pg_rows), "auto_created": 0,
        "merged": 0, "converted": 0, "deleted_rows": 0, "targets": 0, "skipped": [],
    }

    # Agrega por (cmig_product_alvo, conta) ANTES de escrever (evita ORA-00001 no índice
    # único quando vários PG resolvem para o mesmo CMIG+conta).
    targets: dict[tuple[int, int], dict] = {}
    for fs in pg_rows:
        cmig_id = await _cmig_id_for_account(db, fs.marketplace_account_id)
        if not cmig_id:
            report["skipped"].append({"fs_id": fs.id, "reason": "conta sem cmig"})
            continue
        cp = await resolve_full_cmig_product(
            db, cmig_id=cmig_id, catalog_product_id=fs.product_id, create=False
        )
        if not cp:
            cp = await resolve_full_cmig_product(
                db, cmig_id=cmig_id, catalog_product_id=fs.product_id, create=True
            )
            if cp:
                report["auto_created"] += 1
        if not cp:
            report["skipped"].append({"fs_id": fs.id, "pg_id": fs.product_id, "reason": "sem PG resolvível"})
            continue
        t = targets.setdefault((cp.id, fs.marketplace_account_id), {"qty": 0, "reserved": 0, "rows": []})
        t["qty"] += int(fs.qty or 0)
        t["reserved"] += int(fs.reserved_qty or 0)
        t["rows"].append(fs)

    report["targets"] = len(targets)
    for (cmig_pid, acct), t in targets.items():
        existing = (
            await db.execute(
                select(FullStock).where(
                    FullStock.product_type == "cmig",
                    FullStock.product_id == cmig_pid,
                    FullStock.marketplace_account_id == acct,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.qty = int(existing.qty or 0) + t["qty"]
            existing.reserved_qty = int(existing.reserved_qty or 0) + t["reserved"]
            for fs in t["rows"]:
                db.delete(fs)  # síncrono
                report["deleted_rows"] += 1
            report["merged"] += 1
        else:
            first = t["rows"][0]
            first.product_type = "cmig"
            first.product_id = cmig_pid
            first.qty = t["qty"]
            first.reserved_qty = t["reserved"]
            for fs in t["rows"][1:]:
                db.delete(fs)  # síncrono
                report["deleted_rows"] += 1
            report["converted"] += 1
        db.add(StockMovement(  # síncrono — rastro da migração
            product_type="cmig", product_id=cmig_pid, movement_type="full_migrate",
            qty=t["qty"], field_affected="full_stock", delta=0,
        ))

    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    logger.info("[migrate-full-pg-to-cmig] %s", {k: v for k, v in report.items() if k != "skipped"})
    return report


async def _ensure_token(account, db: AsyncSession) -> str:
    """Retorna access_token válido (refresh centralizado e coordenado em ml_auth)."""
    from services.ml_auth import get_valid_token

    return await get_valid_token(account, db)


@router.post("/recompute-all")
async def recompute_all_stock_endpoint(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_menu_permission("estoque")),
):
    """Recalcula stock_quantity de TODOS os produtos a partir dos eventos (NF-e + pedidos),
    reconstrói as reservas e reativa as flags de NF-e de entrada. Roda em background.

    Operação GLOBAL (todas as CMIGs/galpões) — restrita a admin e operador de galpão (UGO).
    Também usada após zerar o estoque (SQL 74) para reconstruir os valores canônicos.
    """
    if current_user.role not in ("admin", "ugo"):
        raise HTTPException(
            status_code=403,
            detail="Apenas admin ou operador de galpão (UGO) podem recalcular o estoque de todos os produtos",
        )
    async def _run():
        from services.fiscal.stock_calculator import recompute_all_stock
        from services.stock_reservation_service import recompute_reservations_from_movements
        async with task_db() as db:
            # Reativa stock_updated nas NF-e de entrada já finalizadas/autorizadas,
            # pois o replay usa essa flag para incluir a NF-e nos eventos de estoque.
            # EXCLUI as notas que devem ficar inertes ao recompute (senão a flag em
            # massa as ressuscitaria): devolução (Fase B — fonte canônica é o Return)
            # e movimentação SIMBÓLICA (regra is_simbolica — não movimenta estoque).
            _nat = func.lower(func.coalesce(Invoice.natureza_operacao, ""))
            await db.execute(
                update(Invoice)
                .where(
                    Invoice.direction == "in",
                    Invoice.status.in_(("finalized", "authorized")),
                    func.coalesce(Invoice.purpose, "") != "devolucao",
                    _nat.notlike("%simbolic%"),
                    _nat.notlike("%simbólic%"),
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
        # Recomputa o estoque FULL por replay (ADR-0019 Fase 1) — sessão própria.
        from services.full_stock_service import recompute_full_stock
        async with task_db() as db3:
            full_result = await recompute_full_stock(db3)
            await db3.commit()
            logger.info("recompute_full_stock: %s", full_result)

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Recompute iniciado em background"}


@router.post("/recompute-reservations")
async def recompute_reservations_endpoint(
    current_user: User = Depends(require_menu_permission("estoque")),
    db: AsyncSession = Depends(get_db),
):
    """Reconstrói reserved_quantity de todos os produtos a partir dos stock_movements.

    Use após executar SQL 74 (zero_all_stock) para restaurar as reservas ativas
    sem precisar refazer o recompute completo de estoque físico.
    """
    from services.stock_reservation_service import recompute_reservations_from_movements
    result = await recompute_reservations_from_movements(db)
    return {"ok": True, **result}


@router.post("/release-orphan-reservations")
async def release_orphan_reservations_endpoint(
    apply: bool = Query(False, description="False = dry-run (não grava); True = aplica"),
    limit: int = Query(1000, ge=1, le=5000),
    current_user: User = Depends(require_menu_permission("estoque")),
    db: AsyncSession = Depends(get_db),
):
    """Libera reservas órfãs de pedidos não-FULL já entregues no ML.

    Pedidos com shipment_status 'shipped'/'delivered' que ainda têm reserva ativa
    (movimento 'reserve' sem fechamento). Libera apenas `reserved_quantity` — NÃO
    toca no estoque físico, que é event-sourced (pedido entregue já é a saída
    canônica). Dry-run por padrão — passe `apply=true` para gravar.
    """
    from services.stock_reservation_service import backfill_orphan_reservations
    result = await backfill_orphan_reservations(db, dry_run=not apply, limit=limit)
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

    from models.order import Order

    count_q = (
        select(func.count())
        .select_from(StockMovement)
        .where(
            StockMovement.product_type == product_type,
            StockMovement.product_id == product_id,
        )
    )
    total = (await db.execute(count_q)).scalar()

    rows = (
        await db.execute(
            select(StockMovement, Order)
            .outerjoin(Order, Order.id == StockMovement.order_id)
            .where(
                StockMovement.product_type == product_type,
                StockMovement.product_id == product_id,
            )
            .order_by(StockMovement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    def _mkt_url(platform, platform_order_id):
        if platform == "mercadolivre" and platform_order_id:
            return f"https://www.mercadolivre.com.br/vendas/{platform_order_id}/detalhe"
        return None

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
                "order_platform": (o.platform if o else None),
                "order_platform_id": (o.platform_order_id if o else None),
                "marketplace_url": _mkt_url(o.platform, o.platform_order_id) if o else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m, o in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

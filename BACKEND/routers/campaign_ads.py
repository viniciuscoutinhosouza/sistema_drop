"""
Campanhas ADS — acompanhamento (read-only) de Product Ads / Catálogo-UP do
Mercado Livre por CMIG. Dados consultados AO VIVO na API de Mercado Ads (sem
job, sem tabela própria). Cada anunciante pertence ao token de uma conta ML,
por isso os endpoints de métricas exigem o par (account_id, advertiser_id).

Gating: require_menu_permission("campanha_ads") + checagem de acesso à conta
(_get_account_or_403, reusado de routers.anuncios).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import services.ml_service as ml_service
from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.cmig import CMIG, CMIGAdministrator
from models.integration import MarketplaceAccount
from models.user import User
from routers.anuncios import _get_account_or_403
from services.ml_auth import get_valid_token

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_RANGE_DAYS = 90  # Limite da API de Mercado Ads.


async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession) -> CMIG:
    """Garante que o usuário pode ver a CMIG (admin/ugo bypass; senão CMIGAdministrator)."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada.")
    if user.role in ("admin", "ugo"):
        return cmig
    link = (
        await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.cmig_id == cmig_id,
                CMIGAdministrator.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG.")
    return cmig


def _validate_range(date_from: str, date_to: str) -> None:
    from datetime import date

    try:
        d0 = date.fromisoformat(date_from)
        d1 = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=422, detail="Datas devem estar no formato YYYY-MM-DD.")
    if d1 < d0:
        raise HTTPException(status_code=422, detail="date_to não pode ser anterior a date_from.")
    if (d1 - d0).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Intervalo máximo permitido pela API do ML é de {MAX_RANGE_DAYS} dias.",
        )


# ── GET /advertisers?cmig_id= ────────────────────────────────────────────────
@router.get("/advertisers")
async def list_advertisers(
    cmig_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("campanha_ads")),
):
    """Lista os anunciantes (Product Ads) das contas ML ativas da CMIG.

    Cada item carrega o account_id de origem — necessário para as consultas de
    métricas (o advertiser é resolvido pelo token daquela conta).
    """
    await _check_cmig_access(cmig_id, current_user, db)

    accounts = (
        await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.cmig_id == cmig_id,
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    advertisers: list[dict] = []
    for acc in accounts:
        if acc.requires_reauth:
            continue
        try:
            token = await get_valid_token(acc, db, margin_seconds=600)
            advs = await ml_service.get_advertisers(token, product_id="PADS")
        except Exception as exc:  # noqa: BLE001 — tolerância por conta
            logger.warning("[campaign-ads] advertisers conta %s falhou: %s", acc.id, exc)
            continue
        for a in advs or []:
            advertisers.append(
                {
                    "account_id": acc.id,
                    "account_description": acc.description or acc.platform_username or acc.email,
                    "advertiser_id": a.get("advertiser_id"),
                    "advertiser_name": a.get("advertiser_name"),
                    "site_id": a.get("site_id") or "MLB",
                }
            )
    return {"advertisers": advertisers}


async def _resolve_account_token(account_id: int, user: User, db: AsyncSession):
    account = await _get_account_or_403(account_id, user, db)
    if account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Conta não é do Mercado Livre.")
    token = await get_valid_token(account, db, margin_seconds=600)
    return account, token


# ── GET /product/campaigns ───────────────────────────────────────────────────
@router.get("/product/campaigns")
async def product_campaigns(
    account_id: int = Query(...),
    advertiser_id: str = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    site_id: str = Query("MLB"),
    status: str | None = Query(None),
    campaign_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("campanha_ads")),
):
    """Campanhas de Product Ads com métricas + totalizador (metrics_summary)."""
    _validate_range(date_from, date_to)
    _, token = await _resolve_account_token(account_id, current_user, db)
    return await ml_service.search_product_ads_campaigns(
        token,
        site_id,
        advertiser_id,
        date_from,
        date_to,
        status=status,
        campaign_ids=campaign_id,
        limit=limit,
        offset=offset,
    )


# ── GET /product/ads ─────────────────────────────────────────────────────────
@router.get("/product/ads")
async def product_ads(
    account_id: int = Query(...),
    advertiser_id: str = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    site_id: str = Query("MLB"),
    campaign_id: int | None = Query(None),
    item_id: str | None = Query(None),
    statuses: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str | None = Query(None),
    sort: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("campanha_ads")),
):
    """Anúncios (ads) de Product Ads com métricas, paginados/ordenáveis."""
    _validate_range(date_from, date_to)
    _, token = await _resolve_account_token(account_id, current_user, db)
    return await ml_service.search_product_ads(
        token,
        site_id,
        advertiser_id,
        date_from,
        date_to,
        campaign_id=campaign_id,
        item_id=item_id,
        statuses=statuses,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort=sort,
    )


# ── GET /product/campaign-detail ─────────────────────────────────────────────
@router.get("/product/campaign-detail")
async def product_campaign_detail(
    account_id: int = Query(...),
    advertiser_id: str = Query(...),
    campaign_id: str = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    site_id: str = Query("MLB"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("campanha_ads")),
):
    """Detalhe de uma campanha com métricas extras de share (impression_share etc.)."""
    _validate_range(date_from, date_to)
    _, token = await _resolve_account_token(account_id, current_user, db)
    return await ml_service.get_campaign_detail(
        token, site_id, advertiser_id, campaign_id, date_from, date_to
    )


# ── GET /product/ad-detail (Raio-X do anúncio) ───────────────────────────────
@router.get("/product/ad-detail")
async def product_ad_detail(
    account_id: int = Query(...),
    advertiser_id: str = Query(...),
    item_id: str = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    site_id: str = Query("MLB"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("campanha_ads")),
):
    """Raio-X do anúncio: métricas agregadas do item + série diária.

    A API do ML só aceita um aggregation_type por chamada, então buscamos as
    duas visões (item + DAILY) em paralelo.
    """
    _validate_range(date_from, date_to)
    _, token = await _resolve_account_token(account_id, current_user, db)
    agg, daily = await asyncio.gather(
        ml_service.search_product_ads(
            token, site_id, advertiser_id, date_from, date_to,
            item_id=item_id, aggregation_type="item", limit=1,
        ),
        ml_service.search_product_ads(
            token, site_id, advertiser_id, date_from, date_to,
            item_id=item_id, aggregation_type="DAILY", metrics_summary=False, limit=200,
        ),
    )
    ad = (agg.get("results") or [{}])[0] if agg.get("results") else {}
    return {"ad": ad, "daily": daily.get("results") or []}


# ── GET /catalog/ad-groups ───────────────────────────────────────────────────
@router.get("/catalog/ad-groups")
async def catalog_ad_groups(
    account_id: int = Query(...),
    advertiser_id: str = Query(...),
    date_from: str = Query(...),
    date_to: str = Query(...),
    site_id: str = Query("MLB"),
    statuses: str | None = Query(None),
    q: str | None = Query(None),
    ad_group_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("campanha_ads")),
):
    """Ad Groups (Catálogo/UP — famílias/catálogos) com métricas + totalizador."""
    _validate_range(date_from, date_to)
    _, token = await _resolve_account_token(account_id, current_user, db)
    return await ml_service.search_ad_groups(
        token,
        site_id,
        advertiser_id,
        date_from,
        date_to,
        statuses=statuses,
        q=q,
        ad_group_id=ad_group_id,
        limit=limit,
        offset=offset,
    )

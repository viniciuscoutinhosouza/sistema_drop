"""Relatórios — "Vendas do Mês" por conta de marketplace (grid + export PDF/Excel)."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.user import User
from routers.anuncios import _get_account_or_403
from services import sales_report_export as export
from services import sales_report_service as svc

router = APIRouter()

_PLATFORM = {"mercadolivre": "Mercado Livre", "shopee": "Shopee", "bling": "Bling"}


def _account_label(acc) -> str:
    plat = _PLATFORM.get(acc.platform, acc.platform or "")
    desc = (
        getattr(acc, "description", None)
        or getattr(acc, "platform_username", None)
        or getattr(acc, "email", None)
        or f"#{acc.id}"
    )
    return f"{plat} — {desc}"


@router.get("/monthly-sales")
async def monthly_sales(
    account_id: int,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(require_role("admin", "ac", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Grid de vendas do mês por produto para a conta."""
    acc = await _get_account_or_403(account_id, current_user, db)
    data = await svc.build_monthly_sales(db, account_id, year, month)
    data["account"] = {"id": acc.id, "label": _account_label(acc)}
    return data


@router.post("/monthly-sales/refresh")
async def monthly_sales_refresh(
    account_id: int,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(require_role("admin", "ac", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Re-sincroniza os pedidos da conta no período e devolve o grid atualizado."""
    acc = await _get_account_or_403(account_id, current_user, db)
    warn = await svc.resync_account_period(db, acc, year, month)
    data = await svc.build_monthly_sales(db, account_id, year, month)
    data["account"] = {"id": acc.id, "label": _account_label(acc)}
    if warn:
        data["refresh_warning"] = warn
    return data


@router.get("/monthly-sales/export")
async def monthly_sales_export(
    account_id: int,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    format: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    current_user: User = Depends(require_role("admin", "ac", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Exporta o relatório em PDF ou Excel."""
    acc = await _get_account_or_403(account_id, current_user, db)
    data = await svc.build_monthly_sales(db, account_id, year, month)
    label = _account_label(acc)
    fname = f"vendas-{data.get('period', '')}-conta-{account_id}"
    if format == "xlsx":
        return Response(
            content=export.build_xlsx(data, label),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
        )
    return Response(
        content=export.build_pdf(data, label),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
    )

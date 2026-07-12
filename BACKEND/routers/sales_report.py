"""Relatórios — Vendas por período, por conta de marketplace (grid + gráfico + PDF/Excel)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
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

# Teto de dias do período — evita varredura desnecessária e relatório gigante.
_MAX_DIAS = 366


def _account_label(acc) -> str:
    plat = _PLATFORM.get(acc.platform, acc.platform or "")
    desc = (
        getattr(acc, "description", None)
        or getattr(acc, "platform_username", None)
        or getattr(acc, "email", None)
        or f"#{acc.id}"
    )
    return f"{plat} — {desc}"


def _validate_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="A data inicial não pode ser maior que a final.")
    if (date_to - date_from).days + 1 > _MAX_DIAS:
        raise HTTPException(status_code=422, detail=f"Período máximo de {_MAX_DIAS} dias.")


@router.get("/monthly-sales")
async def sales_report(
    account_id: int,
    date_from: date = Query(..., description="Data inicial (inclusiva, fuso BR)"),
    date_to: date = Query(..., description="Data final (inclusiva, fuso BR)"),
    current_user: User = Depends(require_role("admin", "ac", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Grid de vendas do período por produto + série diária para o gráfico."""
    _validate_period(date_from, date_to)
    acc = await _get_account_or_403(account_id, current_user, db)
    data = await svc.build_sales_report(db, account_id, date_from, date_to)
    data["account"] = {"id": acc.id, "label": _account_label(acc)}
    return data


@router.post("/monthly-sales/refresh")
async def sales_report_refresh(
    account_id: int,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_role("admin", "ac", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Re-sincroniza os pedidos da conta no período e devolve o relatório atualizado."""
    _validate_period(date_from, date_to)
    acc = await _get_account_or_403(account_id, current_user, db)
    warn = await svc.resync_account_period(db, acc, date_from, date_to)
    data = await svc.build_sales_report(db, account_id, date_from, date_to)
    data["account"] = {"id": acc.id, "label": _account_label(acc)}
    if warn:
        data["refresh_warning"] = warn
    return data


@router.get("/monthly-sales/export")
async def sales_report_export_file(
    account_id: int,
    date_from: date = Query(...),
    date_to: date = Query(...),
    format: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    current_user: User = Depends(require_role("admin", "ac", "go")),
    db: AsyncSession = Depends(get_db),
):
    """Exporta o relatório do período em PDF ou Excel."""
    _validate_period(date_from, date_to)
    acc = await _get_account_or_403(account_id, current_user, db)
    data = await svc.build_sales_report(db, account_id, date_from, date_to)
    label = _account_label(acc)
    fname = f"vendas-{date_from}_a_{date_to}-conta-{account_id}"
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

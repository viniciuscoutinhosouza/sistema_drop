"""Endpoints de geração de relatórios PDF para uma CMIG."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.user import User
from services.cmig_report_service import (
    build_price_table_pdf,
    build_stock_report_pdf,
)

router = APIRouter()


@router.get("/price-table")
async def report_price_table(
    cmig_id: int,
    include_zero_stock: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pdf_bytes = await build_price_table_pdf(db, cmig_id, current_user, include_zero_stock)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="tabela-precos-cmig-{cmig_id}.pdf"'
        },
    )


@router.get("/stock")
async def report_stock(
    cmig_id: int,
    include_zero_stock: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pdf_bytes = await build_stock_report_pdf(db, cmig_id, current_user, include_zero_stock)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="estoque-cmig-{cmig_id}.pdf"'
        },
    )

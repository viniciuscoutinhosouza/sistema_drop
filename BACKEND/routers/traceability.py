"""Relatórios de rastreabilidade (ADR-0027, Fase 6) — entrada × saída por lote/validade/serial.

Endpoints só-leitura sob `/api/v1/traceability`. Gate: usuário autenticado. O recall reverso NÃO
expõe dados pessoais do comprador (só referência de pedido) — LGPD Art. 11 (dado de saúde p/ med).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.user import User
from services import traceability_report_service as reports

router = APIRouter()


@router.get("/lots")
async def get_product_lots(
    product_type: str = Query(..., pattern="^(pg|cmig|variant_pg|variant_cmig)$"),
    product_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lotes de um produto (saldo/validade, FEFO)."""
    return await reports.list_product_lots(db, product_type, product_id)


@router.get("/lots/{lot_id}/ledger")
async def get_lot_ledger(
    lot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kardex do lote: entradas (notas) × saídas (pedidos)."""
    return await reports.lot_ledger(db, lot_id)


@router.get("/expiring")
async def get_expiring(
    days: int = Query(30, ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lotes a vencer em até N dias (com saldo > 0)."""
    return await reports.expiring_lots(db, days)


@router.get("/recall")
async def get_recall(
    lot_code: str = Query(..., min_length=1, max_length=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rastreabilidade reversa: dado um lote → pedidos que o levaram (sem PII do comprador)."""
    return await reports.recall_by_lot(db, lot_code)


@router.get("/serials/{serial}")
async def get_serial(
    serial: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico de uma unidade serial."""
    return await reports.serial_history(db, serial)

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_menu_permission
from models.cmig import CMIG, CMIGAdministrator
from models.dre import DREEntry, DRESnapshot
from models.user import User
from schemas.dre import DREEntryIn, DREEntryUpdate, DRESyncRequest
from schemas.financial import BalanceOut, PIXDepositRequest
from services import dre_service
from services.financial_service import credit_balance, get_balance, get_transactions

router = APIRouter()


@router.get("/balance", response_model=BalanceOut)
async def get_my_balance(
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    balance, reserved = await get_balance(db, current_user.id)
    return BalanceOut(
        balance=balance,
        balance_reserved=reserved,
        available=balance - reserved,
    )


@router.get("/transactions")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    return await get_transactions(
        db,
        dropshipper_id=current_user.id,
        page=page,
        page_size=page_size,
        type_filter=type,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/pix-deposit", status_code=201)
async def register_pix_deposit(
    body: PIXDepositRequest,
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a PIX deposit.
    In production this would be confirmed via bank webhook.
    For now, it credits immediately (manual confirmation flow).
    """
    tx = await credit_balance(
        db,
        dropshipper_id=current_user.id,
        amount=body.amount,
        description=f"Depósito PIX – TXID: {body.pix_txid}",
        reference_type="pix_deposit",
        pix_txid=body.pix_txid,
        pix_key=body.pix_key,
    )
    return {
        "message": "Depósito registrado com sucesso",
        "transaction_id": tx.id,
        "new_balance": float(tx.balance_after),
    }


# ─── Gestão Financeira / DRE ─────────────────────────────────────────────────


async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession) -> CMIG:
    """Valida acesso do usuário à CMIG (admin total; AC via CMIGAdministrator;
    UGO via galpão). Reaproveita o mesmo critério de routers/fiscal_config.py."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    if user.role == "admin":
        return cmig
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        return cmig
    if user.role in ("ac", "go"):
        admin = (
            await db.execute(
                select(CMIGAdministrator).where(
                    CMIGAdministrator.user_id == user.id,
                    CMIGAdministrator.cmig_id == cmig_id,
                )
            )
        ).scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        return cmig
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


@router.get("/dre/cmigs")
async def list_dre_cmigs(
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    """CMIGs visíveis ao usuário para o seletor da DRE."""
    if current_user.role == "admin":
        result = await db.execute(select(CMIG).where(CMIG.is_active == True))  # noqa: E712
    elif current_user.role == "ugo":
        result = await db.execute(
            select(CMIG).where(CMIG.warehouse_id == current_user.warehouse_id)
        )
    else:  # ac / go
        subq = select(CMIGAdministrator.cmig_id).where(
            CMIGAdministrator.user_id == current_user.id
        )
        result = await db.execute(select(CMIG).where(CMIG.id.in_(subq)))
    return [
        {"id": c.id, "trade_name": c.trade_name or c.company_name or f"CMIG #{c.id}"}
        for c in result.scalars().all()
    ]


@router.get("/dre")
async def get_dre(
    cmig_id: int,
    year: int = Query(..., ge=2000, le=2100),
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    """Grade da DRE (12 meses) — só lê snapshots + lançamentos + imposto."""
    await _check_cmig_access(cmig_id, current_user, db)
    return await dre_service.build_dre(db, cmig_id, year)


@router.post("/dre/sync")
async def sync_dre_month(
    body: DRESyncRequest,
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    """Sincroniza um mês com o Mercado Livre (operacional + ADS + billing).

    sync_month gerencia as próprias sessões curtas (libera a conexão durante a
    rede ao ML), então a sessão do request não é repassada — só usada no
    _check_cmig_access acima.
    """
    await _check_cmig_access(body.cmig_id, current_user, db)
    # Libera a conexão do request (a checagem acima abriu uma transação só de leitura)
    # ANTES da fase de rede longa do sync — evita esgotar o pool de conexões.
    await db.rollback()
    result = await dre_service.sync_month(body.cmig_id, body.year, body.month)
    return {
        "message": "Mês sincronizado",
        "month": body.month,
        "source": result["source"],
        "last_synced_at": result["last_synced_at"],
    }


@router.get("/dre/debug")
async def debug_dre_month(
    cmig_id: int,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    """Auditoria: mostra as 3 fontes (banco / ao vivo / billing) do mês para
    depurar divergências de valores. Lê o que o último sync gravou no snapshot."""
    await _check_cmig_access(cmig_id, current_user, db)
    snap = (
        await db.execute(
            select(DRESnapshot).where(
                DRESnapshot.cmig_id == cmig_id,
                DRESnapshot.ref_year == year,
                DRESnapshot.ref_month == month,
            )
        )
    ).scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Mês ainda não sincronizado")
    try:
        recon = json.loads(snap.billing_json) if snap.billing_json else {}
    except (ValueError, TypeError):
        recon = {"raw": snap.billing_json}
    return {
        "cmig_id": cmig_id,
        "year": year,
        "month": month,
        "source": snap.source,
        "last_synced_at": snap.last_synced_at.isoformat() if snap.last_synced_at else None,
        "snapshot": {
            "faturamento": float(snap.faturamento or 0),
            "vendas_canceladas": float(snap.vendas_canceladas or 0),
            "tarifa_venda": float(snap.tarifa_venda or 0),
            "frete_vendedor": float(snap.frete_vendedor or 0),
            "custo_produtos": float(snap.custo_produtos or 0),
            "gasto_ads": float(snap.gasto_ads or 0),
            "devolucao_parcial": float(snap.devolucao_parcial or 0),
        },
        "reconciliacao": recon,
    }


@router.get("/dre/entries")
async def list_dre_entries(
    cmig_id: int,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    await _check_cmig_access(cmig_id, current_user, db)
    return await dre_service.list_entries(db, cmig_id, year, month)


@router.post("/dre/entries", status_code=201)
async def create_dre_entry(
    body: DREEntryIn,
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    await _check_cmig_access(body.cmig_id, current_user, db)
    created = await dre_service.create_entry(
        db, body.cmig_id, current_user.id, body.model_dump()
    )
    return {"message": "Lançamento criado", "count": len(created), "ids": [e.id for e in created]}


async def _get_entry_with_access(
    entry_id: int, user: User, db: AsyncSession
) -> DREEntry:
    entry = (
        await db.execute(select(DREEntry).where(DREEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado")
    await _check_cmig_access(entry.cmig_id, user, db)
    return entry


@router.put("/dre/entries/{entry_id}")
async def update_dre_entry(
    entry_id: int,
    body: DREEntryUpdate,
    scope: str = Query("one", pattern="^(one|future)$"),
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_entry_with_access(entry_id, current_user, db)
    await dre_service.update_entry(db, entry, body.model_dump(exclude_none=True), scope)
    return {"message": "Lançamento atualizado"}


@router.delete("/dre/entries/{entry_id}")
async def delete_dre_entry(
    entry_id: int,
    scope: str = Query("one", pattern="^(one|future)$"),
    current_user: User = Depends(require_menu_permission("financeiro")),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_entry_with_access(entry_id, current_user, db)
    await dre_service.delete_entry(db, entry, scope)
    return {"message": "Lançamento excluído"}

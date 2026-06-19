"""Análise de Concorrência (ML + IA) — inicia estudo em background, consulta status,
histórico, anota (notes) e exclui."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.competitor_analysis import CompetitorAnalysis
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(a: CompetitorAnalysis, *, with_result: bool = True) -> dict:
    result = None
    if with_result and a.result_json:
        try:
            result = json.loads(a.result_json)
        except Exception:
            result = None
    return {
        "id": a.id,
        "product_type": a.product_type,
        "product_id": a.product_id,
        "account_id": a.account_id,
        "desired_margin_pct": float(a.desired_margin_pct) if a.desired_margin_pct is not None else None,
        "status": a.status,
        "progress_step": a.progress_step,
        "user_prompt": a.user_prompt,
        "notes": a.notes,
        "error": a.error,
        "result": result,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "finished_at": a.finished_at.isoformat() if a.finished_at else None,
    }


async def _check_account(account_id: int, user: User, db: AsyncSession):
    from routers.anuncios import _get_account_or_403

    return await _get_account_or_403(account_id, user, db)


@router.post("", status_code=201)
async def start_analysis(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.competitor_analysis_service import schedule_analysis

    product_type = (body.get("product_type") or "").strip()
    product_id = body.get("product_id")
    account_id = body.get("account_id")
    if product_type not in ("pg", "cmig") or not product_id or not account_id:
        raise HTTPException(status_code=422, detail="product_type ('pg'|'cmig'), product_id e account_id são obrigatórios")

    acc = await _check_account(account_id, current_user, db)  # 403/404 se sem acesso
    if (getattr(acc, "platform", None) or "") != "mercadolivre":
        raise HTTPException(status_code=422, detail="A análise usa a API do Mercado Livre; selecione uma conta ML.")

    a = CompetitorAnalysis(
        requester_user_id=current_user.id,
        product_type=product_type,
        product_id=int(product_id),
        account_id=int(account_id),
        desired_margin_pct=body.get("desired_margin_pct"),
        status="running",
        progress_step="Na fila",
        user_prompt=(body.get("user_prompt") or None),
    )
    db.add(a)
    await db.flush()
    await db.commit()
    schedule_analysis(a.id)
    return {"id": a.id, "status": a.status}


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = (
        await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    if current_user.role != "admin" and a.requester_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este estudo")
    return _serialize(a)


@router.get("")
async def list_analyses(
    product_type: str = Query(...),
    product_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Escopo por dono: cada usuário vê só os próprios estudos (admin vê todos).
    conds = [
        CompetitorAnalysis.product_type == product_type,
        CompetitorAnalysis.product_id == product_id,
    ]
    if current_user.role != "admin":
        conds.append(CompetitorAnalysis.requester_user_id == current_user.id)
    rows = (
        await db.execute(
            select(CompetitorAnalysis).where(*conds).order_by(CompetitorAnalysis.created_at.desc())
        )
    ).scalars().all()
    # Sem result_json no histórico (payload menor); só metadados + anotações.
    return [_serialize(a, with_result=False) for a in rows]


@router.patch("/{analysis_id}")
async def update_notes(
    analysis_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = (
        await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    if current_user.role != "admin" and a.requester_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este estudo")
    if "notes" in body:
        a.notes = body.get("notes")
    await db.commit()
    return {"ok": True, "notes": a.notes}


@router.delete("/{analysis_id}")
async def delete_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = (
        await db.execute(select(CompetitorAnalysis).where(CompetitorAnalysis.id == analysis_id))
    ).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    if current_user.role != "admin" and a.requester_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este estudo")
    if a.status == "running":
        raise HTTPException(status_code=409, detail="Estudo em andamento; aguarde concluir para excluir.")
    db.delete(a)  # síncrono
    await db.commit()
    return {"ok": True}

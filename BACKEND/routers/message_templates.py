"""
Mensagens Prontas (templates de resposta) da Central de Atendimento.
Escopo: template pessoal (user_id) OU por CMIG (cmig_id, das CMIGs do usuário).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.claim import MessageTemplate
from models.user import User
from services.atendimento_access import get_accessible_cmig_ids

router = APIRouter(prefix="/api/v1/message-templates", tags=["message-templates"])
logger = logging.getLogger(__name__)


def _serialize(t: MessageTemplate) -> dict:
    return {
        "id": t.id,
        "cmig_id": t.cmig_id,
        "user_id": t.user_id,
        "title": t.title,
        "body": t.body,
        "scope": "cmig" if t.cmig_id else "personal",
    }


@router.get("/")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista templates visíveis: pessoais do usuário + das CMIGs que ele acessa."""
    cmig_ids = await get_accessible_cmig_ids(db, current_user)
    conds = [MessageTemplate.user_id == current_user.id]
    if cmig_ids:
        conds.append(MessageTemplate.cmig_id.in_(cmig_ids))
    rows = (
        await db.execute(select(MessageTemplate).where(or_(*conds)).order_by(MessageTemplate.title))
    ).scalars().all()
    return {"data": [_serialize(t) for t in rows]}


async def _check_scope(cmig_id, current_user, db):
    """Se cmig_id informado, exige que o usuário administre a CMIG."""
    if cmig_id is None:
        return
    cmig_ids = await get_accessible_cmig_ids(db, current_user)
    if cmig_id not in cmig_ids:
        raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG.")


@router.post("/")
async def create_template(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    title = (body.get("title") or "").strip()[:200]
    content = (body.get("body") or "").strip()
    if not title or not content:
        raise HTTPException(status_code=422, detail="Título e conteúdo são obrigatórios.")
    cmig_id = body.get("cmig_id") or None
    await _check_scope(cmig_id, current_user, db)

    tpl = MessageTemplate(cmig_id=cmig_id, user_id=current_user.id, title=title, body=content)
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


async def _get_owned(template_id, current_user, db) -> MessageTemplate:
    tpl = (
        await db.execute(select(MessageTemplate).where(MessageTemplate.id == template_id))
    ).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    # Pode editar: o dono (user_id) ou quem administra a CMIG do template.
    if tpl.user_id != current_user.id:
        cmig_ids = await get_accessible_cmig_ids(db, current_user)
        if not (tpl.cmig_id and tpl.cmig_id in cmig_ids):
            raise HTTPException(status_code=403, detail="Sem permissão sobre este template.")
    return tpl


@router.put("/{template_id}")
async def update_template(
    template_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tpl = await _get_owned(template_id, current_user, db)
    if "title" in body:
        tpl.title = (body.get("title") or "").strip()[:200] or tpl.title
    if "body" in body:
        tpl.body = (body.get("body") or "").strip() or tpl.body
    if "cmig_id" in body:
        new_cmig = body.get("cmig_id") or None
        await _check_scope(new_cmig, current_user, db)
        tpl.cmig_id = new_cmig
    await db.commit()
    await db.refresh(tpl)
    return _serialize(tpl)


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tpl = await _get_owned(template_id, current_user, db)
    db.delete(tpl)  # AsyncSyncSession: delete é síncrono (sem await)
    await db.commit()
    return {"message": "Template excluído."}

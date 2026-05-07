"""
Configuração de IA para atendimento automático.
Config global (singleton) e config por CMIG.
"""
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models.user import User
from models.messages import AIConfig, CMIGAIConfig
from models.cmig import CMIG, CMIGAdministrator
import services.ai_service as ai_svc

router = APIRouter(prefix="/api/v1/ai-config", tags=["ai-config"])
logger = logging.getLogger(__name__)

AVAILABLE_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
}


def _mask_key(key: str | None) -> str:
    if not key:
        return ""
    try:
        decoded = base64.b64decode(key.encode()).decode()
        return decoded[:8] + "••••••••" + decoded[-4:] if len(decoded) > 12 else "••••••••"
    except Exception:
        return "••••••••"


def _encode_key(key: str) -> str:
    return base64.b64encode(key.strip().encode()).decode()


def _decode_key(encoded: str) -> str:
    return base64.b64decode(encoded.encode()).decode()


# ---------------------------------------------------------------------------
# Config Global
# ---------------------------------------------------------------------------

@router.get("/")
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna configuração global de IA (api_key mascarada)."""
    result = await db.execute(select(AIConfig))
    cfg = result.scalar_one_or_none()
    if not cfg:
        return {
            "configured": False,
            "provider": "anthropic",
            "api_key_masked": "",
            "model_name": "claude-sonnet-4-6",
            "global_instructions": "",
            "is_active": False,
            "available_models": AVAILABLE_MODELS,
        }
    return {
        "configured": True,
        "id": cfg.id,
        "provider": cfg.provider,
        "api_key_masked": _mask_key(cfg.api_key),
        "model_name": cfg.model_name,
        "global_instructions": cfg.global_instructions or "",
        "is_active": cfg.is_active,
        "available_models": AVAILABLE_MODELS,
    }


@router.put("/")
async def update_ai_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Salva configuração global de IA. Somente admin."""
    provider = body.get("provider", "anthropic")
    model_name = body.get("model_name", "claude-sonnet-4-6")
    global_instructions = body.get("global_instructions", "")
    is_active = body.get("is_active", False)
    raw_key = body.get("api_key", "")  # vazio = não alterar

    result = await db.execute(select(AIConfig))
    cfg = result.scalar_one_or_none()

    if not cfg:
        cfg = AIConfig(
            provider=provider,
            model_name=model_name,
            global_instructions=global_instructions,
            is_active=is_active,
        )
        if raw_key:
            cfg.api_key = _encode_key(raw_key)
        db.add(cfg)
    else:
        cfg.provider = provider
        cfg.model_name = model_name
        cfg.global_instructions = global_instructions
        cfg.is_active = is_active
        if raw_key:
            cfg.api_key = _encode_key(raw_key)

    await db.commit()
    await db.refresh(cfg)
    return {"message": "Configuração de IA salva com sucesso.", "is_active": cfg.is_active}


@router.post("/test")
async def test_ai_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Testa a configuração de IA atual enviando uma mensagem simples."""
    result = await db.execute(select(AIConfig))
    cfg = result.scalar_one_or_none()
    if not cfg or not cfg.api_key:
        raise HTTPException(status_code=400, detail="Nenhuma configuração de IA encontrada.")

    api_key = _decode_key(cfg.api_key)
    await ai_svc.test_connection(provider=cfg.provider, api_key=api_key, model=cfg.model_name)
    return {"message": "Conexão com a IA testada com sucesso.", "provider": cfg.provider, "model": cfg.model_name}


# ---------------------------------------------------------------------------
# Config por CMIG
# ---------------------------------------------------------------------------

async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession):
    result = await db.execute(select(CMIG).where(CMIG.id == cmig_id))
    cmig = result.scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada.")
    if user.role == "admin":
        return cmig
    result2 = await db.execute(
        select(CMIGAdministrator).where(
            CMIGAdministrator.cmig_id == cmig_id,
            CMIGAdministrator.user_id == user.id,
        )
    )
    if not result2.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG.")
    return cmig


@router.get("/cmig/{cmig_id}")
async def get_cmig_ai_config(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_cmig_access(cmig_id, current_user, db)

    result = await db.execute(select(CMIGAIConfig).where(CMIGAIConfig.cmig_id == cmig_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        return {"cmig_id": cmig_id, "custom_instructions": "", "auto_respond": False}
    return {
        "id": cfg.id,
        "cmig_id": cfg.cmig_id,
        "custom_instructions": cfg.custom_instructions or "",
        "auto_respond": cfg.auto_respond,
    }


@router.put("/cmig/{cmig_id}")
async def update_cmig_ai_config(
    cmig_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_cmig_access(cmig_id, current_user, db)

    result = await db.execute(select(CMIGAIConfig).where(CMIGAIConfig.cmig_id == cmig_id))
    cfg = result.scalar_one_or_none()

    custom_instructions = body.get("custom_instructions", "")
    auto_respond = bool(body.get("auto_respond", False))

    if not cfg:
        cfg = CMIGAIConfig(cmig_id=cmig_id, custom_instructions=custom_instructions, auto_respond=auto_respond)
        db.add(cfg)
    else:
        cfg.custom_instructions = custom_instructions
        cfg.auto_respond = auto_respond

    await db.commit()
    return {"message": "Configuração de IA da CMIG salva.", "auto_respond": auto_respond}

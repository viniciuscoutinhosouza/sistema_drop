"""Configuração por marketplace (Super Admin).

Singleton por marketplace em `marketplace_settings.settings_json` (JSON flexível).
Leitura: qualquer usuário autenticado. Escrita: apenas admin (Super Admin).
Os defaults de formato de mídia (DEFAULT_MEDIA_SPECS) são mesclados na leitura,
então a tela sempre mostra um padrão sugerido mesmo sem registro salvo.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models.integration import MarketplaceSetting
from models.user import User

router = APIRouter(prefix="/api/v1/marketplace-settings", tags=["marketplace-settings"])
logger = logging.getLogger(__name__)

# Marketplaces suportados e seus rótulos.
MARKETPLACES = {
    "mercadolivre": "Mercado Livre",
    "shopee": "Shopee",
    "amazon": "Amazon",
    "tiktok": "TikTok Shop",
    "magalu": "Magalu",
}

# Formatos recomendados por marketplace (pesquisados). Sugestão editável — o
# usuário pode sobrescrever via PUT; o que ele salvar tem precedência.
DEFAULT_MEDIA_SPECS = {
    "mercadolivre": {
        "image": {
            "aspect": "1:1", "min_px": 500, "rec_px": 1200, "max_px": 1920,
            "max_mb": 10, "formats": ["JPG", "PNG"],
            "background": "Fundo branco/neutro; produto ocupando ~95%.",
        },
        "clip": {
            "enabled": True, "delivery": "youtube", "aspect": "16:9",
            "min_sec": 0, "max_sec": 0, "max_mb": 0, "formats": ["YouTube"],
            "note": "ML usa link do YouTube (video_id), não upload direto.",
            "ai_prompt": "Crie um clip curto e dinâmico mostrando o produto em uso, "
                         "com movimentos suaves de câmera, fundo limpo e boa iluminação.",
        },
    },
    "shopee": {
        "image": {
            "aspect": "1:1", "min_px": 350, "rec_px": 1000, "max_px": 0,
            "max_mb": 0, "formats": ["JPG", "PNG"],
            "background": "Até 9 imagens; alta qualidade, sem marca d'água.",
        },
        "clip": {
            "enabled": True, "delivery": "upload", "aspect": "1:1 a 16:9",
            "min_sec": 10, "max_sec": 60, "max_mb": 30, "formats": ["MP4"],
            "note": "",
        },
    },
    "amazon": {
        "image": {
            "aspect": "1:1", "min_px": 1000, "rec_px": 1600, "max_px": 10000,
            "max_mb": 0, "formats": ["JPEG", "PNG"],
            "background": "Fundo branco puro; produto ≥85%. Lado maior ≥1600px p/ zoom.",
        },
        "clip": {
            "enabled": True, "delivery": "upload", "aspect": "1:1 ou 16:9",
            "min_sec": 0, "max_sec": 0, "max_mb": 0, "formats": ["MP4", "MOV"],
            "note": "",
        },
    },
    "tiktok": {
        "image": {
            "aspect": "1:1", "min_px": 600, "rec_px": 800, "max_px": 0,
            "max_mb": 5, "formats": ["JPG", "PNG"],
            "background": "Principal 1:1, fundo claro, produto ≥80%.",
        },
        "clip": {
            "enabled": True, "delivery": "upload", "aspect": "9:16",
            "min_sec": 15, "max_sec": 60, "max_mb": 0, "formats": ["MP4", "MOV"],
            "note": "Vertical 1080×1920.",
        },
    },
    "magalu": {
        "image": {
            "aspect": "1:1", "min_px": 1000, "rec_px": 1000, "max_px": 0,
            "max_mb": 0, "formats": ["JPG", "PNG"],
            "background": "Fundo branco (verificar specs atuais do Magalu).",
        },
        "clip": {
            "enabled": False, "delivery": "upload", "aspect": "",
            "min_sec": 0, "max_sec": 0, "max_mb": 0, "formats": [],
            "note": "",
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Mescla `override` sobre `base` recursivamente (não muta os originais)."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _parse(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


async def _load_map(db: AsyncSession) -> dict[str, dict]:
    """marketplace -> settings_json (parseado) das linhas existentes."""
    res = await db.execute(select(MarketplaceSetting))
    return {row.marketplace: _parse(row.settings_json) for row in res.scalars().all()}


def _merged(marketplace: str, stored: dict) -> dict:
    defaults = {"media": DEFAULT_MEDIA_SPECS.get(marketplace, {})}
    return _deep_merge(defaults, stored)


@router.get("")
async def list_marketplace_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Todas as marketplaces com defaults mesclados."""
    stored_map = await _load_map(db)
    out = []
    for mp, label in MARKETPLACES.items():
        out.append({
            "marketplace": mp,
            "label": label,
            "settings": _merged(mp, stored_map.get(mp, {})),
        })
    return {"marketplaces": out}


@router.get("/{marketplace}")
async def get_marketplace_settings(
    marketplace: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Marketplace inválido")
    stored_map = await _load_map(db)
    return {
        "marketplace": marketplace,
        "label": MARKETPLACES[marketplace],
        "settings": _merged(marketplace, stored_map.get(marketplace, {})),
    }


@router.put("/{marketplace}")
async def update_marketplace_settings(
    marketplace: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Salva (upsert) o settings_json do marketplace. Apenas Super Admin.

    O `body` é gravado como está (já deve conter a árvore completa, ex.: {media: {...}}).
    """
    if marketplace not in MARKETPLACES:
        raise HTTPException(status_code=404, detail="Marketplace inválido")

    res = await db.execute(
        select(MarketplaceSetting).where(MarketplaceSetting.marketplace == marketplace)
    )
    row = res.scalar_one_or_none()
    payload = json.dumps(body or {}, ensure_ascii=False)

    if row is None:
        row = MarketplaceSetting(marketplace=marketplace, settings_json=payload)
        db.add(row)
    else:
        row.settings_json = payload

    await db.commit()
    return {
        "message": "Configuração salva.",
        "marketplace": marketplace,
        "settings": _merged(marketplace, _parse(payload)),
    }

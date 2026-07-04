"""Configuração por marketplace (Super Admin).

Singleton por marketplace em `marketplace_settings.settings_json` (JSON flexível).
Leitura: qualquer usuário autenticado. Escrita: apenas admin (Super Admin).
Os defaults de formato de mídia (DEFAULT_MEDIA_SPECS) são mesclados na leitura,
então a tela sempre mostra um padrão sugerido mesmo sem registro salvo.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from dependencies import get_current_user, require_role
from models.fiscal import PlatformCertConfig
from models.integration import MarketplaceSetting
from models.user import User
from services.fiscal import cert_crypto
from services.fiscal.pfx_utils import validate_pfx

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


# ── Certificado A1 CENTRAL do assinante (marketplace) — usado na DC-e ──────────
# Diferente do cert por-CMIG (NF-e): este é único por `profile_type` (ex.: 'marketplace_dce')
# e assina a DC-e das contas de vendedor CPF por conta e ordem, com o A1 da MIG.


@router.get("/platform-certificate/{profile_type}")
async def get_platform_certificate(
    profile_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Status do certificado central do assinante (ex.: 'marketplace_dce'). Super Admin."""
    cfg = (
        await db.execute(
            select(PlatformCertConfig).where(PlatformCertConfig.profile_type == profile_type)
        )
    ).scalar_one_or_none()
    if not cfg:
        return {"configured": False, "profile_type": profile_type}
    return {
        "configured": bool(cfg.cert_path and cfg.cert_pass_encrypted),
        "profile_type": cfg.profile_type,
        "cnpj": cfg.cnpj,
        "company_name": cfg.company_name,
        "site": cfg.site,
        "certificate_subject": cfg.certificate_subject,
        "certificate_expires_at": cfg.certificate_expires_at.isoformat()
        if cfg.certificate_expires_at
        else None,
    }


@router.post("/platform-certificate/{profile_type}")
async def upload_platform_certificate(
    profile_type: str,
    cnpj: str = Form(...),
    company_name: str = Form(...),
    password: str = Form(...),
    site: str = Form(None),
    pfx_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Upload do A1 CENTRAL do assinante marketplace (ex.: A1 da MIG p/ DC-e). Super Admin.

    O .pfx é gravado em diretório restrito no servidor; a senha fica CIFRADA (Fernet) no banco.
    Armazenado em `platform_cert_configs`, único por `profile_type`."""
    pfx_bytes = await pfx_file.read()
    if not pfx_bytes:
        raise HTTPException(status_code=422, detail="Arquivo .pfx vazio")
    if len(pfx_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Arquivo .pfx muito grande (máx 5MB)")

    expires_at, subject = validate_pfx(pfx_bytes, password)
    if not expires_at:
        raise HTTPException(status_code=422, detail="Certificado inválido ou senha incorreta")

    try:
        pass_token = cert_crypto.encrypt(password)
    except cert_crypto.CertCryptoError as e:
        raise HTTPException(status_code=500, detail=str(e))

    certs_dir = Path(get_settings().NFE_CERTS_DIR)
    certs_dir.mkdir(parents=True, exist_ok=True)
    safe_profile = "".join(c for c in profile_type if c.isalnum() or c in ("_", "-"))
    cert_path = certs_dir / f"platform_{safe_profile}.pfx"
    cert_path.write_bytes(pfx_bytes)
    try:
        os.chmod(cert_path, 0o600)
    except OSError:
        pass

    cfg = (
        await db.execute(
            select(PlatformCertConfig).where(PlatformCertConfig.profile_type == profile_type)
        )
    ).scalar_one_or_none()
    if not cfg:
        cfg = PlatformCertConfig(profile_type=profile_type, cnpj=cnpj, company_name=company_name)
        db.add(cfg)
    cfg.cnpj = cnpj
    cfg.company_name = company_name
    cfg.site = site
    cfg.cert_path = str(cert_path)
    cfg.cert_pass_encrypted = pass_token
    cfg.certificate_uploaded_at = datetime.utcnow()
    cfg.certificate_expires_at = expires_at
    cfg.certificate_subject = subject
    await db.commit()

    return {
        "detail": f"Certificado central '{profile_type}' armazenado (assinante marketplace)",
        "cnpj": cnpj,
        "certificate_subject": subject,
        "certificate_expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.post("/platform-certificate/{profile_type}/status-check")
async def dce_status_check(
    profile_type: str,
    tp_amb: int = 2,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Smoke da conexão SVRS DC-e: resolve o A1 central e consulta o Status do Serviço.

    Valida certificado + mTLS + envelope antes de qualquer emissão. tp_amb=2 (homologação)
    por default. Retorna o cStat/xMotivo bruto do serviço."""
    import contextlib as _cl
    import os as _os

    from services.fiscal.dce import dce_client
    from services.fiscal.dce.exceptions import DceError
    from services.fiscal.dce.signer_cert import resolve_platform_signer_cert
    from services.fiscal.sefaz.sefaz_client import extract_cert_pem

    try:
        pfx_path, senha = await resolve_platform_signer_cert(db, profile_type)
    except DceError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cert_pem, key_pem = extract_cert_pem(pfx_path, senha, runtime_dir=get_settings().NFE_CERTS_DIR)
    try:
        verify = tp_amb == 1
        resp = dce_client.status_servico(tp_amb, cert_pem, key_pem, verify_ssl=verify)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao conectar na SVRS DC-e: {e}")
    finally:
        for f in (cert_pem, key_pem):
            with _cl.suppress(OSError):
                _os.remove(f)

    ret = dce_client.extrair_retorno(resp.body)
    return {
        "http_status": resp.status_code,
        "cstat": ret["cstat"],
        "xmotivo": ret["xmotivo"],
        "tp_amb": tp_amb,
        "raw_head": resp.body[:600],
    }

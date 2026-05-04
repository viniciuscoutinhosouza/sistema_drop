from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime

from database import get_db
from dependencies import get_current_user
from models.user import User
from models.cmig import CMIG, CMIGAdministrator
from models.fiscal import CMIGFiscalConfig
from services.fiscal import focus_service

router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────

async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession, require_owner: bool = False) -> CMIG:
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")

    if user.role == "admin":
        return cmig
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        if require_owner:
            raise HTTPException(status_code=403, detail="Apenas o AC proprietário pode realizar esta ação")
        return cmig
    if user.role == "ac":
        admin = (
            await db.execute(
                select(CMIGAdministrator).where(
                    and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig_id)
                )
            )
        ).scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        if require_owner and not admin.is_owner:
            raise HTTPException(status_code=403, detail="Apenas o AC proprietário pode realizar esta ação")
        return cmig
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


def _serialize(cfg: CMIGFiscalConfig | None) -> dict:
    if not cfg:
        return {}
    return {
        "id": cfg.id,
        "cmig_id": cfg.cmig_id,
        "crt": cfg.crt,
        "environment": cfg.environment,
        "focus_registered": bool(cfg.focus_company_token),
        "focus_company_id": cfg.focus_company_id,
        "focus_registered_at": cfg.focus_registered_at.isoformat() if cfg.focus_registered_at else None,
        "certificate_loaded": bool(cfg.certificate_uploaded_at),
        "certificate_uploaded_at": cfg.certificate_uploaded_at.isoformat() if cfg.certificate_uploaded_at else None,
        "certificate_expires_at": cfg.certificate_expires_at.isoformat() if cfg.certificate_expires_at else None,
        "certificate_subject": cfg.certificate_subject,
        "ie": cfg.ie,
        "im": cfg.im,
        "cnae": cfg.cnae,
        "default_natureza_operacao": cfg.default_natureza_operacao,
        "nfe_serie": cfg.nfe_serie,
        "nfe_next_number": cfg.nfe_next_number,
        "csc_id": cfg.csc_id,
        "csc_token_set": bool(cfg.csc_token),
        "fiscal_email_copy": cfg.fiscal_email_copy,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_fiscal_config(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna config fiscal da CMIG. Cria automaticamente se não existir."""
    await _check_cmig_access(cmig_id, current_user, db)
    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        cfg = CMIGFiscalConfig(cmig_id=cmig_id)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return _serialize(cfg)


@router.patch("")
async def update_fiscal_config(
    cmig_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_cmig_access(cmig_id, current_user, db, require_owner=False)
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC ou admin podem editar configuração fiscal")

    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        cfg = CMIGFiscalConfig(cmig_id=cmig_id)
        db.add(cfg)
        await db.flush()

    editable = {
        "crt", "environment", "ie", "im", "cnae", "default_natureza_operacao",
        "nfe_serie", "nfe_next_number", "fiscal_email_copy",
    }
    if body.get("crt") is not None and body["crt"] not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="crt deve ser 1, 2, 3 ou 4")
    if body.get("environment") and body["environment"] not in ("homolog", "production"):
        raise HTTPException(status_code=422, detail="environment deve ser 'homolog' ou 'production'")

    for k, v in body.items():
        if k in editable:
            setattr(cfg, k, v)

    await db.commit()
    await db.refresh(cfg)
    return _serialize(cfg)


# ── Registro Focus NFe ────────────────────────────────────────────────────────

@router.post("/register-focus")
async def register_focus(
    cmig_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra a empresa (CNPJ) no Focus NFe. Requer master_token (do dev).
    Salva o token específico da empresa em cfg.focus_company_token."""
    cmig = await _check_cmig_access(cmig_id, current_user, db)
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC ou admin podem registrar no Focus")

    master_token = (body.get("master_token") or "").strip()
    if not master_token:
        raise HTTPException(status_code=422, detail="master_token é obrigatório")

    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        cfg = CMIGFiscalConfig(cmig_id=cmig_id)
        db.add(cfg)
        await db.flush()

    if not cfg.crt:
        raise HTTPException(status_code=400, detail="Configure o CRT antes de registrar no Focus")
    if not cmig.cnpj:
        raise HTTPException(status_code=400, detail="CMIG sem CNPJ cadastrado")

    try:
        result = await focus_service.register_company(cfg, cmig, master_token)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    # Focus retorna `token_homologacao` ou `token_producao` da empresa registrada
    company_token = (
        result.get("token_homologacao") if cfg.environment == "homolog"
        else result.get("token_producao")
    )
    if not company_token:
        # Algumas respostas do Focus retornam ambos; tentar o oposto também
        company_token = result.get("token_producao") or result.get("token_homologacao")

    cfg.focus_company_token = company_token
    cfg.focus_company_id = result.get("id") or result.get("uuid") or _digits_only(cmig.cnpj)
    cfg.focus_registered_at = datetime.utcnow()

    await db.commit()
    await db.refresh(cfg)
    return {
        "detail": "Empresa registrada no Focus NFe",
        "focus_company_id": cfg.focus_company_id,
        "config": _serialize(cfg),
    }


@router.post("/certificate")
async def upload_certificate(
    cmig_id: int,
    master_token: str = Form(...),
    password: str = Form(...),
    pfx_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload do certificado A1 (.pfx) — repassa para o Focus NFe.
    O .pfx NÃO é salvo localmente: vai direto para o cofre do Focus."""
    cmig = await _check_cmig_access(cmig_id, current_user, db)
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC ou admin podem subir certificado")

    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=400, detail="Configure a CMIG no Focus antes de enviar o certificado")

    pfx_bytes = await pfx_file.read()
    if not pfx_bytes:
        raise HTTPException(status_code=422, detail="Arquivo .pfx vazio")
    if len(pfx_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Arquivo .pfx muito grande (máx 5MB)")

    # Validar localmente que o .pfx + senha são válidos antes de enviar
    expires_at, subject = _validate_pfx(pfx_bytes, password)
    if not expires_at:
        raise HTTPException(status_code=422, detail="Certificado inválido ou senha incorreta")

    try:
        await focus_service.upload_certificate(cfg, cmig, master_token, pfx_bytes, password)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    cfg.certificate_uploaded_at = datetime.utcnow()
    cfg.certificate_expires_at = expires_at
    cfg.certificate_subject = subject
    await db.commit()
    await db.refresh(cfg)

    return {
        "detail": "Certificado enviado para o Focus NFe",
        "certificate_subject": subject,
        "certificate_expires_at": expires_at.isoformat() if expires_at else None,
    }


def _digits_only(s: str | None) -> str:
    import re
    return re.sub(r"\D", "", s or "")


def _validate_pfx(pfx_bytes: bytes, password: str):
    """Valida o .pfx; retorna (expires_at, subject) ou (None, None) se inválido."""
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12
        _, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, password.encode("utf-8"))
        if cert is None:
            return None, None
        subject = cert.subject.rfc4514_string()
        # cryptography >= 42 expõe not_valid_after_utc; versões mais antigas só têm not_valid_after
        expires = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
        return expires.replace(tzinfo=None) if expires.tzinfo else expires, subject
    except Exception:
        return None, None

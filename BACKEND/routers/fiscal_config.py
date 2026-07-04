import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from dependencies import get_current_user
from models.cmig import CMIG, CMIGAdministrator
from models.fiscal import CMIGFiscalConfig
from models.user import User
from services.fiscal import cert_crypto

router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────


async def _check_cmig_access(
    cmig_id: int, user: User, db: AsyncSession, require_owner: bool = False
) -> CMIG:
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")

    if user.role == "admin":
        return cmig
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        if require_owner:
            raise HTTPException(
                status_code=403, detail="Apenas o AC proprietário pode realizar esta ação"
            )
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
            raise HTTPException(
                status_code=403, detail="Apenas o AC proprietário pode realizar esta ação"
            )
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
        # Certificado A1 (emissão própria SEFAZ): armazenado local, senha cifrada no banco
        "certificate_loaded": bool(cfg.cert_path and cfg.cert_pass_encrypted),
        "certificate_uploaded_at": cfg.certificate_uploaded_at.isoformat()
        if cfg.certificate_uploaded_at
        else None,
        "certificate_expires_at": cfg.certificate_expires_at.isoformat()
        if cfg.certificate_expires_at
        else None,
        "certificate_subject": cfg.certificate_subject,
        "production_released": bool(cfg.production_released),
        # DC-e (conta CPF): autorização "por conta e ordem" p/ a MIG emitir pelo vendedor
        "dce_authorized": bool(cfg.dce_authorized),
        "ie": cfg.ie,
        "im": cfg.im,
        "cnae": cfg.cnae,
        "default_natureza_operacao": cfg.default_natureza_operacao,
        "nfe_serie": cfg.nfe_serie,
        "nfe_next_number": cfg.nfe_next_number,
        # Série específica configurável da emissão MANUAL via SEFAZ (separada do marketplace)
        "manual_nfe_serie": cfg.manual_nfe_serie,
        "manual_nfe_next_number": cfg.manual_nfe_next_number,
        "manual_nfe_next_number_homolog": cfg.manual_nfe_next_number_homolog,
        "aliquota_fecp": float(cfg.aliquota_fecp) if cfg.aliquota_fecp is not None else 0,
        "csc_id": cfg.csc_id,
        "csc_token_set": bool(cfg.csc_token),
        "fiscal_email_copy": cfg.fiscal_email_copy,
        "tax_estimate_pct": float(cfg.tax_estimate_pct) if cfg.tax_estimate_pct is not None else 0,
        "tax_regime_mode": cfg.tax_regime_mode or "legacy",
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
        raise HTTPException(
            status_code=403, detail="Apenas AC ou admin podem editar configuração fiscal"
        )
    # Autorização "por conta e ordem" (DC-e) expõe o CNPJ da MIG como assinante — só admin liga.
    if "dce_authorized" in body and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Apenas admin pode autorizar a emissão de DC-e por conta e ordem (dce_authorized).",
        )

    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        cfg = CMIGFiscalConfig(cmig_id=cmig_id)
        db.add(cfg)
        await db.flush()

    editable = {
        "crt",
        "environment",
        "ie",
        "im",
        "cnae",
        "default_natureza_operacao",
        "nfe_serie",
        "nfe_next_number",
        "manual_nfe_serie",
        "manual_nfe_next_number",
        "manual_nfe_next_number_homolog",
        "aliquota_fecp",
        "production_released",
        "dce_authorized",
        "fiscal_email_copy",
        "tax_estimate_pct",
        "tax_regime_mode",
    }
    if body.get("crt") is not None and body["crt"] not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="crt deve ser 1, 2, 3 ou 4")
    if body.get("environment") and body["environment"] not in ("homolog", "production"):
        raise HTTPException(
            status_code=422, detail="environment deve ser 'homolog' ou 'production'"
        )
    if "production_released" in body:
        body["production_released"] = 1 if body.get("production_released") else 0
    if "dce_authorized" in body:
        body["dce_authorized"] = 1 if body.get("dce_authorized") else 0
    # A série manual SEFAZ não pode colidir com a série do Faturador ML (nfe_serie) do mesmo CNPJ.
    new_manual_serie = body.get("manual_nfe_serie", getattr(cfg, "manual_nfe_serie", None))
    new_ml_serie = body.get("nfe_serie", getattr(cfg, "nfe_serie", None))
    if new_manual_serie is not None and new_ml_serie is not None and new_manual_serie == new_ml_serie:
        raise HTTPException(
            status_code=422,
            detail="A série da NF-e manual (SEFAZ) deve ser diferente da série do marketplace (nfe_serie).",
        )
    if body.get("tax_regime_mode") and body["tax_regime_mode"] not in (
        "legacy", "transition", "reform"
    ):
        raise HTTPException(
            status_code=422,
            detail="tax_regime_mode deve ser 'legacy', 'transition' ou 'reform'",
        )

    for k, v in body.items():
        if k in editable:
            setattr(cfg, k, v)

    await db.commit()
    await db.refresh(cfg)
    return _serialize(cfg)


# ── Certificado A1 (emissão própria SEFAZ) ─────────────────────────────────────


@router.post("/certificate")
async def upload_certificate(
    cmig_id: int,
    password: str = Form(...),
    pfx_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload do certificado A1 (.pfx) da CMIG para emissão própria à SEFAZ.

    O .pfx é gravado em diretório RESTRITO no servidor (fora de static/) e a senha
    é arquivada CIFRADA no banco (Fernet master key). Nada vai para terceiros."""
    cmig = await _check_cmig_access(cmig_id, current_user, db)
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC ou admin podem subir certificado")

    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        cfg = CMIGFiscalConfig(cmig_id=cmig_id)
        db.add(cfg)
        await db.flush()

    pfx_bytes = await pfx_file.read()
    if not pfx_bytes:
        raise HTTPException(status_code=422, detail="Arquivo .pfx vazio")
    if len(pfx_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Arquivo .pfx muito grande (máx 5MB)")

    # Validar o .pfx + senha antes de qualquer persistência
    expires_at, subject = _validate_pfx(pfx_bytes, password)
    if not expires_at:
        raise HTTPException(status_code=422, detail="Certificado inválido ou senha incorreta")

    # Cifrar a senha ANTES de gravar nada (falha cedo se a master key não estiver configurada)
    try:
        pass_token = cert_crypto.encrypt(password)
    except cert_crypto.CertCryptoError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Gravar o .pfx em diretório restrito (fora de static/, que é servido por HTTP)
    certs_dir = Path(get_settings().NFE_CERTS_DIR)
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_path = certs_dir / f"cmig_{cmig_id}.pfx"
    cert_path.write_bytes(pfx_bytes)
    try:
        os.chmod(cert_path, 0o600)  # best-effort (no-op efetivo no Windows)
    except OSError:
        pass

    cfg.cert_path = str(cert_path)
    cfg.cert_pass_encrypted = pass_token
    cfg.certificate_uploaded_at = datetime.utcnow()
    cfg.certificate_expires_at = expires_at
    cfg.certificate_subject = subject
    await db.commit()
    await db.refresh(cfg)

    return {
        "detail": "Certificado A1 armazenado para emissão própria à SEFAZ",
        "certificate_subject": subject,
        "certificate_expires_at": expires_at.isoformat() if expires_at else None,
    }


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

"""Resolução do certificado A1 CENTRAL do assinante (marketplace) para a DC-e.

Diferente do cert-por-CMIG (`CMIGFiscalConfig.cert_path`, usado na NF-e), a DC-e é assinada
pelo A1 do CNPJ da MIG no perfil "Marketplace" — cert único por `profile_type`, guardado em
`PlatformCertConfig` (migration 120). Cifra da senha reaproveita `cert_crypto` (Fernet).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from models.fiscal import PlatformCertConfig
from services.fiscal import cert_crypto
from services.fiscal.dce.exceptions import DceError

PROFILE_MARKETPLACE_DCE = "marketplace_dce"


async def get_platform_cert_config(db, profile_type: str = PROFILE_MARKETPLACE_DCE):
    return (
        await db.execute(
            select(PlatformCertConfig).where(PlatformCertConfig.profile_type == profile_type)
        )
    ).scalar_one_or_none()


async def resolve_platform_signer_cert(
    db, profile_type: str = PROFILE_MARKETPLACE_DCE
) -> tuple[str, str]:
    """Retorna (pfx_path, senha_em_claro) do assinante central. Levanta DceError se ausente."""
    cfg = await get_platform_cert_config(db, profile_type)
    if not cfg or not cfg.cert_path or not cfg.cert_pass_encrypted:
        raise DceError(
            "Certificado central do assinante (marketplace) não configurado. Cadastre o A1 da "
            "MIG em Configuração Fiscal → Certificado do Marketplace."
        )
    if not Path(cfg.cert_path).exists():
        raise DceError(f"Arquivo do certificado do marketplace não encontrado: {cfg.cert_path}")
    try:
        senha = cert_crypto.decrypt(cfg.cert_pass_encrypted)
    except cert_crypto.CertCryptoError as e:
        raise DceError(str(e)) from e
    return cfg.cert_path, senha

"""Validador de NCM (Nomenclatura Comum do MERCOSUL).

Fase 1 — dois níveis de validação:
1. Formato: 8 dígitos numéricos (capítulo 2 + posição 2 + subposição 2 + item 1 + subitem 1)
2. Existência na tabela `ncm_codes` (se a tabela estiver populada).

Quando a tabela estiver vazia (sem TEC importada), apenas a validação de formato
é aplicada para não bloquear operações legítimas.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal import NCMCode

_NCM_RE = re.compile(r"^\d{8}$")


def normalize_ncm(value: str | None) -> str | None:
    """Remove pontos e traços, retorna string com 8 dígitos ou None se vazio."""
    if not value:
        return None
    cleaned = re.sub(r"[\.\-\s]", "", value.strip())
    return cleaned if cleaned else None


def is_valid_format(ncm: str | None) -> bool:
    """Verifica se o NCM tem 8 dígitos numéricos."""
    if not ncm:
        return False
    return bool(_NCM_RE.match(normalize_ncm(ncm) or ""))


async def validate_ncm(
    db: AsyncSession,
    ncm: str | None,
    *,
    strict: bool = False,
) -> tuple[bool, str | None]:
    """Valida NCM em dois níveis.

    Retorna (valid: bool, error_message: str | None).

    strict=True: recusa NCMs que não estejam na tabela (mesmo se tabela estiver vazia).
    strict=False (padrão): aceita NCMs com formato correto mesmo fora da tabela.
    """
    normalized = normalize_ncm(ncm)

    if not normalized:
        return False, "NCM é obrigatório"

    if not is_valid_format(normalized):
        return False, f"NCM '{ncm}' inválido — deve ter exatamente 8 dígitos numéricos"

    # Verificar na tabela
    row = (
        await db.execute(
            select(NCMCode).where(NCMCode.code == normalized, NCMCode.is_active == 1)
        )
    ).scalar_one_or_none()

    if row:
        return True, None

    # Tabela vazia → sem validação de existência (TEC ainda não importada)
    count = (await db.execute(select(NCMCode.id).limit(1))).scalar_one_or_none()
    if count is None:
        if strict:
            return False, f"NCM '{normalized}' não encontrado na tabela TEC"
        return True, None

    # Tabela tem dados mas NCM não encontrado
    if strict:
        return False, f"NCM '{normalized}' não consta na Tabela ECCM Comum (TEC)"

    # Modo não-strict: aceita com aviso (retorna True mas mensagem de warning)
    return True, f"ATENÇÃO: NCM {normalized} não consta na TEC local — verificar validade"


async def get_ncm_description(db: AsyncSession, ncm: str | None) -> str | None:
    """Retorna descrição do NCM se existir na tabela, None caso contrário."""
    normalized = normalize_ncm(ncm)
    if not normalized:
        return None
    row = (
        await db.execute(select(NCMCode).where(NCMCode.code == normalized))
    ).scalar_one_or_none()
    return row.description if row else None

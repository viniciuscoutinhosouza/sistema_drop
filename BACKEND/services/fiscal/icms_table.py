"""Serviço de consulta de alíquotas ICMS por par UF origem/destino.

Regras padrão CONFAZ (2024):
- Intra-estadual: alíquota própria de cada UF (tabela icms_rates, uf_origin = uf_dest)
- Interestadual SS→SS: 12%   (Sul/Sudeste entre si)
- Interestadual SS→outros: 7%
- Interestadual outros→qualquer: 12%

Onde SS = {ES, MG, PR, RJ, RS, SC, SP}.

Linhas específicas na tabela `icms_rates` sobrescrevem o padrão acima.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal import ICMSRate

# Estados Sul/Sudeste (geram alíquota reduzida de 7% quando vendem para fora do grupo)
_SS_STATES: frozenset[str] = frozenset({"ES", "MG", "PR", "RJ", "RS", "SC", "SP"})

# Alíquota padrão intra quando não encontrar linha na tabela
_DEFAULT_INTRA = Decimal("18")
# Alíquotas padrão interestaduais
_INTER_SS_TO_SS = Decimal("12")
_INTER_SS_TO_OTHER = Decimal("7")
_INTER_OTHER_TO_ANY = Decimal("12")


async def get_icms_rate(
    db: AsyncSession,
    uf_origin: str | None,
    uf_dest: str | None,
) -> Decimal:
    """Retorna alíquota ICMS aplicável para o par UF origem/destino.

    1. Busca linha exata na tabela (uf_origin, uf_dest) com is_active=1 e valid_to NULL.
    2. Se não encontrar, aplica regras padrão CONFAZ.
    """
    uf_o = (uf_origin or "").strip().upper()
    uf_d = (uf_dest or "").strip().upper()

    if not uf_o or not uf_d:
        return _INTER_OTHER_TO_ANY

    # Busca linha específica na tabela
    row = (
        await db.execute(
            select(ICMSRate).where(
                and_(
                    ICMSRate.uf_origin == uf_o,
                    ICMSRate.uf_dest == uf_d,
                    ICMSRate.is_active == 1,
                    ICMSRate.valid_to.is_(None),
                )
            )
        )
    ).scalar_one_or_none()

    if row:
        return Decimal(str(row.aliquota))

    # Regra CONFAZ padrão
    if uf_o == uf_d:
        return _DEFAULT_INTRA  # fallback se não houver linha intra

    if uf_o in _SS_STATES:
        return _INTER_SS_TO_SS if uf_d in _SS_STATES else _INTER_SS_TO_OTHER

    return _INTER_OTHER_TO_ANY


def compute_difal(
    base_value: Decimal,
    aliquota_orig: Decimal,
    aliquota_dest: Decimal,
    fcp_aliquota: Decimal = Decimal("0"),
) -> dict:
    """Calcula DIFAL e FCP para venda interestadual a consumidor final.

    DIFAL = base × (aliquota_dest - aliquota_orig)
    FCP   = base × fcp_aliquota

    Desde 2019 (EC 87), 100% do diferencial vai ao estado de destino.
    """
    difal_value = (base_value * (aliquota_dest - aliquota_orig) / Decimal("100")).quantize(
        Decimal("0.01")
    )
    fcp_value = (base_value * fcp_aliquota / Decimal("100")).quantize(Decimal("0.01"))

    return {
        "difal_base": base_value,
        "difal_aliquota_orig": aliquota_orig,
        "difal_aliquota_dest": aliquota_dest,
        "difal_value": max(difal_value, Decimal("0")),  # nunca negativo
        "difal_fcp_aliquota": fcp_aliquota,
        "difal_fcp_value": fcp_value,
    }

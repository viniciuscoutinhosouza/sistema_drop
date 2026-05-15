"""Calculador básico de impostos por item de NFe.

MVP: regras simples baseadas em CRT (regime tributário) e CFOP.
- CRT 1/2 (Simples Nacional) → CSOSN 102 (sem permissão de crédito), PIS/COFINS isentos
- CRT 3 (Regime Normal) → CST 00 (tributada integralmente), PIS/COFINS conforme alíquota informada

Para casos complexos (ICMS-ST por UF/MVA, ICMS interestadual com partilha,
diferimento etc.) será necessário evoluir para tabela `tax_rules`.
"""

from __future__ import annotations

from decimal import Decimal


def calculate_item_taxes(
    *,
    crt: int,
    cfop: str | None,
    base_value: Decimal | float | None,
    icms_aliquota: Decimal | float | None = None,
    pis_aliquota: Decimal | float | None = None,
    cofins_aliquota: Decimal | float | None = None,
    origin: int = 0,
) -> dict:
    """Retorna dict com CST/CSOSN e valores calculados.

    Não considera ICMS-ST nem partilha interestadual no MVP.
    """
    base = Decimal(str(base_value or 0))
    is_simples = crt in (1, 2, 4)
    is_outside_state = bool(cfop and cfop.startswith("6"))  # 6xxx = interestadual

    out: dict = {
        "icms_cst": None,
        "icms_csosn": None,
        "icms_base": Decimal("0"),
        "icms_aliquota": Decimal("0"),
        "icms_value": Decimal("0"),
        "pis_cst": None,
        "pis_aliquota": Decimal("0"),
        "pis_value": Decimal("0"),
        "cofins_cst": None,
        "cofins_aliquota": Decimal("0"),
        "cofins_value": Decimal("0"),
    }

    # ICMS
    if is_simples:
        out["icms_csosn"] = "102"  # Tributada pelo Simples sem permissão de crédito
        # Sob Simples, ICMS é recolhido no DAS — não destaca na NFe
    else:
        cst = "00"  # Tributada integralmente
        out["icms_cst"] = cst
        rate = Decimal(str(icms_aliquota or 0))
        if rate == 0:
            # Default razoável: 18% intra (varia por UF, ajustar nas configs)
            rate = Decimal("12") if is_outside_state else Decimal("18")
        out["icms_base"] = base
        out["icms_aliquota"] = rate
        out["icms_value"] = (base * rate / Decimal("100")).quantize(Decimal("0.01"))

    # PIS / COFINS
    if is_simples:
        # Simples Nacional não destaca PIS/COFINS na NFe
        out["pis_cst"] = "07"  # Operação isenta da contribuição
        out["cofins_cst"] = "07"
    else:
        # Lucro Real/Presumido — alíquota informada ou default não-cumulativo
        pis_rate = Decimal(str(pis_aliquota or 0)) or Decimal("1.65")
        cofins_rate = Decimal(str(cofins_aliquota or 0)) or Decimal("7.6")
        out["pis_cst"] = "01"
        out["pis_aliquota"] = pis_rate
        out["pis_value"] = (base * pis_rate / Decimal("100")).quantize(Decimal("0.01"))
        out["cofins_cst"] = "01"
        out["cofins_aliquota"] = cofins_rate
        out["cofins_value"] = (base * cofins_rate / Decimal("100")).quantize(Decimal("0.01"))

    return out


def suggest_cfop(*, purpose: str, uf_emit: str | None, uf_dest: str | None) -> str:
    """Sugere CFOP padrão para saída a partir de finalidade e UF emit/dest."""
    same_state = (uf_emit or "").upper() == (uf_dest or "").upper() and uf_emit
    if purpose == "venda":
        return "5102" if same_state else "6102"
    if purpose == "devolucao":
        return "5202" if same_state else "6202"
    if purpose == "remessa":
        return "5949" if same_state else "6949"
    if purpose == "transferencia":
        return "5152" if same_state else "6152"
    if purpose == "retorno":
        return "5949" if same_state else "6949"
    return "5102" if same_state else "6102"

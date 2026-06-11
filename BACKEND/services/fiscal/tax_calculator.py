"""Calculadora de impostos por item de NFe.

Suporta três modos de regime tributário (tax_regime_mode):

  legacy     — regime atual: ICMS / PIS / COFINS (CRT 1-4)
  transition — coexistência 2026-2032: calcula ICMS/PIS/COFINS reduzidos E IBS/CBS
               nas alíquotas escalonadas conforme cronograma EC 132/2023
  reform     — regime pleno IBS/CBS (a partir de 2033)

Alíquotas de transição CBS/IBS revisáveis em _TRANSITION_RATES por ano.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# ── Tabela de alíquotas de transição (CBS + IBS) por ano ─────────────────────
# Fonte: PLP 68/2024 — cronograma de escalonamento EC 132/2023.
# CBS (federal, substitui PIS+COFINS); IBS (dual, substitui ICMS+ISS).
# Revisar anualmente conforme publicação oficial do Comitê Gestor.
_TRANSITION_RATES: dict[int, dict] = {
    2026: {"cbs": Decimal("0.9"),  "ibs_uf": Decimal("0.05"), "ibs_mun": Decimal("0.05")},
    2027: {"cbs": Decimal("1.8"),  "ibs_uf": Decimal("0.10"), "ibs_mun": Decimal("0.05")},
    2028: {"cbs": Decimal("2.7"),  "ibs_uf": Decimal("0.20"), "ibs_mun": Decimal("0.10")},
    2029: {"cbs": Decimal("3.6"),  "ibs_uf": Decimal("0.30"), "ibs_mun": Decimal("0.15")},
    2030: {"cbs": Decimal("4.5"),  "ibs_uf": Decimal("0.40"), "ibs_mun": Decimal("0.20")},
    2031: {"cbs": Decimal("5.4"),  "ibs_uf": Decimal("0.60"), "ibs_mun": Decimal("0.25")},
    2032: {"cbs": Decimal("7.6"),  "ibs_uf": Decimal("0.80"), "ibs_mun": Decimal("0.30")},
}
# Regime pleno 2033+ (estimativas PLP 68 — sujeitas a alteração)
_REFORM_CBS  = Decimal("9.25")
_REFORM_IBS_UF  = Decimal("5.00")
_REFORM_IBS_MUN = Decimal("2.00")

# CST de não-incidência CBS e IBS durante período de teste
_CST_CBS_ISENTO  = "07"
_CST_IBS_ISENTO  = "07"
_CST_CBS_TRIBUTADO = "01"
_CST_IBS_TRIBUTADO = "01"


def _current_year() -> int:
    return date.today().year


def _transition_rates(year: int | None = None) -> dict:
    y = year or _current_year()
    if y in _TRANSITION_RATES:
        return _TRANSITION_RATES[y]
    if y > max(_TRANSITION_RATES):
        return _TRANSITION_RATES[max(_TRANSITION_RATES)]
    return _TRANSITION_RATES[min(_TRANSITION_RATES)]


# ── Calculadora principal ─────────────────────────────────────────────────────


def calculate_item_taxes(
    *,
    crt: int,
    cfop: str | None,
    base_value: Decimal | float | None,
    icms_aliquota: Decimal | float | None = None,
    pis_aliquota: Decimal | float | None = None,
    cofins_aliquota: Decimal | float | None = None,
    origin: int = 0,
    tax_regime_mode: str = "legacy",
    year: int | None = None,
) -> dict:
    """Calcula impostos por item conforme CRT e modo de regime tributário.

    Retorna dict com todos os campos de imposto do InvoiceItem.
    Campos ausentes no modo vigente são retornados como None/0.
    """
    base = Decimal(str(base_value or 0))
    is_simples = crt in (1, 2, 4)
    is_outside_state = bool(cfop and cfop.startswith("6"))

    out: dict = {
        # ICMS legacy
        "icms_cst": None, "icms_csosn": None,
        "icms_base": Decimal("0"), "icms_aliquota": Decimal("0"), "icms_value": Decimal("0"),
        # PIS/COFINS legacy
        "pis_cst": None, "pis_aliquota": Decimal("0"), "pis_value": Decimal("0"),
        "cofins_cst": None, "cofins_aliquota": Decimal("0"), "cofins_value": Decimal("0"),
        # CBS
        "cbs_cst": None, "cbs_aliquota": Decimal("0"), "cbs_base": Decimal("0"), "cbs_value": Decimal("0"),
        # IBS
        "ibs_cst": None,
        "ibs_aliquota_uf": Decimal("0"), "ibs_aliquota_mun": Decimal("0"),
        "ibs_base": Decimal("0"), "ibs_value": Decimal("0"),
        # IS
        "is_value": Decimal("0"),
    }

    mode = tax_regime_mode or "legacy"

    if mode in ("legacy", "transition"):
        _fill_legacy(out, base, is_simples, is_outside_state, icms_aliquota, pis_aliquota, cofins_aliquota)

    if mode in ("transition", "reform"):
        _fill_ibs_cbs(out, base, year)

    return out


def _fill_legacy(out: dict, base: Decimal, is_simples: bool, is_outside_state: bool,
                 icms_aliquota, pis_aliquota, cofins_aliquota) -> None:
    """Preenche campos ICMS/PIS/COFINS (regime legado)."""
    if is_simples:
        out["icms_csosn"] = "102"
        out["pis_cst"]    = "07"
        out["cofins_cst"] = "07"
    else:
        out["icms_cst"] = "00"
        rate = Decimal(str(icms_aliquota or 0))
        if rate == 0:
            rate = Decimal("12") if is_outside_state else Decimal("18")
        out["icms_base"]     = base
        out["icms_aliquota"] = rate
        out["icms_value"]    = (base * rate / Decimal("100")).quantize(Decimal("0.01"))

        pis_rate    = Decimal(str(pis_aliquota or 0)) or Decimal("1.65")
        cofins_rate = Decimal(str(cofins_aliquota or 0)) or Decimal("7.6")
        out["pis_cst"]           = "01"
        out["pis_aliquota"]      = pis_rate
        out["pis_value"]         = (base * pis_rate / Decimal("100")).quantize(Decimal("0.01"))
        out["cofins_cst"]        = "01"
        out["cofins_aliquota"]   = cofins_rate
        out["cofins_value"]      = (base * cofins_rate / Decimal("100")).quantize(Decimal("0.01"))


def _fill_ibs_cbs(out: dict, base: Decimal, year: int | None) -> None:
    """Preenche campos IBS/CBS conforme alíquotas do ano de transição ou reforma plena."""
    y = year or _current_year()
    if y >= 2033:
        cbs_rate    = _REFORM_CBS
        ibs_uf_rate = _REFORM_IBS_UF
        ibs_mu_rate = _REFORM_IBS_MUN
    else:
        rates       = _transition_rates(y)
        cbs_rate    = rates["cbs"]
        ibs_uf_rate = rates["ibs_uf"]
        ibs_mu_rate = rates["ibs_mun"]

    # CBS
    out["cbs_cst"]      = _CST_CBS_TRIBUTADO if cbs_rate > 0 else _CST_CBS_ISENTO
    out["cbs_aliquota"] = cbs_rate
    out["cbs_base"]     = base
    out["cbs_value"]    = (base * cbs_rate / Decimal("100")).quantize(Decimal("0.01"))

    # IBS
    ibs_total = ibs_uf_rate + ibs_mu_rate
    out["ibs_cst"]         = _CST_IBS_TRIBUTADO if ibs_total > 0 else _CST_IBS_ISENTO
    out["ibs_aliquota_uf"] = ibs_uf_rate
    out["ibs_aliquota_mun"]= ibs_mu_rate
    out["ibs_base"]        = base
    out["ibs_value"]       = (base * ibs_total / Decimal("100")).quantize(Decimal("0.01"))


# ── Sugestão de CFOP ─────────────────────────────────────────────────────────


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

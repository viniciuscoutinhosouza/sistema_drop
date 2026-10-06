"""Cascata de resolução fiscal POR PRODUTO (migration 147) — ponto único.

Resolve CADA campo fiscal de um item de emissão própria pela cascata:

    valor do PRODUTO  →  senão default_* da CMIG (CMIGFiscalConfig)  →  senão fallback

A regra DIVERGE por regime (``cfg.crt``):

- **CRT 1/2/4 (Simples Nacional)** — a nota usa **CSOSN** (produto.csosn → cfg.default_csosn →
  "102"). PIS/COFINS continuam como hoje (CST 99 zerado no builder); NÃO resolvemos alíquotas.
- **CRT 3 (Regime Normal — Lucro Real/Presumido)** — a nota usa **CST** de ICMS e destaca
  ICMS/IPI/PIS/COFINS reais. Aqui a cascata FALHA ALTO (``SefazServiceError``) quando não há
  como resolver o CST de ICMS (produto e CMIG ambos vazios) — emitir uma nota de Regime Normal
  sem grupo de ICMS correto é erro fiscal grave.

O dict retornado é o SNAPSHOT que grava as colunas fiscais do ``InvoiceItem`` na CRIAÇÃO da nota
(padrão do snapshot imutável de rastro/med — ADR-0027): uma vez gravado, a emissão lê do item,
nunca recalcula. A gravação só acontece se o campo ainda estiver vazio (edição manual vence).

Esta camada é PURA (sem ORM/DB): recebe o objeto ``produto`` (CMIGProduct/CatalogProduct) e a
``cfg`` (CMIGFiscalConfig) já carregados, e devolve um dict de valores escalares.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _sefaz_error(msg: str) -> Exception:
    """Instancia `SefazServiceError` por import TARDIO — mantém este módulo PURO (sem puxar o
    stack de DB do sefaz_service no import). A exceção é a MESMA que o router captura.

    Fallback a `RuntimeError` só se o stack de DB (sqlalchemy) estiver indisponível — jamais em
    produção; ainda assim FALHA ALTO (não engole o erro de CST ausente)."""
    try:
        from services.fiscal.sefaz_service import SefazServiceError
        return SefazServiceError(msg)
    except ImportError:
        return RuntimeError(msg)


# CRTs que são Simples Nacional (usam CSOSN); CRT 3 é Regime Normal (usa CST).
_CRT_SIMPLES = (1, 2, 4)

# Fallbacks conservadores do Regime Normal quando produto e CMIG não definem.
# Só o CST de ICMS NÃO tem fallback (falha alto): é o campo que define todo o grupo <ICMS>.
_FALLBACK_PIS_CST = "01"       # tributável, alíquota básica
_FALLBACK_COFINS_CST = "01"
_FALLBACK_PIS_ALIQ = Decimal("1.65")
_FALLBACK_COFINS_ALIQ = Decimal("7.60")


def _first(*vals: Any) -> Any:
    """Primeiro valor não-vazio da cascata (None e '' contam como vazio; 0 NÃO)."""
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None


def _g(obj: Any, name: str) -> Any:
    """getattr tolerante (produto/cfg podem não ter o atributo em versões antigas)."""
    return getattr(obj, name, None) if obj is not None else None


def resolve_item_fiscal(produto: Any, cfg: Any) -> dict:
    """Resolve os campos fiscais de UM item pela cascata produto → CMIG default → fallback.

    `produto`: CMIGProduct ou CatalogProduct (migration 147 — campos cfop/icms_cst/… por produto).
    `cfg`: CMIGFiscalConfig (crt + default_* + tax_regime_mode).

    Retorna um dict com as chaves das colunas de `InvoiceItem` a gravar (snapshot). Campos não
    aplicáveis ao regime ficam None. FALHA ALTO (SefazServiceError) no Regime Normal sem CST.
    """
    crt = int(_g(cfg, "crt") or 1)
    origin = _first(_g(produto, "origin"), _g(cfg, "default_origin"))
    cfop = _first(_g(produto, "cfop"), _g(cfg, "default_cfop"))

    out: dict = {"origin": origin, "cfop": cfop}

    if crt in _CRT_SIMPLES:
        # Simples: CSOSN manda; PIS/COFINS ficam como hoje (CST 99 zerado no builder — não tocamos).
        out["icms_csosn"] = _first(_g(produto, "csosn"), _g(cfg, "default_csosn"), "102")
        out["icms_cst"] = None
        return out

    # ── Regime Normal (CRT 3) ────────────────────────────────────────────────
    icms_cst = _first(_g(produto, "icms_cst"), _g(cfg, "default_icms_cst"))
    if not icms_cst:
        nome = _g(produto, "title") or _g(produto, "name") or _g(produto, "sku_cmig") or "?"
        raise _sefaz_error(
            f"Produto '{nome}' sem CST de ICMS e CMIG sem padrão (default_icms_cst) — "
            "configure o CST de ICMS antes de emitir no Regime Normal."
        )
    out["icms_csosn"] = None
    out["icms_cst"] = str(icms_cst).zfill(2)
    out["icms_aliquota"] = _dec(_first(_g(produto, "icms_aliquota"), _g(cfg, "default_icms_aliquota"))) or Decimal("0")
    out["icms_reducao_bc"] = _dec(_g(produto, "icms_reducao_bc")) or Decimal("0")
    out["fcp_aliquota"] = _dec(_g(produto, "fcp_aliquota")) or Decimal("0")
    out["mot_des_icms"] = _g(produto, "mot_des_icms")
    out["cbenef"] = _g(produto, "cbenef")

    # PIS/COFINS reais
    out["pis_cst"] = str(_first(_g(produto, "pis_cst"), _g(cfg, "default_pis_cst"), _FALLBACK_PIS_CST))
    out["cofins_cst"] = str(_first(_g(produto, "cofins_cst"), _g(cfg, "default_cofins_cst"), _FALLBACK_COFINS_CST))
    out["pis_aliquota"] = _dec(_first(_g(produto, "pis_aliquota"), _g(cfg, "default_pis_aliquota"), _FALLBACK_PIS_ALIQ)) or Decimal("0")
    out["cofins_aliquota"] = _dec(_first(_g(produto, "cofins_aliquota"), _g(cfg, "default_cofins_aliquota"), _FALLBACK_COFINS_ALIQ)) or Decimal("0")

    # IPI é OPCIONAL: só emite grupo <IPI> quando o produto tem ipi_cst. Sem ipi_cst → sem IPI.
    ipi_cst = _first(_g(produto, "ipi_cst"), _g(cfg, "default_ipi_cst"))
    if ipi_cst:
        out["ipi_cst"] = str(ipi_cst).zfill(2)
        out["ipi_aliquota"] = _dec(_g(produto, "ipi_aliquota")) or Decimal("0")
        out["ipi_cenq"] = _g(produto, "ipi_cenq") or "999"
    else:
        out["ipi_cst"] = None

    return out


def apply_fiscal_snapshot(item: Any, resolved: dict) -> None:
    """Grava o snapshot fiscal nas colunas do InvoiceItem SEM sobrescrever valor já presente.

    "Já presente" = coluna com valor não-nulo e não-zero/não-vazio: a edição manual vence a
    cascata (igual ao snapshot imutável de rastro/med — ADR-0027). Só preenche o que está vazio.
    """
    def _empty(cur: Any) -> bool:
        if cur is None:
            return True
        if isinstance(cur, str):
            return not cur.strip()
        try:
            return Decimal(str(cur)) == 0
        except (ValueError, ArithmeticError):
            return False

    for col in (
        "cfop", "origin", "icms_cst", "icms_csosn", "icms_aliquota", "icms_reducao_bc",
        "fcp_aliquota", "mot_des_icms", "cbenef", "pis_cst", "cofins_cst", "pis_aliquota",
        "cofins_aliquota", "ipi_cst", "ipi_aliquota", "ipi_cenq",
    ):
        if col not in resolved:
            continue
        if not hasattr(item, col):
            continue
        if _empty(getattr(item, col, None)):
            setattr(item, col, resolved[col])


def compute_item_tax_values(
    *, crt: int, vprod: Decimal,
    icms_cst: str | None, icms_aliquota: Decimal | None, icms_reducao_bc: Decimal | None,
    fcp_aliquota: Decimal | None,
    pis_cst: str | None, pis_aliquota: Decimal | None,
    cofins_cst: str | None, cofins_aliquota: Decimal | None,
    ipi_cst: str | None, ipi_aliquota: Decimal | None,
) -> dict:
    """Calcula os VALORES monetários do item no Regime Normal a partir de vProd e das alíquotas.

    Só CST tributados geram valor; CST isento/não-tributado/ST zera o próprio. Puro e sem efeitos.
    Retorna {icms_base, icms_value, fcp_value, pis_value, cofins_value, ipi_value}.
    """
    z = Decimal("0")
    out = {"icms_base": z, "icms_value": z, "fcp_value": z, "pis_value": z, "cofins_value": z, "ipi_value": z}
    if crt in _CRT_SIMPLES:
        return out  # Simples não destaca — valores ficam zerados (recolhe no DAS).

    vprod = Decimal(str(vprod or 0))
    aliq_icms = Decimal(str(icms_aliquota or 0))
    red = Decimal(str(icms_reducao_bc or 0))
    # ICMS com valor próprio: CST 00 (integral) e 20 (redução BC). CST 40/41/50/60/90 não calculam
    # ICMS próprio nesta fase (isento/ST retida/outras) — o grupo sai sem vICMS tributado.
    cst = (icms_cst or "").zfill(2)
    if cst in ("00", "20"):
        base = (vprod * (Decimal("100") - red) / Decimal("100")).quantize(Decimal("0.01"))
        out["icms_base"] = base
        out["icms_value"] = (base * aliq_icms / Decimal("100")).quantize(Decimal("0.01"))
        fcp = Decimal(str(fcp_aliquota or 0))
        if fcp > 0:
            out["fcp_value"] = (base * fcp / Decimal("100")).quantize(Decimal("0.01"))

    # PIS/COFINS: só CST tributável aliq (01/02) geram valor; NT (04/05/06/07/08/09) = 0.
    if (pis_cst or "") in ("01", "02"):
        out["pis_value"] = (vprod * Decimal(str(pis_aliquota or 0)) / Decimal("100")).quantize(Decimal("0.01"))
    if (cofins_cst or "") in ("01", "02"):
        out["cofins_value"] = (vprod * Decimal(str(cofins_aliquota or 0)) / Decimal("100")).quantize(Decimal("0.01"))

    # IPI: só tributado (CST 50 + alíquota > 0) gera valor. 52/53/55 saem com zeros; isentos sem valor.
    if ipi_cst and (ipi_cst or "").zfill(2) == "50":
        out["ipi_value"] = (vprod * Decimal(str(ipi_aliquota or 0)) / Decimal("100")).quantize(Decimal("0.01"))

    return out

"""Montagem do XML NFe 4.00 a partir de `NotaEmissao` (via lxml, minificado).

lxml (não f-strings) protege contra escape de caracteres especiais, namespace
duplicado e whitespace entre tags (SEFAZ rejeita com cStat=588).

Cobertura: NFe-55, DOIS regimes.
- **Simples Nacional (CRT 1/2/4)** — item com `csosn`. CSOSN 102 (sem ST) e 500 (ICMS-ST já
  retido). PIS/COFINS CST 99 zerado; sem grupo IPI; totais ICMSTot zerados. RAMO INTOCADO: a
  saída é byte-idêntica à histórica (zero regressão).
- **Regime Normal (CRT 3 — Lucro Real/Presumido)** — item com `icms_cst` (sem `csosn`). Grupos
  ICMS por CST (00/20/40/41/50/60; 10/70/90 caem num ICMS90 genérico válido), IPI opcional, PIS/
  COFINS reais por CST, e ICMSTot com totais REAIS somados dos itens.

Sem ICMSUFDest/DIFAL de partilha (Simples — Tema 1093/STF; no Normal é fase futura). `idDest`
calculado (intra x inter-UF). NFCe-65, ICMS10/70 completos, IBS/CBS/IS: fases futuras.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from lxml import etree

from services.fiscal.sefaz.exceptions import XmlBuildError
from services.fiscal.sefaz.models import (
    Cliente,
    Endereco,
    Estabelecimento,
    ItemEmissao,
    NotaEmissao,
    Pagamento,
)

NFE_NAMESPACE: Final = "http://www.portalfiscal.inf.br/nfe"

_CODIGO_UF: Final[dict[str, str]] = {
    "AC": "12", "AL": "27", "AM": "13", "AP": "16", "BA": "29", "CE": "23",
    "DF": "53", "ES": "32", "GO": "52", "MA": "21", "MG": "31", "MS": "50",
    "MT": "51", "PA": "15", "PB": "25", "PE": "26", "PI": "22", "PR": "41",
    "RJ": "33", "RN": "24", "RO": "11", "RR": "14", "RS": "43", "SC": "42",
    "SE": "28", "SP": "35", "TO": "17",
}

_CSOSN_SUPORTADOS: Final = frozenset({"102", "500"})


def codigo_uf(uf: str) -> str:
    """cUF (2 dígitos) a partir da UF de 2 letras."""
    try:
        return _CODIGO_UF[uf]
    except KeyError as exc:
        raise XmlBuildError(f"UF desconhecida: {uf!r}") from exc


# --- formatação fiscal --------------------------------------------------------

def fmt_qtd(d: Decimal) -> str:
    return f"{d:.4f}"


def fmt_unit(d: Decimal) -> str:
    return f"{d:.10f}"


def fmt_val(d: Decimal) -> str:
    return f"{d:.2f}"


def fmt_pct(d: Decimal) -> str:
    return f"{d:.2f}"


def fmt_iso_datetime(dt_aware: object) -> str:
    """ISO 8601 com offset ':' (SEFAZ exige '+00:00', Python emite '+0000')."""
    if not hasattr(dt_aware, "isoformat"):
        raise XmlBuildError(f"dh_emi precisa ser datetime, recebido {type(dt_aware)}")
    iso = dt_aware.isoformat(timespec="seconds")  # type: ignore[attr-defined]
    if len(iso) >= 5 and iso[-5] in "+-" and iso[-3] != ":":
        iso = iso[:-2] + ":" + iso[-2:]
    return iso


# --- blocos -------------------------------------------------------------------

def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    elem = etree.SubElement(parent, f"{{{NFE_NAMESPACE}}}{tag}")
    if text is not None:
        elem.text = text
    return elem


def _montar_endereco(parent: etree._Element, tag: str, end: Endereco, telefone: str | None) -> None:
    ender = _sub(parent, tag)
    _sub(ender, "xLgr", end.logradouro)
    _sub(ender, "nro", end.numero)
    if end.complemento:
        _sub(ender, "xCpl", end.complemento)
    _sub(ender, "xBairro", end.bairro)
    _sub(ender, "cMun", end.municipio_ibge)
    _sub(ender, "xMun", end.municipio_nome)
    _sub(ender, "UF", end.uf)
    _sub(ender, "CEP", end.cep)
    _sub(ender, "cPais", end.pais_codigo)
    _sub(ender, "xPais", end.pais_nome)
    if telefone:
        _sub(ender, "fone", telefone)


def _id_dest(nota: NotaEmissao) -> str:
    """idDest: 1=interna (mesma UF), 2=interestadual, 3=exterior."""
    if nota.destinatario.endereco.pais_codigo != "1058":
        return "3"
    return "1" if nota.emitente.endereco.uf == nota.destinatario.endereco.uf else "2"


def _montar_ide(inf_nfe: etree._Element, nota: NotaEmissao) -> None:
    ide = _sub(inf_nfe, "ide")
    _sub(ide, "cUF", codigo_uf(nota.emitente.endereco.uf))
    _sub(ide, "cNF", nota.c_nf)
    _sub(ide, "natOp", nota.natureza_operacao)
    _sub(ide, "mod", str(nota.modelo))
    _sub(ide, "serie", str(nota.serie))
    _sub(ide, "nNF", str(nota.numero))
    _sub(ide, "dhEmi", fmt_iso_datetime(nota.dh_emi))
    _sub(ide, "tpNF", "0" if nota.finalidade == 4 else "1")  # 0=entrada(devolução), 1=saída
    _sub(ide, "idDest", _id_dest(nota))
    _sub(ide, "cMunFG", nota.emitente.endereco.municipio_ibge)
    _sub(ide, "tpImp", "1")  # DANFE retrato
    _sub(ide, "tpEmis", str(nota.tp_emis))
    _sub(ide, "cDV", nota.chave[-1])
    _sub(ide, "tpAmb", "2" if nota.ambiente == "homologacao" else "1")
    _sub(ide, "finNFe", str(nota.finalidade))
    _sub(ide, "indFinal", str(nota.ind_final))
    _sub(ide, "indPres", str(nota.ind_presenca))
    _sub(ide, "indIntermed", str(nota.ind_intermed))
    _sub(ide, "procEmi", "0")
    _sub(ide, "verProc", nota.ver_proc)
    # Devolução (finalidade=4) referencia a NF-e original
    if nota.finalidade == 4 and nota.chave_referenciada:
        nfref = _sub(ide, "NFref")
        _sub(nfref, "refNFe", nota.chave_referenciada)


def _montar_emit(inf_nfe: etree._Element, emit: Estabelecimento) -> None:
    el = _sub(inf_nfe, "emit")
    _sub(el, "CNPJ", emit.cnpj)
    _sub(el, "xNome", emit.razao_social)
    if emit.nome_fantasia:
        _sub(el, "xFant", emit.nome_fantasia)
    _montar_endereco(el, "enderEmit", emit.endereco, emit.telefone)
    _sub(el, "IE", emit.ie)
    if emit.ie_st:
        _sub(el, "IEST", emit.ie_st)
    _sub(el, "CRT", str(emit.crt))


def _montar_dest(inf_nfe: etree._Element, dest: Cliente, ambiente: str) -> None:
    el = _sub(inf_nfe, "dest")
    if dest.tipo == "PJ":
        _sub(el, "CNPJ", dest.cpf_cnpj)
    else:
        _sub(el, "CPF", dest.cpf_cnpj)
    # Homologação: xNome literal obrigatório (regra SEFAZ).
    nome = (
        "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
        if ambiente == "homologacao"
        else dest.nome_razao_social
    )
    _sub(el, "xNome", nome)
    _montar_endereco(el, "enderDest", dest.endereco, dest.telefone)
    _sub(el, "indIEDest", str(dest.indicador_ie))
    if dest.indicador_ie in (1, 2) and dest.ie:
        _sub(el, "IE", dest.ie)
    if dest.email:
        _sub(el, "email", dest.email)


def _montar_pis_cofins_simples(imposto: etree._Element) -> None:
    """PIS/COFINS do Simples: CST 99 (outras operações), zerado (recolhe no DAS)."""
    pis = _sub(imposto, "PIS")
    pis_outr = _sub(pis, "PISOutr")
    _sub(pis_outr, "CST", "99")
    _sub(pis_outr, "vBC", "0.00")
    _sub(pis_outr, "pPIS", "0.00")
    _sub(pis_outr, "vPIS", "0.00")
    cofins = _sub(imposto, "COFINS")
    cofins_outr = _sub(cofins, "COFINSOutr")
    _sub(cofins_outr, "CST", "99")
    _sub(cofins_outr, "vBC", "0.00")
    _sub(cofins_outr, "pCOFINS", "0.00")
    _sub(cofins_outr, "vCOFINS", "0.00")


def _montar_imposto_simples(imposto: etree._Element, item: ItemEmissao) -> None:
    """<imposto> do item — Simples Nacional (CSOSN 102 ou 500). Sem IPI.

    RAMO ORIGINAL, intocado — a saída tem de ficar BYTE-IDÊNTICA à histórica (zero regressão)."""
    csosn = item.produto.csosn
    icms = _sub(imposto, "ICMS")
    if csosn == "102":
        sn = _sub(icms, "ICMSSN102")
        _sub(sn, "orig", item.produto.origem)
        _sub(sn, "CSOSN", "102")
    elif csosn == "500":
        # Mercadoria já recebida com ICMS-ST retido — não recalcula ST.
        sn = _sub(icms, "ICMSSN500")
        _sub(sn, "orig", item.produto.origem)
        _sub(sn, "CSOSN", "500")
        _sub(sn, "vBCSTRet", fmt_val(item.produto.vbc_st_ret or Decimal("0")))
        _sub(sn, "vICMSSTRet", fmt_val(item.produto.vicms_st_ret or Decimal("0")))
    else:
        raise XmlBuildError(
            f"CSOSN {csosn!r} não suportado no xml_builder (suportados: {sorted(_CSOSN_SUPORTADOS)})."
        )
    _montar_pis_cofins_simples(imposto)


# ── Regime Normal (CRT 3) — grupos ICMS por CST, IPI, PIS/COFINS reais ────────
# Leiaute NFe 4.00. Cada CST tem o seu grupo filho de <ICMS>. Esta fase cobre os CST mais comuns
# da REVENDA/dropshipping: 00 (tributado integral), 20 (redução de BC), 40/41/50 (isenta/não-trib/
# suspensão), 60 (ST já recolhida). 10/70 (com ST própria) e casos completos de 90 caem num ICMS90
# genérico (fallback válido) — completar 10/70 é fase futura.

_ICMS_DESON = frozenset({"40", "41", "50"})  # CST desoneráveis (vICMSDeson/motDesICMS)


def _cbenef(grupo: etree._Element, item: ItemEmissao) -> None:
    """cBenef (código de benefício fiscal) — logo após o CST no grupo <ICMSxx>, quando houver."""
    cb = item.produto.cbenef
    if cb:
        _sub(grupo, "cBenef", cb)


def _montar_icms_normal(icms: etree._Element, item: ItemEmissao) -> None:
    p = item.produto
    cst = (p.icms_cst or "").zfill(2)
    orig = p.origem
    vbc = p.icms_base or Decimal("0")
    vicms = p.icms_value or Decimal("0")
    aliq = p.icms_aliquota or Decimal("0")

    if cst == "00":
        g = _sub(icms, "ICMS00")
        _sub(g, "orig", orig)
        _sub(g, "CST", "00")
        _cbenef(g, item)
        _sub(g, "modBC", "3")  # 3 = valor da operação
        _sub(g, "vBC", fmt_val(vbc))
        _sub(g, "pICMS", fmt_pct(aliq))
        _sub(g, "vICMS", fmt_val(vicms))
    elif cst == "20":
        g = _sub(icms, "ICMS20")
        _sub(g, "orig", orig)
        _sub(g, "CST", "20")
        _cbenef(g, item)
        _sub(g, "modBC", "3")
        _sub(g, "pRedBC", fmt_pct(p.icms_reducao_bc or Decimal("0")))
        _sub(g, "vBC", fmt_val(vbc))
        _sub(g, "pICMS", fmt_pct(aliq))
        _sub(g, "vICMS", fmt_val(vicms))
        fcp = p.fcp_aliquota or Decimal("0")
        if fcp > 0:
            _sub(g, "vBCFCP", fmt_val(vbc))
            _sub(g, "pFCP", fmt_pct(fcp))
            _sub(g, "vFCP", fmt_val(p.fcp_value or Decimal("0")))
    elif cst in _ICMS_DESON:
        # 40 isenta / 41 não tributada / 50 suspensão. Grupo mínimo: orig + CST (+ desoneração).
        g = _sub(icms, f"ICMS{cst}")
        _sub(g, "orig", orig)
        _sub(g, "CST", cst)
        _cbenef(g, item)
        if p.mot_des_icms:
            # vICMSDeson vem antes de motDesICMS no schema; sem valor da desoneração, 0.00.
            _sub(g, "vICMSDeson", fmt_val(vicms or Decimal("0")))
            _sub(g, "motDesICMS", p.mot_des_icms)
    elif cst == "60":
        # ST já recolhida anteriormente. Revenda sem os valores retidos → 0.00 (aceito pela SEFAZ).
        g = _sub(icms, "ICMS60")
        _sub(g, "orig", orig)
        _sub(g, "CST", "60")
        _cbenef(g, item)
        _sub(g, "vBCSTRet", fmt_val(p.vbc_st_ret or Decimal("0")))
        _sub(g, "vICMSSTRet", fmt_val(p.vicms_st_ret or Decimal("0")))
    else:
        # ICMS90 (outras) — fallback genérico VÁLIDO para 10/70/90 nesta fase. Tributa como 00
        # (orig/CST/modBC/vBC/pICMS/vICMS); os componentes de ST de 10/70 ficam p/ fase futura.
        g = _sub(icms, "ICMS90")
        _sub(g, "orig", orig)
        _sub(g, "CST", cst or "90")
        _cbenef(g, item)
        _sub(g, "modBC", "3")
        _sub(g, "vBC", fmt_val(vbc))
        _sub(g, "pICMS", fmt_pct(aliq))
        _sub(g, "vICMS", fmt_val(vicms))


# IPI: CST que indicam tributação (têm alíquota/valor) vs. não-tributados.
_IPI_TRIB = frozenset({"00", "49", "50", "99"})  # tributados → <IPITrib>
_IPI_NT = frozenset({"01", "02", "03", "04", "05", "51", "52", "53", "54", "55"})  # <IPINT>


def _montar_ipi_normal(imposto: etree._Element, item: ItemEmissao) -> None:
    """Grupo <IPI> — só quando o item tem ipi_cst. Conservador: IPITrib p/ tributado, IPINT p/ não.

    Entrada (CST 50) e saída tributada → <IPITrib> com vBC/pIPI/vIPI. Isenta/imune/suspensa →
    <IPINT> só com o CST. Alíquota-zero (52/53/54/55) tratado como IPINT (sem destacar valor)."""
    cst = (item.produto.ipi_cst or "").zfill(2)
    if not item.produto.ipi_cst:
        return
    ipi = _sub(imposto, "IPI")
    _sub(ipi, "cEnq", item.produto.ipi_cenq or "999")
    vipi = item.produto.ipi_value or Decimal("0")
    if cst in _IPI_TRIB:
        trib = _sub(ipi, "IPITrib")
        _sub(trib, "CST", cst)
        _sub(trib, "vBC", fmt_val(item.valor_produto))
        _sub(trib, "pIPI", fmt_pct(item.produto.ipi_aliquota or Decimal("0")))
        _sub(trib, "vIPI", fmt_val(vipi))
    else:
        # Default conservador: qualquer outro CST (incl. 01-05 e 51-55) sai como não-tributado.
        nt = _sub(ipi, "IPINT")
        _sub(nt, "CST", cst)


_PIS_COFINS_ALIQ = frozenset({"01", "02"})         # tributável por alíquota → PISAliq/COFINSAliq
_PIS_COFINS_NT = frozenset({"04", "05", "06", "07", "08", "09"})  # não-tributado → PISNT/COFINSNT


def _montar_pis_cofins_normal(imposto: etree._Element, item: ItemEmissao) -> None:
    """PIS/COFINS reais do Regime Normal por CST. NÃO usa o 99 zerado do Simples."""
    p = item.produto
    pis_cst = (p.pis_cst or "49").zfill(2)
    cofins_cst = (p.cofins_cst or "49").zfill(2)

    pis = _sub(imposto, "PIS")
    if pis_cst in _PIS_COFINS_ALIQ:
        g = _sub(pis, "PISAliq")
        _sub(g, "CST", pis_cst)
        _sub(g, "vBC", fmt_val(item.valor_produto))
        _sub(g, "pPIS", fmt_pct(p.pis_aliquota or Decimal("0")))
        _sub(g, "vPIS", fmt_val(p.pis_value or Decimal("0")))
    elif pis_cst in _PIS_COFINS_NT:
        g = _sub(pis, "PISNT")
        _sub(g, "CST", pis_cst)
    else:
        g = _sub(pis, "PISOutr")
        _sub(g, "CST", pis_cst)
        _sub(g, "vBC", "0.00")
        _sub(g, "pPIS", "0.00")
        _sub(g, "vPIS", "0.00")

    cofins = _sub(imposto, "COFINS")
    if cofins_cst in _PIS_COFINS_ALIQ:
        g = _sub(cofins, "COFINSAliq")
        _sub(g, "CST", cofins_cst)
        _sub(g, "vBC", fmt_val(item.valor_produto))
        _sub(g, "pCOFINS", fmt_pct(p.cofins_aliquota or Decimal("0")))
        _sub(g, "vCOFINS", fmt_val(p.cofins_value or Decimal("0")))
    elif cofins_cst in _PIS_COFINS_NT:
        g = _sub(cofins, "COFINSNT")
        _sub(g, "CST", cofins_cst)
    else:
        g = _sub(cofins, "COFINSOutr")
        _sub(g, "CST", cofins_cst)
        _sub(g, "vBC", "0.00")
        _sub(g, "pCOFINS", "0.00")
        _sub(g, "vCOFINS", "0.00")


def _montar_imposto_normal(imposto: etree._Element, item: ItemEmissao) -> None:
    """<imposto> do item — Regime Normal (CRT 3): ICMS por CST + IPI (opcional) + PIS/COFINS reais.

    Ordem do schema NFe 4.00 no grupo <imposto>: ICMS, (IPI), PIS, COFINS."""
    icms = _sub(imposto, "ICMS")
    _montar_icms_normal(icms, item)
    _montar_ipi_normal(imposto, item)  # <IPI> entre <ICMS> e <PIS>, só quando presente
    _montar_pis_cofins_normal(imposto, item)


def _montar_imposto(imposto: etree._Element, item: ItemEmissao) -> None:
    """<imposto> do item — ramifica por regime SEM tocar o ramo Simples (zero regressão).

    Simples (item com `csosn`) → ramo histórico byte-idêntico. Regime Normal (item com `icms_cst`,
    sem csosn) → grupos ICMS por CST + IPI + PIS/COFINS reais. A escolha é só pela presença do
    csosn: a `Produto` já garante exatamente um dos dois no `__post_init__`."""
    if item.produto.csosn is not None:
        _montar_imposto_simples(imposto, item)
    else:
        _montar_imposto_normal(imposto, item)


def _montar_det(inf_nfe: etree._Element, item: ItemEmissao) -> None:
    det = etree.SubElement(inf_nfe, f"{{{NFE_NAMESPACE}}}det")
    det.set("nItem", str(item.numero_item))
    prod = _sub(det, "prod")
    _sub(prod, "cProd", item.produto.codigo)
    _sub(prod, "cEAN", item.produto.ean or "SEM GTIN")
    _sub(prod, "xProd", item.produto.descricao)
    _sub(prod, "NCM", item.produto.ncm)
    if item.produto.cest:
        _sub(prod, "CEST", item.produto.cest)
    _sub(prod, "CFOP", item.cfop)
    _sub(prod, "uCom", item.produto.unidade)
    _sub(prod, "qCom", fmt_qtd(item.quantidade))
    _sub(prod, "vUnCom", fmt_unit(item.preco_unitario))
    _sub(prod, "vProd", fmt_val(item.valor_produto))
    _sub(prod, "cEANTrib", item.produto.ean or "SEM GTIN")
    _sub(prod, "uTrib", item.produto.unidade)
    _sub(prod, "qTrib", fmt_qtd(item.quantidade))
    _sub(prod, "vUnTrib", fmt_unit(item.preco_unitario))
    if item.valor_frete:
        _sub(prod, "vFrete", fmt_val(item.valor_frete))
    if item.valor_seguro:
        _sub(prod, "vSeg", fmt_val(item.valor_seguro))
    if item.valor_desconto:
        _sub(prod, "vDesc", fmt_val(item.valor_desconto))
    if item.valor_outras:
        _sub(prod, "vOutro", fmt_val(item.valor_outras))
    _sub(prod, "indTot", "1")
    # Rastreabilidade (ADR-0027) — grupos filhos de <prod>, na ordem do schema NFe 4.00:
    # <rastro> (I80, 0..500) DEPOIS de indTot e ANTES de <med> (K).
    for r in (item.rastros or ()):
        rastro = _sub(prod, "rastro")
        _sub(rastro, "nLote", r.n_lote)
        _sub(rastro, "qLote", fmt_qtd(r.q_lote))
        if r.d_fab:
            _sub(rastro, "dFab", r.d_fab)
        if r.d_val:
            _sub(rastro, "dVal", r.d_val)
        if r.c_agreg:
            _sub(rastro, "cAgreg", r.c_agreg)
    if item.produto.med_anvisa:
        med = _sub(prod, "med")
        _sub(med, "cProdANVISA", item.produto.med_anvisa)
        if item.produto.med_anvisa == "ISENTO" and item.produto.med_exempt_reason:
            _sub(med, "xMotivoIsencao", item.produto.med_exempt_reason)
        _sub(med, "vPMC", fmt_val(item.produto.med_pmc or Decimal("0")))
    imposto = _sub(det, "imposto")
    _montar_imposto(imposto, item)
    if item.produto.info_adicional:
        _sub(det, "infAdProd", item.produto.info_adicional)


def _nota_e_simples(nota: NotaEmissao) -> bool:
    """Todos os itens de uma nota são do MESMO regime (mesmo CRT). Detecta pela presença de csosn.

    Simples → ao menos um item com csosn (na prática, todos). Regime Normal → nenhum csosn.

    BLINDAGEM: uma nota NUNCA pode misturar itens CSOSN (Simples) com itens CST (Regime Normal) —
    seria zerar o ICMSTot em silêncio (ramo Simples) sobre itens que destacam ICMS real. Caso
    inalcançável hoje (o emissor usa um único CRT por nota), mas falha alto se acontecer."""
    tem_csosn = any(i.produto.csosn is not None for i in nota.itens)
    tem_cst = any(i.produto.icms_cst is not None for i in nota.itens)
    if tem_csosn and tem_cst:
        raise XmlBuildError(
            "nota não pode misturar CSOSN (Simples) e CST (Regime Normal)"
        )
    return tem_csosn


def _montar_total(inf_nfe: etree._Element, nota: NotaEmissao) -> None:
    total = _sub(inf_nfe, "total")
    icms_tot = _sub(total, "ICMSTot")
    zero = "0.00"
    soma_frete = sum((i.valor_frete for i in nota.itens), start=Decimal("0"))
    soma_seg = sum((i.valor_seguro for i in nota.itens), start=Decimal("0"))
    soma_desc = sum((i.valor_desconto for i in nota.itens), start=Decimal("0"))
    soma_outro = sum((i.valor_outras for i in nota.itens), start=Decimal("0"))

    if _nota_e_simples(nota):
        # RAMO ORIGINAL (Simples) — totais zerados, BYTE-IDÊNTICOS ao histórico (zero regressão).
        v_bc = v_icms = v_deson = v_fcp = v_st = v_ipi = v_pis = v_cofins = zero
    else:
        # Regime Normal — totais REAIS somados dos itens (snapshot gravado no InvoiceItem).
        def _soma(attr: str) -> Decimal:
            return sum((getattr(i.produto, attr) or Decimal("0") for i in nota.itens), start=Decimal("0"))
        v_bc = fmt_val(_soma("icms_base"))
        v_icms = fmt_val(_soma("icms_value"))
        v_deson = zero
        v_fcp = fmt_val(_soma("fcp_value"))
        v_st = fmt_val(_soma("vicms_st_ret"))  # ST retida (CST 60) — o que há de ST nesta fase
        v_ipi = fmt_val(_soma("ipi_value"))
        v_pis = fmt_val(_soma("pis_value"))
        v_cofins = fmt_val(_soma("cofins_value"))

    _sub(icms_tot, "vBC", v_bc)
    _sub(icms_tot, "vICMS", v_icms)
    _sub(icms_tot, "vICMSDeson", v_deson)
    _sub(icms_tot, "vFCP", v_fcp)
    _sub(icms_tot, "vBCST", zero)
    _sub(icms_tot, "vST", v_st)
    _sub(icms_tot, "vFCPST", zero)
    _sub(icms_tot, "vFCPSTRet", zero)
    _sub(icms_tot, "vProd", fmt_val(nota.valor_total_produtos))
    _sub(icms_tot, "vFrete", fmt_val(soma_frete))
    _sub(icms_tot, "vSeg", fmt_val(soma_seg))
    _sub(icms_tot, "vDesc", fmt_val(soma_desc))
    _sub(icms_tot, "vII", zero)
    _sub(icms_tot, "vIPI", v_ipi)
    _sub(icms_tot, "vIPIDevol", zero)
    _sub(icms_tot, "vPIS", v_pis)
    _sub(icms_tot, "vCOFINS", v_cofins)
    _sub(icms_tot, "vOutro", fmt_val(soma_outro))
    _sub(icms_tot, "vNF", fmt_val(nota.valor_total_nf))


def _montar_transp(inf_nfe: etree._Element, nota: NotaEmissao) -> None:
    transp = _sub(inf_nfe, "transp")
    _sub(transp, "modFrete", str(nota.transporte_modalidade))


def _montar_pag(inf_nfe: etree._Element, nota: NotaEmissao) -> None:
    pag = _sub(inf_nfe, "pag")
    pagamentos: tuple[Pagamento, ...] = nota.pagamentos or (
        Pagamento(forma_pag="01", valor=nota.valor_total_nf, ind_pag=0),
    )
    for p in pagamentos:
        det_pag = _sub(pag, "detPag")
        _sub(det_pag, "indPag", str(p.ind_pag))
        _sub(det_pag, "tPag", p.forma_pag)
        _sub(det_pag, "vPag", fmt_val(p.valor))
        if p.troco is not None:
            _sub(det_pag, "vTroco", fmt_val(p.troco))


def _montar_inf_adic(inf_nfe: etree._Element, nota: NotaEmissao) -> None:
    if not nota.info_complementar and not nota.info_fisco:
        return
    inf_adic = _sub(inf_nfe, "infAdic")
    if nota.info_fisco:
        _sub(inf_adic, "infAdFisco", nota.info_fisco)
    if nota.info_complementar:
        _sub(inf_adic, "infCpl", nota.info_complementar)


def montar_xml_nfe(nota: NotaEmissao) -> str:
    """Monta o XML NFe 4.00 minificado a partir de `NotaEmissao` (pronto p/ assinar)."""
    nsmap: dict[str | None, str] = {None: NFE_NAMESPACE}
    nfe = etree.Element(f"{{{NFE_NAMESPACE}}}NFe", nsmap=nsmap)  # type: ignore[arg-type]
    inf_nfe = etree.SubElement(nfe, f"{{{NFE_NAMESPACE}}}infNFe")
    inf_nfe.set("versao", "4.00")
    inf_nfe.set("Id", f"NFe{nota.chave}")

    _montar_ide(inf_nfe, nota)
    _montar_emit(inf_nfe, nota.emitente)
    _montar_dest(inf_nfe, nota.destinatario, nota.ambiente)
    for item in nota.itens:
        _montar_det(inf_nfe, item)
    _montar_total(inf_nfe, nota)
    _montar_transp(inf_nfe, nota)
    _montar_pag(inf_nfe, nota)
    _montar_inf_adic(inf_nfe, nota)

    return etree.tostring(nfe, xml_declaration=True, encoding="UTF-8", pretty_print=False).decode("utf-8")

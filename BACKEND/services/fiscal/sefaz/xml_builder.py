"""Montagem do XML NFe 4.00 a partir de `NotaEmissao` (via lxml, minificado).

lxml (não f-strings) protege contra escape de caracteres especiais, namespace
duplicado e whitespace entre tags (SEFAZ rejeita com cStat=588).

Cobertura: NFe-55 + Simples Nacional. CSOSN 102 (sem ST) e 500 (mercadoria com
ICMS-ST já retido). PIS/COFINS CST 99 zerado; sem grupo IPI; sem ICMSUFDest/DIFAL
de partilha (Simples — Tema 1093/STF). `idDest` é calculado (intra x inter-UF).
NFCe-65, ST como substituto, devolução com tributos destacados: fases futuras.
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


def _montar_imposto(imposto: etree._Element, item: ItemEmissao) -> None:
    """<imposto> do item — Simples Nacional (CSOSN 102 ou 500). Sem IPI."""
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
    imposto = _sub(det, "imposto")
    _montar_imposto(imposto, item)
    if item.produto.info_adicional:
        _sub(det, "infAdProd", item.produto.info_adicional)


def _montar_total(inf_nfe: etree._Element, nota: NotaEmissao) -> None:
    total = _sub(inf_nfe, "total")
    icms_tot = _sub(total, "ICMSTot")
    zero = "0.00"
    soma_frete = sum((i.valor_frete for i in nota.itens), start=Decimal("0"))
    soma_seg = sum((i.valor_seguro for i in nota.itens), start=Decimal("0"))
    soma_desc = sum((i.valor_desconto for i in nota.itens), start=Decimal("0"))
    soma_outro = sum((i.valor_outras for i in nota.itens), start=Decimal("0"))
    _sub(icms_tot, "vBC", zero)
    _sub(icms_tot, "vICMS", zero)
    _sub(icms_tot, "vICMSDeson", zero)
    _sub(icms_tot, "vFCP", zero)
    _sub(icms_tot, "vBCST", zero)
    _sub(icms_tot, "vST", zero)
    _sub(icms_tot, "vFCPST", zero)
    _sub(icms_tot, "vFCPSTRet", zero)
    _sub(icms_tot, "vProd", fmt_val(nota.valor_total_produtos))
    _sub(icms_tot, "vFrete", fmt_val(soma_frete))
    _sub(icms_tot, "vSeg", fmt_val(soma_seg))
    _sub(icms_tot, "vDesc", fmt_val(soma_desc))
    _sub(icms_tot, "vII", zero)
    _sub(icms_tot, "vIPI", zero)
    _sub(icms_tot, "vIPIDevol", zero)
    _sub(icms_tot, "vPIS", zero)
    _sub(icms_tot, "vCOFINS", zero)
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

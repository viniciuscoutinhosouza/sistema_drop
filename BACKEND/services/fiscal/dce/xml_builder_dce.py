"""Montador do XML da DC-e (infDCe) — perfil Marketplace (tpEmit=1).

Estrutura conforme o leiaute SVRS (Anexo I) e o schema `DCe_v1.00.xsd`:
  DCe > infDCe(versao, Id) > ide, emit(+enderEmit), Marketplace, dest(+enderDest), det[], total, transp

O `emit` é o REMETENTE (vendedor CPF); o grupo `Marketplace` é o ASSINANTE (CNPJ da MIG). A chave
de acesso é keyed ao CNPJ do assinante.

⚠️ VALIDAR CONTRA O XSD EM HOMOLOGAÇÃO: os nomes/ordem de tags aqui seguem o leiaute documentado e um
DACE real, mas o `DCe_v1.00.xsd` é a fonte canônica — rodar validação de schema + emissão em
homologação (tpAmb=2) antes de produção. Assinatura (Signature) é adicionada depois pelo signer.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from lxml import etree

NS_DCE = "http://www.portalfiscal.inf.br/dce"
VERSAO = "1.00"
MODELO = "99"
TP_EMIT_MARKETPLACE = "1"
CPAIS_BR = "1058"
XPAIS_BR = "BRASIL"


def _fmt(value, casas: int) -> str:
    q = Decimal(10) ** -casas
    return str(Decimal(str(value or 0)).quantize(q, rounding=ROUND_HALF_UP))


def _sub(parent, tag: str, text=None):
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _add_endereco(parent, tag: str, end: dict) -> None:
    e = _sub(parent, tag)
    _sub(e, "xLgr", end.get("x_lgr"))
    _sub(e, "nro", end.get("nro") or "S/N")
    if end.get("x_cpl"):
        _sub(e, "xCpl", end["x_cpl"])
    _sub(e, "xBairro", end.get("x_bairro"))
    _sub(e, "cMun", end.get("c_mun"))   # código IBGE do município (7 díg.)
    _sub(e, "xMun", end.get("x_mun"))
    _sub(e, "UF", end.get("uf"))
    _sub(e, "CEP", (end.get("cep") or "").replace("-", "").replace(".", ""))
    _sub(e, "cPais", CPAIS_BR)
    _sub(e, "xPais", XPAIS_BR)
    if end.get("fone"):
        _sub(e, "fone", end["fone"])


def montar_xml_dce(dados: dict) -> str:
    """Monta o XML infDCe (não assinado) a partir de `dados`. Retorna string UTF-8.

    dados = {
      "chave": "<44 díg>", "tp_amb": 1|2,
      "ide": {"c_uf","c_dc","nat_op","serie","n_dc","dh_emi","tp_emis","ver_proc"},
      "emit": {"cpf","x_nome","ender": {x_lgr,nro,x_bairro,c_mun,x_mun,uf,cep,...}},
      "marketplace": {"cnpj","x_nome","site"},
      "dest": {"cpf"|"cnpj","x_nome","ender": {...}},
      "itens": [{"x_prod","ncm","q_com","v_un_com","v_prod"}],
      "transp": {"mod_trans","cnpj_transp"?}  # opcional
    }
    """
    chave = str(dados["chave"])
    ide = dados["ide"]
    emit = dados["emit"]
    mkt = dados["marketplace"]
    dest = dados["dest"]
    itens = dados.get("itens") or []

    dce = etree.Element("DCe", nsmap={None: NS_DCE})
    inf = etree.SubElement(dce, "infDCe", {"versao": VERSAO, "Id": f"DCe{chave}"})

    # ── ide ──────────────────────────────────────────────────────────────
    g_ide = _sub(inf, "ide")
    _sub(g_ide, "cUF", ide["c_uf"])
    _sub(g_ide, "cDC", ide["c_dc"])                       # código numérico (8 díg.) = chave[35:43]
    _sub(g_ide, "natOp", ide.get("nat_op"))
    _sub(g_ide, "mod", MODELO)
    _sub(g_ide, "serie", int(ide["serie"]))
    _sub(g_ide, "nDC", int(ide["n_dc"]))
    _sub(g_ide, "dhEmi", ide["dh_emi"])                   # ISO com offset, ex.: 2026-07-01T01:30:00-03:00
    _sub(g_ide, "tpEmis", ide.get("tp_emis", 1))
    _sub(g_ide, "tpEmit", TP_EMIT_MARKETPLACE)
    _sub(g_ide, "cDV", chave[43])
    _sub(g_ide, "tpAmb", dados["tp_amb"])                 # 1=produção 2=homologação
    _sub(g_ide, "verProc", ide.get("ver_proc", "SistemaDrop-1.0"))

    # ── emit (REMETENTE = vendedor CPF) ──────────────────────────────────
    g_emit = _sub(inf, "emit")
    _sub(g_emit, "CPF", (emit["cpf"] or "").replace(".", "").replace("-", ""))
    _sub(g_emit, "xNome", emit["x_nome"])
    _add_endereco(g_emit, "enderEmit", emit.get("ender") or {})

    # ── Marketplace (ASSINANTE = CNPJ da MIG) ────────────────────────────
    g_mkt = _sub(inf, "Marketplace")
    _sub(g_mkt, "CNPJ", (mkt["cnpj"] or "").replace(".", "").replace("/", "").replace("-", ""))
    _sub(g_mkt, "xNome", mkt["x_nome"])
    if mkt.get("site"):
        _sub(g_mkt, "Site", mkt["site"])

    # ── dest (comprador) ─────────────────────────────────────────────────
    g_dest = _sub(inf, "dest")
    if dest.get("cnpj"):
        _sub(g_dest, "CNPJ", dest["cnpj"].replace(".", "").replace("/", "").replace("-", ""))
    else:
        _sub(g_dest, "CPF", (dest.get("cpf") or "").replace(".", "").replace("-", ""))
    _sub(g_dest, "xNome", dest["x_nome"])
    _add_endereco(g_dest, "enderDest", dest.get("ender") or {})

    # ── det (itens) ──────────────────────────────────────────────────────
    for i, it in enumerate(itens, start=1):
        g_det = _sub(inf, "det")
        g_det.set("nItem", str(i))
        g_prod = _sub(g_det, "prod")
        _sub(g_prod, "xProd", it["x_prod"])
        if it.get("ncm"):
            _sub(g_prod, "NCM", it["ncm"])
        _sub(g_prod, "qCom", _fmt(it.get("q_com", 1), 4))
        _sub(g_prod, "vUnCom", _fmt(it.get("v_un_com", 0), 2))
        _sub(g_prod, "vProd", _fmt(it.get("v_prod", 0), 2))

    # ── total ────────────────────────────────────────────────────────────
    v_dc = sum(Decimal(str(it.get("v_prod", 0) or 0)) for it in itens)
    g_total = _sub(inf, "total")
    _sub(g_total, "vDC", _fmt(v_dc, 2))

    # ── transp (opcional) ────────────────────────────────────────────────
    transp = dados.get("transp") or {}
    if transp:
        g_transp = _sub(inf, "transp")
        _sub(g_transp, "modTrans", transp.get("mod_trans", "0"))  # 0=Correios
        if transp.get("cnpj_transp"):
            _sub(g_transp, "CNPJTransp", transp["cnpj_transp"])

    return etree.tostring(dce, encoding="unicode")

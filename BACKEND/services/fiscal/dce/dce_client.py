"""Cliente SOAP dos webservices da DC-e — Ambiente Nacional (SEFAZ-PR).

Reaproveita o transporte mTLS/SOAP 1.2 do NF-e (`sefaz_client.post_sefaz`,
`extract_cert_pem`, `_build_ssl_context`) — o padrão SEFAZ é o mesmo. Só muda o namespace
do envelope (`.../dce/wsdl/{servico}`) e o elemento `dceDadosMsg`.

URLs (informadas pelo portal SVRS/SEFAZ-PR):
  Produção:    https://dce.fazenda.pr.gov.br/dce/{Servico}
  Homologação: https://homologacao.dce.fazenda.pr.gov.br/dce/{Servico}

⚠️ VALIDAR EM HOMOLOGAÇÃO: o wrapper da mensagem de autorização (enviDCe vs DCe direto, síncrono
vs assíncrono) e os nomes exatos das tags de retorno (protDCe/chDCe) devem ser confirmados contra
o Manual/WSDL rodando em homologação (tpAmb=2). O transporte (mTLS/SOAP) é o do NF-e, já validado.
"""

from __future__ import annotations

import re
from typing import Final

from services.fiscal.sefaz.sefaz_client import SefazResponse, extract_cstat, post_sefaz

DCE_NAMESPACE: Final = "http://www.portalfiscal.inf.br/dce"

DCE_ENDPOINTS: Final[dict[str, dict[str, str]]] = {
    "homologacao": {
        "status": "https://homologacao.dce.fazenda.pr.gov.br/dce/DCeStatusServico",
        "autorizacao": "https://homologacao.dce.fazenda.pr.gov.br/dce/DCeAutorizacao",
        "consulta": "https://homologacao.dce.fazenda.pr.gov.br/dce/DCeConsulta",
        "evento": "https://homologacao.dce.fazenda.pr.gov.br/dce/DCeRecepcaoEvento",
    },
    "producao": {
        "status": "https://dce.fazenda.pr.gov.br/dce/DCeStatusServico",
        "autorizacao": "https://dce.fazenda.pr.gov.br/dce/DCeAutorizacao",
        "consulta": "https://dce.fazenda.pr.gov.br/dce/DCeConsulta",
        "evento": "https://dce.fazenda.pr.gov.br/dce/DCeRecepcaoEvento",
    },
}

# Serviço → nome do serviço no namespace do WSDL (dce/wsdl/{servico}).
_WSDL_SERVICO: Final[dict[str, str]] = {
    "status": "DCeStatusServico",
    "autorizacao": "DCeAutorizacao",
    "consulta": "DCeConsulta",
    "evento": "DCeRecepcaoEvento",
}


def _ambiente_key(tp_amb: int | str) -> str:
    return "producao" if str(tp_amb) == "1" else "homologacao"


def soap_envelope_dce(servico: str, inner_xml: str) -> str:
    """Envelope SOAP 1.2 padrão SEFAZ para a DC-e (elemento dceDadosMsg)."""
    wsdl_ns = f"{DCE_NAMESPACE}/wsdl/{_WSDL_SERVICO[servico]}"
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        f'<dceDadosMsg xmlns="{wsdl_ns}">'
        f"{inner_xml}"
        "</dceDadosMsg>"
        "</soap12:Body>"
        "</soap12:Envelope>"
    )


def _post(servico: str, inner_xml: str, tp_amb: int | str, cert_pem: str, key_pem: str,
          *, verify_ssl: bool = True) -> SefazResponse:
    url = DCE_ENDPOINTS[_ambiente_key(tp_amb)][servico]
    body = soap_envelope_dce(servico, inner_xml)
    return post_sefaz(
        url, body, cert_pem, key_pem, verify_ssl=verify_ssl, user_agent="sistemadrop_dce/1.0"
    )


def status_servico(tp_amb: int | str, cert_pem: str, key_pem: str, *, verify_ssl: bool = True) -> SefazResponse:
    """Consulta status do serviço (consStatServ). Útil p/ smoke da conexão/cert."""
    inner = (
        f'<consStatServ xmlns="{DCE_NAMESPACE}" versao="1.00">'
        f"<tpAmb>{tp_amb}</tpAmb><xServ>STATUS</xServ>"
        "</consStatServ>"
    )
    return _post("status", inner, tp_amb, cert_pem, key_pem, verify_ssl=verify_ssl)


def autorizar(xml_dce_assinado: str, tp_amb: int | str, cert_pem: str, key_pem: str,
              *, id_lote: str = "1", verify_ssl: bool = True) -> SefazResponse:
    """Envia a DC-e assinada para autorização (síncrono).

    ⚠️ Wrapper `enviDCe` (idLote/indSinc/DCe) a confirmar em homologação — pode ser DCe direto.
    """
    inner = (
        f'<enviDCe xmlns="{DCE_NAMESPACE}" versao="1.00">'
        f"<idLote>{id_lote}</idLote><indSinc>1</indSinc>"
        f"{xml_dce_assinado}"
        "</enviDCe>"
    )
    return _post("autorizacao", inner, tp_amb, cert_pem, key_pem, verify_ssl=verify_ssl)


def consultar(chave: str, tp_amb: int | str, cert_pem: str, key_pem: str,
              *, verify_ssl: bool = True) -> SefazResponse:
    """Consulta a situação de uma DC-e pela chave (consSitDCe)."""
    inner = (
        f'<consSitDCe xmlns="{DCE_NAMESPACE}" versao="1.00">'
        f"<tpAmb>{tp_amb}</tpAmb><xServ>CONSULTAR</xServ><chDCe>{chave}</chDCe>"
        "</consSitDCe>"
    )
    return _post("consulta", inner, tp_amb, cert_pem, key_pem, verify_ssl=verify_ssl)


# --- extração de retorno (regex; DC-e usa chDCe no lugar de chNFe) -------------

_RE_NPROT = re.compile(r"<nProt>(\d+)</nProt>")
_RE_CHDCE = re.compile(r"<chDCe>(\d{44})</chDCe>")


def extrair_retorno(soap_xml: str) -> dict:
    """cStat/xMotivo + nProt + chDCe do retorno de autorização."""
    cstat, xmotivo = extract_cstat(soap_xml)
    m_prot = _RE_NPROT.search(soap_xml)
    m_chave = _RE_CHDCE.search(soap_xml)
    return {
        "cstat": cstat,
        "xmotivo": xmotivo,
        "protocolo": m_prot.group(1) if m_prot else None,
        "chave": m_chave.group(1) if m_chave else None,
    }

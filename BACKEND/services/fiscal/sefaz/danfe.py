"""Geração do DANFE PDF a partir do XML NFe autorizado (BrazilFiscalReport).

Espera XML já autorizado: `<nfeProc>` (NFe + protNFe) ou `<NFe>` simples (nesse
caso, junta o `<protNFe>` extraído da resposta SEFAZ antes de renderizar).
"""

from __future__ import annotations

import re
from io import BytesIO

from services.fiscal.sefaz.exceptions import FiscalError

_RE_PROT = re.compile(r"<protNFe[^>]*>.*?</protNFe>", re.DOTALL)


class DanfeError(FiscalError):
    """Falha na geração do DANFE PDF."""


def extrair_protNFe(soap_response_xml: str) -> str | None:
    """Extrai o `<protNFe>...</protNFe>` do envelope SOAP da SEFAZ."""
    m = _RE_PROT.search(soap_response_xml)
    return m.group(0) if m else None


def empacotar_nfeproc(xml_signed: str, protocolo_xml: str | None) -> str:
    """Compõe `<nfeProc>` com `<NFe>` + `<protNFe>` (formato que o DANFE espera)."""
    if "<nfeProc" in xml_signed:
        return xml_signed
    if not protocolo_xml:
        m = _RE_PROT.search(xml_signed)
        if not m:
            raise DanfeError("XML sem <nfeProc> nem <protNFe> — não é possível empacotar.")
        protocolo_xml = m.group(0)
    xml = xml_signed
    if xml.startswith("<?xml"):
        xml = xml.split("?>", 1)[1].lstrip()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f"{xml}{protocolo_xml}</nfeProc>"
    )


def gerar_danfe(xml_signed: str, *, protocolo_xml: str | None = None) -> bytes:
    """Gera os bytes do PDF DANFE a partir do XML autorizado."""
    xml_para_danfe = empacotar_nfeproc(xml_signed, protocolo_xml)
    return _render(xml_para_danfe)


def gerar_danfe_previa(xml_nfe: str) -> bytes:
    """DANFE de PRÉVIA — nota AINDA NÃO autorizada (rascunho / finalizada sem SEFAZ).

    Renderiza o `<NFe>` puro, SEM `<protNFe>`: a própria BrazilFiscalReport, ao não achar
    protocolo, desenha a marca d'água **"SEM VALOR FISCAL"** em todas as vias (idem quando
    tpAmb=2). Não passa por `empacotar_nfeproc` — protocolo sintético seria mentir no papel.
    """
    return _render(xml_nfe)


def _render(xml: str) -> bytes:
    try:
        from brazilfiscalreport.danfe import Danfe

        danfe = Danfe(xml=xml)
        buf = BytesIO()
        danfe.output(buf)
        return buf.getvalue()
    except DanfeError:
        raise
    except Exception as exc:  # noqa: BLE001 — consolida erros da lib
        raise DanfeError(f"falha ao gerar DANFE: {exc}") from exc

"""Consulta NFe na SEFAZ via `nfeConsultaProtocolo` (regra N-6).

Antes de qualquer reenvio, perguntar à SEFAZ se a NFe já foi autorizada — evita
duplicação fiscal. cStats terminais não reenviam; 217 (não consta) reenvia.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from services.fiscal.sefaz.exceptions import ChaveAcessoError, FiscalError
from services.fiscal.sefaz.sefaz_client import (
    NFE_NAMESPACE,
    SEFAZ_NFE_ENDPOINTS_POR_UF,
    SefazResponse,
    extract_cert_pem,
    extract_cstat,
    extract_nprot,
    post_sefaz,
    soap_envelope,
)

CSTATS_TERMINAIS: Final[frozenset[str]] = frozenset(
    {"100", "101", "102", "110", "150", "204", "218", "301", "302"}
)
CSTAT_PERMITE_REENVIO: Final = "217"


@dataclass(frozen=True, slots=True)
class RetornoConsulta:
    chave: str
    cstat: str | None
    motivo: str | None
    nprot: str | None
    response: SefazResponse

    @property
    def terminal(self) -> bool:
        return self.cstat in CSTATS_TERMINAIS

    @property
    def autorizada(self) -> bool:
        return self.cstat == "100"

    @property
    def permite_reenvio(self) -> bool:
        return self.cstat == CSTAT_PERMITE_REENVIO


def _montar_cons_sit_nfe(chave: str, ambiente: Literal["homologacao", "producao"]) -> str:
    tp_amb = "2" if ambiente == "homologacao" else "1"
    return (
        f'<consSitNFe xmlns="{NFE_NAMESPACE}" versao="4.00">'
        f"<tpAmb>{tp_amb}</tpAmb><xServ>CONSULTAR</xServ><chNFe>{chave}</chNFe>"
        "</consSitNFe>"
    )


def consultar_nfe(
    chave: str,
    *,
    ambiente: Literal["homologacao", "producao"],
    uf: str,
    pfx_path: str | Path,
    pfx_password: str,
    timeout: int = 30,
    verify_ssl: bool = True,
    endpoint_url: str | None = None,
    runtime_dir: str | Path | None = None,
) -> RetornoConsulta:
    """Consulta situação da NFe — defende retry contra duplicação fiscal."""
    if len(chave) != 44 or not chave.isdigit():
        raise ChaveAcessoError(f"chave inválida: {chave!r}")
    if endpoint_url is None:
        if uf not in SEFAZ_NFE_ENDPOINTS_POR_UF:
            raise FiscalError(
                f"UF {uf!r} sem endpoint de consulta (suportado: {sorted(SEFAZ_NFE_ENDPOINTS_POR_UF.keys())})"
            )
        endpoint_url = SEFAZ_NFE_ENDPOINTS_POR_UF[uf][ambiente]["consulta_proto"]

    inner = _montar_cons_sit_nfe(chave, ambiente)
    envelope = soap_envelope("NFeConsultaProtocolo4", inner)
    cert_pem, key_pem = extract_cert_pem(pfx_path, pfx_password, runtime_dir=runtime_dir)
    try:
        response = post_sefaz(
            endpoint_url, envelope, cert_pem, key_pem, timeout=timeout, verify_ssl=verify_ssl
        )
    finally:
        Path(cert_pem).unlink(missing_ok=True)
        Path(key_pem).unlink(missing_ok=True)

    cstat_protocolo, motivo_protocolo = _extract_cstat_protocolo(response.body)
    cstat_lote, motivo_lote = extract_cstat(response.body)
    return RetornoConsulta(
        chave=chave,
        cstat=cstat_protocolo or cstat_lote,
        motivo=motivo_protocolo or motivo_lote,
        nprot=extract_nprot(response.body),
        response=response,
    )


def _extract_cstat_protocolo(soap_response_xml: str) -> tuple[str | None, str | None]:
    inicio = soap_response_xml.find("<protNFe")
    if inicio < 0:
        return (None, None)
    fim = soap_response_xml.find("</protNFe>", inicio)
    if fim < 0:
        fim = len(soap_response_xml)
    return extract_cstat(soap_response_xml[inicio:fim])

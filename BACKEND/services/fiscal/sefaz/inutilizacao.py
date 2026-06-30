"""Inutilização de numeração de NF-e (NfeInutilizacao4).

Inutiliza uma faixa de números nunca emitidos (evita gap fiscal). Prazo: até o
10º dia do mês seguinte à quebra de sequência. Justificativa 15–255 chars.
Resposta cStat 102 = inutilização homologada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from lxml import etree

from services.fiscal.sefaz.exceptions import FiscalError
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
from services.fiscal.sefaz.signer import assinar_xml
from services.fiscal.sefaz.xml_builder import codigo_uf

CSTAT_INUTILIZACAO_OK = "102"


@dataclass(frozen=True, slots=True)
class RetornoInutilizacao:
    cstat: str | None
    motivo: str | None
    protocolo: str | None
    xml_assinado: str
    response: SefazResponse

    @property
    def ok(self) -> bool:
        return self.cstat == CSTAT_INUTILIZACAO_OK


def inutilizar_nfe(
    *,
    cnpj: str,
    uf: str,
    ambiente: Literal["homologacao", "producao"],
    ano: int,
    modelo: int,
    serie: int,
    n_ini: int,
    n_fim: int,
    justificativa: str,
    pfx_path: str | Path,
    pfx_password: str,
    timeout: int = 30,
    verify_ssl: bool = True,
    runtime_dir: str | Path | None = None,
) -> RetornoInutilizacao:
    if not (15 <= len(justificativa) <= 255):
        raise FiscalError(f"justificativa deve ter 15-255 chars (recebido: {len(justificativa)})")
    if uf not in SEFAZ_NFE_ENDPOINTS_POR_UF:
        raise FiscalError(f"UF {uf!r} sem endpoint de inutilização")
    c_uf = codigo_uf(uf)
    ano2 = f"{ano % 100:02d}"
    inf_id = f"ID{c_uf}{ano2}{cnpj}{modelo:02d}{serie:03d}{n_ini:09d}{n_fim:09d}"
    tp_amb = "2" if ambiente == "homologacao" else "1"

    nsmap: dict[str | None, str] = {None: NFE_NAMESPACE}
    inut = etree.Element(f"{{{NFE_NAMESPACE}}}inutNFe", nsmap=nsmap)  # type: ignore[arg-type]
    inut.set("versao", "4.00")
    inf = etree.SubElement(inut, f"{{{NFE_NAMESPACE}}}infInut")
    inf.set("Id", inf_id)
    for tag, val in (
        ("tpAmb", tp_amb), ("xServ", "INUTILIZAR"), ("cUF", c_uf), ("ano", ano2),
        ("CNPJ", cnpj), ("mod", f"{modelo:02d}"), ("serie", str(serie)),
        ("nNFIni", str(n_ini)), ("nNFFin", str(n_fim)), ("xJust", justificativa),
    ):
        etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}{tag}").text = val

    xml = f'<?xml version="1.0" encoding="UTF-8"?>{etree.tostring(inut, encoding="unicode")}'
    xml_assinado = assinar_xml(xml, pfx_path=pfx_path, pfx_password=pfx_password, ref_id=inf_id)
    inner = xml_assinado.split("?>", 1)[1].lstrip() if xml_assinado.startswith("<?") else xml_assinado
    envelope = soap_envelope("NFeInutilizacao4", inner)

    endpoint_url = SEFAZ_NFE_ENDPOINTS_POR_UF[uf][ambiente]["inutilizacao"]
    cert_pem, key_pem = extract_cert_pem(pfx_path, pfx_password, runtime_dir=runtime_dir)
    try:
        response = post_sefaz(endpoint_url, envelope, cert_pem, key_pem, timeout=timeout, verify_ssl=verify_ssl)
    finally:
        Path(cert_pem).unlink(missing_ok=True)
        Path(key_pem).unlink(missing_ok=True)

    cstat, motivo = extract_cstat(response.body)
    return RetornoInutilizacao(
        cstat=cstat, motivo=motivo, protocolo=extract_nprot(response.body),
        xml_assinado=xml_assinado, response=response,
    )

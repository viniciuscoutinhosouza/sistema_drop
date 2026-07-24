"""Orquestrador fim a fim da emissão de NFe-55 (pipeline puro, sem banco).

    NotaEmissao + cert A1
        → montar_xml_nfe → assinar_xml → montar_enviNFe → soap_envelope
        → post_sefaz → parse retEnviNFe/protNFe → RetornoEmissao
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from services.fiscal.sefaz.exceptions import SefazError, SefazRejeicao
from services.fiscal.sefaz.models import NotaEmissao
from services.fiscal.sefaz.sefaz_client import (
    NFE_NAMESPACE,
    SEFAZ_NFE_ENDPOINTS_POR_UF,
    SefazResponse,
    extract_cert_pem,
    extract_chnfe,
    extract_cstat,
    extract_nprot,
    post_sefaz,
    soap_envelope,
)
from services.fiscal.sefaz.signer import assinar_xml
from services.fiscal.sefaz.xml_builder import montar_xml_nfe

_ENDPOINTS_POR_UF: Final[dict[str, dict[str, dict[str, str]]]] = SEFAZ_NFE_ENDPOINTS_POR_UF


@dataclass(frozen=True, slots=True)
class RetornoEmissao:
    """Resultado de uma tentativa de emissão (tudo que a persistência precisa)."""

    chave: str
    xml_unsigned: str
    xml_signed: str
    envelope_soap: str
    response: SefazResponse
    cstat_lote: str | None
    motivo_lote: str | None
    cstat_protocolo: str | None
    motivo_protocolo: str | None
    nprot: str | None

    @property
    def cstat_final(self) -> str | None:
        return self.cstat_protocolo or self.cstat_lote

    @property
    def motivo_final(self) -> str | None:
        return self.motivo_protocolo or self.motivo_lote

    @property
    def autorizada(self) -> bool:
        # 100 = autorizada; 150 = autorizada "fora de prazo" (dhEmi fora da janela) — TAMBÉM é
        # autorização válida. Tratar 150 como rejeitada marcaria localmente como 'rejected' uma
        # nota que a SEFAZ tem como autorizada → duplicidade (204) na retransmissão.
        return self.cstat_final in ("100", "150")


def montar_enviNFe(xml_signed: str, id_lote: int | str, indSinc: Literal[0, 1] = 1) -> str:
    nfe_inner = xml_signed
    if nfe_inner.startswith("<?"):
        nfe_inner = nfe_inner.split("?>", 1)[1]
    nfe_inner = nfe_inner.lstrip()
    return (
        f'<enviNFe xmlns="{NFE_NAMESPACE}" versao="4.00">'
        f"<idLote>{id_lote}</idLote>"
        f"<indSinc>{indSinc}</indSinc>"
        f"{nfe_inner}"
        "</enviNFe>"
    )


def resolver_endpoint_autorizacao(uf: str, ambiente: Literal["homologacao", "producao"]) -> str:
    if uf not in _ENDPOINTS_POR_UF:
        raise SefazError(
            f"UF {uf!r} sem endpoint mapeado (suportado: {sorted(_ENDPOINTS_POR_UF.keys())})"
        )
    return _ENDPOINTS_POR_UF[uf][ambiente]["autorizacao"]


def emitir_nfe(
    nota: NotaEmissao,
    *,
    pfx_path: str | Path,
    pfx_password: str,
    timeout: int = 60,
    verify_ssl: bool = True,
    endpoint_url: str | None = None,
    runtime_dir: str | Path | None = None,
    raise_on_rejeicao: bool = False,
) -> RetornoEmissao:
    """Pipeline de emissão fim a fim (sem banco, sem efeito fora da SEFAZ)."""
    xml_unsigned = montar_xml_nfe(nota)
    xml_signed = assinar_xml(
        xml_unsigned, pfx_path=pfx_path, pfx_password=pfx_password, ref_id=f"NFe{nota.chave}"
    )
    enviNFe = montar_enviNFe(xml_signed, id_lote=nota.numero, indSinc=1)
    envelope = soap_envelope("NFeAutorizacao4", enviNFe)

    url = endpoint_url or resolver_endpoint_autorizacao(nota.emitente.endereco.uf, nota.ambiente)
    cert_pem, key_pem = extract_cert_pem(pfx_path, pfx_password, runtime_dir=runtime_dir)
    try:
        response = post_sefaz(url, envelope, cert_pem, key_pem, timeout=timeout, verify_ssl=verify_ssl)
    finally:
        Path(cert_pem).unlink(missing_ok=True)
        Path(key_pem).unlink(missing_ok=True)

    cstat_lote, motivo_lote = extract_cstat(response.body)
    cstat_protocolo, motivo_protocolo = _extract_cstat_protocolo(response.body)
    nprot = extract_nprot(response.body)
    _ = extract_chnfe(response.body)  # validação cruzada opcional (não bloqueia)

    retorno = RetornoEmissao(
        chave=nota.chave,
        xml_unsigned=xml_unsigned,
        xml_signed=xml_signed,
        envelope_soap=envelope,
        response=response,
        cstat_lote=cstat_lote,
        motivo_lote=motivo_lote,
        cstat_protocolo=cstat_protocolo,
        motivo_protocolo=motivo_protocolo,
        nprot=nprot,
    )
    if raise_on_rejeicao and not retorno.autorizada:
        raise SefazRejeicao(
            cstat=retorno.cstat_final or "?", x_motivo=retorno.motivo_final or "?", raw=response.body
        )
    return retorno


def _extract_cstat_protocolo(soap_response_xml: str) -> tuple[str | None, str | None]:
    """cStat/xMotivo do `<infProt>` (NFe individual), distinto do cStat do lote."""
    inicio = soap_response_xml.find("<protNFe")
    if inicio < 0:
        return (None, None)
    fim = soap_response_xml.find("</protNFe>", inicio)
    if fim < 0:
        fim = len(soap_response_xml)
    return extract_cstat(soap_response_xml[inicio:fim])

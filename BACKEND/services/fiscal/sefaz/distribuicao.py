"""Distribuição de DF-e (NFeDistribuicaoDFe) — Ambiente Nacional.

Puxa as NF-e/eventos emitidos CONTRA o CNPJ (entrada), substituindo o pull que
vinha do Focus. Consulta por `distNSU` (lote a partir do último NSU processado).

Envelope (confirmado na NT 2014.002 / MOC):
    soap12:Envelope > soap12:Body > nfeDistDFeInteresse(xmlns=wsdl/NFeDistribuicaoDFe)
      > nfeDadosMsg > distDFeInt(xmlns=nfe, versao=1.01)
        > tpAmb, cUFAutor, CNPJ, distNSU>ultNSU

Resposta retDistDFeInt: cStat (138=docs encontrados, 137=nenhum documento,
656=consumo indevido/rate-limit), ultNSU, maxNSU, loteDistDFeInt>docZip
(NSU + schema; conteúdo = base64(gzip(xml))).

Rate-limit: quando ultNSU == maxNSU (sem novos), NÃO reconsultar antes de ~1h.
cStat 656 = consumo indevido → aguardar (não é erro terminal).
"""

from __future__ import annotations

import base64
import gzip
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from lxml import etree

from services.fiscal.sefaz.exceptions import FiscalError
from services.fiscal.sefaz.sefaz_client import (
    NFE_NAMESPACE,
    SEFAZ_DFE_AN,
    SefazResponse,
    extract_cert_pem,
    post_sefaz,
)

_WSDL_NS = f"{NFE_NAMESPACE}/wsdl/NFeDistribuicaoDFe"
CSTAT_DOCS_ENCONTRADOS: Final = "138"
CSTAT_NENHUM_DOC: Final = "137"
CSTAT_CONSUMO_INDEVIDO: Final = "656"

# Teto de descompressão por docZip (anti zip-bomb). Uma NF-e/evento real cabe folgado.
_MAX_DOC_BYTES: Final = 8 * 1024 * 1024
# Parser endurecido: docZip é conteúdo de TERCEIROS (emitentes contra o CNPJ) —
# sem resolução de entidades (billion laughs), sem rede, sem huge_tree.
_SAFE_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


def _gunzip_capped(raw_b64: str) -> str | None:
    """base64 → gzip(stream com teto) → utf-8. None se exceder o teto ou falhar."""
    import io

    try:
        comp = base64.b64decode(raw_b64)
        out = bytearray()
        with gzip.GzipFile(fileobj=io.BytesIO(comp)) as gz:
            while True:
                chunk = gz.read(65536)
                if not chunk:
                    break
                out += chunk
                if len(out) > _MAX_DOC_BYTES:
                    return None
        return out.decode("utf-8")
    except (ValueError, OSError):
        return None


@dataclass(frozen=True, slots=True)
class DocDFe:
    nsu: str
    schema: str
    xml: str  # já descomprimido (gunzip do base64)

    @property
    def is_nfe_completa(self) -> bool:
        return self.schema.startswith(("procNFe", "nfeProc"))

    @property
    def is_resumo_nfe(self) -> bool:
        return self.schema.startswith("resNFe")

    @property
    def is_evento(self) -> bool:
        return self.schema.startswith(("resEvento", "procEventoNFe"))


@dataclass(frozen=True, slots=True)
class RetornoDistribuicao:
    cstat: str | None
    motivo: str | None
    ult_nsu: str | None
    max_nsu: str | None
    docs: tuple[DocDFe, ...] = field(default_factory=tuple)
    response: SefazResponse | None = None

    @property
    def tem_mais(self) -> bool:
        """True se ainda há NSU a buscar (ultNSU < maxNSU)."""
        try:
            return int(self.ult_nsu or 0) < int(self.max_nsu or 0)
        except (TypeError, ValueError):
            return False


def _build_dist_dfe_int(cnpj: str, c_uf: str, ambiente: str, ult_nsu: str) -> str:
    tp_amb = "2" if ambiente == "homologacao" else "1"
    nsu = f"{int(ult_nsu or 0):015d}"
    return (
        f'<distDFeInt xmlns="{NFE_NAMESPACE}" versao="1.01">'
        f"<tpAmb>{tp_amb}</tpAmb><cUFAutor>{c_uf}</cUFAutor><CNPJ>{cnpj}</CNPJ>"
        f"<distNSU><ultNSU>{nsu}</ultNSU></distNSU>"
        "</distDFeInt>"
    )


def _envelope_distribuicao(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        f'<nfeDistDFeInteresse xmlns="{_WSDL_NS}">'
        f"<nfeDadosMsg>{inner}</nfeDadosMsg>"
        "</nfeDistDFeInteresse>"
        "</soap12:Body></soap12:Envelope>"
    )


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _findtext(root: etree._Element, name: str) -> str | None:
    for el in root.iter():
        if _local(el.tag) == name:
            return (el.text or "").strip() or None
    return None


def _parse_ret(body: str) -> RetornoDistribuicao:
    try:
        root = etree.fromstring(body.encode("utf-8"), _SAFE_PARSER)
    except etree.XMLSyntaxError as exc:
        raise FiscalError(f"resposta DFe malformada: {exc}") from exc

    cstat = _findtext(root, "cStat")
    motivo = _findtext(root, "xMotivo")
    ult = _findtext(root, "ultNSU")
    mx = _findtext(root, "maxNSU")

    docs: list[DocDFe] = []
    for el in root.iter():
        if _local(el.tag) != "docZip":
            continue
        nsu = el.get("NSU") or ""
        schema = el.get("schema") or ""
        raw = (el.text or "").strip()
        xml = _gunzip_capped(raw)  # teto anti zip-bomb
        if xml is None:
            continue
        docs.append(DocDFe(nsu=nsu, schema=schema, xml=xml))

    return RetornoDistribuicao(
        cstat=cstat, motivo=motivo, ult_nsu=ult, max_nsu=mx, docs=tuple(docs)
    )


def consultar_dfe(
    *,
    cnpj: str,
    c_uf: str,
    ambiente: Literal["homologacao", "producao"],
    ult_nsu: str,
    pfx_path: str | Path,
    pfx_password: str,
    timeout: int = 60,
    verify_ssl: bool = True,
    endpoint_url: str | None = None,
    runtime_dir: str | Path | None = None,
) -> RetornoDistribuicao:
    """Uma chamada de distribuição a partir de `ult_nsu`. SefazError em falha de rede."""
    url = endpoint_url or SEFAZ_DFE_AN[ambiente]
    inner = _build_dist_dfe_int(cnpj, c_uf, ambiente, ult_nsu)
    envelope = _envelope_distribuicao(inner)
    cert_pem, key_pem = extract_cert_pem(pfx_path, pfx_password, runtime_dir=runtime_dir)
    try:
        response = post_sefaz(url, envelope, cert_pem, key_pem, timeout=timeout, verify_ssl=verify_ssl)
    finally:
        Path(cert_pem).unlink(missing_ok=True)
        Path(key_pem).unlink(missing_ok=True)
    ret = _parse_ret(response.body)
    return RetornoDistribuicao(
        cstat=ret.cstat, motivo=ret.motivo, ult_nsu=ret.ult_nsu, max_nsu=ret.max_nsu,
        docs=ret.docs, response=response,
    )

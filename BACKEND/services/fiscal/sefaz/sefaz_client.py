"""Cliente SOAP para os webservices da SEFAZ (NFe 4.0).

Regras validadas em produção (cStat=100) e preservadas:
1. **SOAP 1.2** (`application/soap+xml`), **sem** header `SOAPAction` separado
   (SVRS reseta a conexão) — quando preciso, vai no Content-Type.
2. **TLS legado** — `SECLEVEL=1` + `OP_LEGACY_SERVER_CONNECT` + min TLSv1.2.
3. **urllib3 direto** (não `requests`, que sobrescreve o SSLContext).
4. **RJ via SVRS**, **SP via WS próprio**.
5. **cabundle ICP-Brasil** em produção (`verify_ssl=True`).
"""

from __future__ import annotations

import contextlib
import re
import ssl
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal
from urllib.parse import urlparse

import urllib3
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

from services.fiscal.sefaz.exceptions import SefazError

NFE_NAMESPACE: Final = "http://www.portalfiscal.inf.br/nfe"

# Distribuição de DFe — Ambiente Nacional (não por UF).
SEFAZ_DFE_AN: Final[dict[str, str]] = {
    "homologacao": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    "producao": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}

# Recepção de Evento — Ambiente Nacional (manifestação do destinatário, cOrgao=91).
SEFAZ_EVENTO_AN: Final[dict[str, str]] = {
    "homologacao": "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
    "producao": "https://www1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx",
}

SEFAZ_RJ_NFE_ENDPOINTS: Final[dict[str, dict[str, str]]] = {
    "homologacao": {
        "status": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "autorizacao": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "ret_autorizacao": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta_proto": "https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "recepcao_evento": "https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
        "inutilizacao": "https://nfe-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
    },
    "producao": {
        "status": "https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "ret_autorizacao": "https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx",
        "consulta_proto": "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "recepcao_evento": "https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
        "inutilizacao": "https://nfe.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
    },
}

SEFAZ_SP_NFE_ENDPOINTS: Final[dict[str, dict[str, str]]] = {
    "homologacao": {
        "status": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
        "autorizacao": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        "ret_autorizacao": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
        "consulta_proto": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
        "recepcao_evento": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
        "inutilizacao": "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx",
    },
    "producao": {
        "status": "https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
        "autorizacao": "https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        "ret_autorizacao": "https://nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx",
        "consulta_proto": "https://nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx",
        "recepcao_evento": "https://nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
        "inutilizacao": "https://nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx",
    },
}

SEFAZ_NFE_ENDPOINTS_POR_UF: Final[dict[str, dict[str, dict[str, str]]]] = {
    "RJ": SEFAZ_RJ_NFE_ENDPOINTS,
    "SP": SEFAZ_SP_NFE_ENDPOINTS,
}


@dataclass(frozen=True, slots=True)
class SefazResponse:
    """Resposta crua da SEFAZ (envelope SOAP). Erro de rede/TLS vira SefazError."""

    status_code: int
    body: str
    elapsed_ms: int

    @property
    def is_http_ok(self) -> bool:
        return 200 <= self.status_code < 300


def extract_cert_pem(
    pfx_path: str | Path, password: str, *, runtime_dir: str | Path | None = None
) -> tuple[str, str]:
    """Lê PFX, escreve cert+chain e key em PEM temporário e retorna os paths.

    `SSLContext.load_cert_chain` exige arquivos em disco. Os PEM são gravados em
    `runtime_dir` (diretório restrito do app, chmod 700) se informado — evita o
    `/tmp` compartilhado — senão em `tempfile.gettempdir()`. O caller (emitter)
    apaga via try/finally.
    """
    pfx_path = Path(pfx_path)
    if not pfx_path.exists():
        raise SefazError(f"cert .pfx não encontrado: {pfx_path}")
    try:
        pfx_bytes = pfx_path.read_bytes()
        key, cert, chain = pkcs12.load_key_and_certificates(pfx_bytes, password.encode())
    except (ValueError, OSError) as exc:
        raise SefazError(f"falha ao abrir cert {pfx_path}: {exc}") from exc
    if key is None or cert is None:
        raise SefazError(f"cert {pfx_path} sem key ou cert")

    tmp_dir: str | None = None
    if runtime_dir is not None:
        rd = Path(runtime_dir)
        rd.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            import os

            os.chmod(rd, 0o700)
        tmp_dir = str(rd)

    cert_f = tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode="wb", dir=tmp_dir)  # noqa: SIM115
    try:
        cert_f.write(cert.public_bytes(Encoding.PEM))
        if chain:
            for c in chain:
                cert_f.write(c.public_bytes(Encoding.PEM))
    finally:
        cert_f.close()

    key_f = tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode="wb", dir=tmp_dir)  # noqa: SIM115
    try:
        key_f.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    finally:
        key_f.close()

    return cert_f.name, key_f.name


def soap_envelope(servico: str, inner_xml: str) -> str:
    """Envelope SOAP 1.2 padrão SEFAZ NFe 4.0 (sem SOAPAction em header)."""
    wsdl_ns = f"{NFE_NAMESPACE}/wsdl/{servico}"
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        f'<nfeDadosMsg xmlns="{wsdl_ns}">'
        f"{inner_xml}"
        "</nfeDadosMsg>"
        "</soap12:Body>"
        "</soap12:Envelope>"
    )


def _build_ssl_context(cert_pem: str, key_pem: str, verify_ssl: bool) -> ssl.SSLContext:
    """SSLContext compatível com SEFAZ/SVRS (TLS legado + mTLS)."""
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    with contextlib.suppress(ssl.SSLError):
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=cert_pem, keyfile=key_pem)
    return ctx


def post_sefaz(
    url: str,
    soap_body: str,
    cert_pem: str,
    key_pem: str,
    *,
    timeout: int = 60,
    verify_ssl: bool = True,
    soap_action: str | None = None,
    user_agent: str = "sistemadrop_nfe/1.0",
) -> SefazResponse:
    """POST SOAP 1.2 com mTLS via urllib3. SefazError em falha de transporte."""
    content_type = "application/soap+xml; charset=utf-8"
    if soap_action:
        content_type += f'; action="{soap_action}"'
    headers = {
        "Content-Type": content_type,
        "Accept": "application/soap+xml, application/xml, */*",
        "User-Agent": user_agent,
    }
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    ctx = _build_ssl_context(cert_pem, key_pem, verify_ssl)
    parsed = urlparse(url)
    if not parsed.hostname:
        raise SefazError(f"URL SEFAZ inválida: {url!r}")
    assert_hostname: str | Literal[False] | None = None if verify_ssl else False
    path = parsed.path + (("?" + parsed.query) if parsed.query else "")

    # SVRS reseta a conexão intermitentemente (~20-30% com payload > 6KB).
    # 4 tentativas com backoff curto (1s, 2s, 4s). Reenvio é seguro: mesmo idLote
    # não duplica (SVRS responde cStat=204).
    max_attempts = 4
    last_exc: Exception | None = None
    t0 = time.time()
    for attempt in range(max_attempts):
        try:
            pool = urllib3.HTTPSConnectionPool(
                host=parsed.hostname,
                port=parsed.port or 443,
                ssl_context=ctx,
                cert_reqs="CERT_REQUIRED" if verify_ssl else "CERT_NONE",
                assert_hostname=assert_hostname,
                timeout=urllib3.Timeout(connect=10, read=timeout),
                retries=False,
            )
            r = pool.request("POST", path, body=soap_body.encode("utf-8"), headers=headers)
            return SefazResponse(
                status_code=r.status,
                body=r.data.decode("utf-8", errors="replace"),
                elapsed_ms=int((time.time() - t0) * 1000),
            )
        except urllib3.exceptions.SSLError as exc:
            raise SefazError(f"TLS handshake falhou contra {parsed.hostname}: {exc}") from exc
        except (urllib3.exceptions.TimeoutError, urllib3.exceptions.HTTPError) as exc:
            last_exc = exc
        if attempt < max_attempts - 1:
            time.sleep(2 ** attempt)

    raise SefazError(
        f"falha HTTP contra {parsed.hostname} após {max_attempts} tentativas: {last_exc}"
    ) from last_exc


# --- extração leve (regex — evita import lxml aqui) ---------------------------

_RE_CSTAT = re.compile(r"<cStat>(\d+)</cStat>")
_RE_XMOTIVO = re.compile(r"<xMotivo>([^<]+)</xMotivo>")
_RE_NPROT = re.compile(r"<nProt>(\d+)</nProt>")
_RE_CHNFE = re.compile(r"<chNFe>(\d{44})</chNFe>")


def extract_cstat(soap_response_xml: str) -> tuple[str | None, str | None]:
    m_cstat = _RE_CSTAT.search(soap_response_xml)
    m_motivo = _RE_XMOTIVO.search(soap_response_xml)
    return (m_cstat.group(1) if m_cstat else None, m_motivo.group(1) if m_motivo else None)


def extract_nprot(soap_response_xml: str) -> str | None:
    m = _RE_NPROT.search(soap_response_xml)
    return m.group(1) if m else None


def extract_chnfe(soap_response_xml: str) -> str | None:
    m = _RE_CHNFE.search(soap_response_xml)
    return m.group(1) if m else None

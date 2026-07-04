"""Assinatura XMLDSig da DC-e — igual à NF-e, MAS sem prefixo `ds:`.

A SEFAZ-PR (DC-e) rejeita a assinatura com prefixo `ds:` (cStat 587 "Usar somente o namespace
padrão da DCe"). A `Signature` deve usar o namespace xmldsig como PADRÃO (sem prefixo). Só isso
difere do signer de NF-e; o resto (SHA-1, 1 cert, reference_uri no Id) é idêntico.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from signxml import methods
from signxml.algorithms import CanonicalizationMethod, DigestAlgorithm, SignatureMethod
from signxml.signer import XMLSigner

from services.fiscal.sefaz.exceptions import SignError

_XMLDSIG = "http://www.w3.org/2000/09/xmldsig#"


class _DCeXMLSigner(XMLSigner):
    """Permite SHA-1 (norma) e emite a Signature SEM prefixo (namespace padrão)."""

    namespaces = {None: _XMLDSIG}  # sem prefixo 'ds:' → exigido pela SEFAZ-PR (cStat 587)

    def check_deprecated_methods(self) -> None:  # type: ignore[override]
        return


def assinar_xml_dce(xml: str, pfx_path: str | Path, pfx_password: str, ref_id: str) -> str:
    """Assina o XML da DC-e com cert A1, sem prefixo na Signature. Retorna string XML assinada."""
    pfx_path = Path(pfx_path)
    if not pfx_path.exists():
        raise SignError(f"cert .pfx não encontrado: {pfx_path}")
    try:
        key, cert, _chain = pkcs12.load_key_and_certificates(
            pfx_path.read_bytes(), pfx_password.encode()
        )
    except (ValueError, OSError) as exc:
        raise SignError(f"falha ao abrir cert {pfx_path}: {exc}") from exc
    if key is None or cert is None:
        raise SignError(f"cert {pfx_path} não contém key ou cert")
    if not isinstance(key, RSAPrivateKey):
        raise SignError(f"cert {pfx_path} tem key {type(key).__name__}, esperado RSAPrivateKey")

    try:
        root = etree.fromstring(xml.encode("utf-8"), etree.XMLParser(remove_blank_text=False))
    except etree.XMLSyntaxError as exc:
        raise SignError(f"XML mal formado: {exc}") from exc

    try:
        signer = _DCeXMLSigner(
            method=methods.enveloped,
            signature_algorithm=SignatureMethod.RSA_SHA1,
            digest_algorithm=DigestAlgorithm.SHA1,
            c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
        )
        # O __init__ do signxml seta self.namespaces={'ds':...}; força SEM prefixo na instância.
        signer.namespaces = {None: _XMLDSIG}
        signed = signer.sign(root, key=key, cert=[cert], reference_uri=ref_id)
    except Exception as exc:  # noqa: BLE001
        raise SignError(f"falha ao assinar DC-e: {exc}") from exc

    return '<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(signed, encoding="unicode")

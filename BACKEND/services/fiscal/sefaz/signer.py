"""Assinatura XMLDSig do XML da NFe usando cert A1 (.pfx).

Regras validadas em produção (cStat=100) e preservadas:
1. **SHA-1** obrigatório (norma SEFAZ NFe 4.0) — `signxml` bloqueia SHA-1 por
   default; subclassamos `XMLSigner` para pular a checagem.
2. **Lista de 1 cert** no `cert=` — SEFAZ rejeita (cStat=225) se a cadeia for incluída.
3. **`reference_uri=Id`** apontando para o `Id` do `infNFe`/`infEvento`.
4. **PKCS#12** via `cryptography.pkcs12`.
5. **Assinatura SEM prefixo `ds:`** (namespace default) — o `signxml` 5.x passou a
   emitir `<ds:Signature>`, mas a SEFAZ valida a assinatura no formato canônico com o
   namespace xmldsig **default** (regra E01 → cStat 290 "Certificado Assinatura inválido"
   quando o `X509Certificate` vem prefixado). Setar `namespaces = {None: ds}` faz o
   `signxml` gerar sem prefixo. Mesma lição do ADR-0017 (DC-e "assinatura sem prefixo ds:").
6. **base64 em linha única** no `X509Certificate`/`SignatureValue` — o `signxml` quebra o
   base64 em 64 colunas; validadores SEFAZ podem recusar. Como `KeyInfo` e `SignatureValue`
   **não** integram o `SignedInfo` assinado, remover as quebras depois de assinar é seguro
   e não invalida a assinatura.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from signxml import methods
from signxml import namespaces as _sx_namespaces
from signxml.algorithms import CanonicalizationMethod, DigestAlgorithm, SignatureMethod
from signxml.signer import XMLSigner

from services.fiscal.sefaz.exceptions import SignError

_NS_DS = _sx_namespaces.ds  # "http://www.w3.org/2000/09/xmldsig#"
# Elementos cujo base64 pode ser recolapsado em linha única SEM invalidar a assinatura
# (ficam FORA do SignedInfo assinado). NÃO incluir DigestValue (está dentro do SignedInfo).
_ONE_LINE_TAGS = ("X509Certificate", "SignatureValue")


class _NFeXMLSigner(XMLSigner):
    """`XMLSigner` que permite SHA-1 (exigido pela norma SEFAZ NFe 4.0)."""

    def check_deprecated_methods(self) -> None:  # type: ignore[override]
        return


def assinar_xml(xml: str, pfx_path: str | Path, pfx_password: str, ref_id: str) -> str:
    """Assina XML (NFe ou evento) com cert A1 e retorna a string XML assinada.

    Args:
        xml: XML não assinado (com `<infNFe Id="NFe<chave>">` ou `<infEvento Id=...>`).
        pfx_path: caminho do `.pfx`.
        pfx_password: senha do `.pfx`.
        ref_id: valor do atributo `Id` referenciado pela assinatura.
    """
    pfx_path = Path(pfx_path)
    if not pfx_path.exists():
        raise SignError(f"cert .pfx não encontrado: {pfx_path}")

    try:
        pfx_bytes = pfx_path.read_bytes()
        key, cert, _chain = pkcs12.load_key_and_certificates(pfx_bytes, pfx_password.encode())
    except (ValueError, OSError) as exc:
        raise SignError(f"falha ao abrir cert {pfx_path}: {exc}") from exc

    if key is None or cert is None:
        raise SignError(f"cert {pfx_path} não contém key ou cert")
    if not isinstance(key, RSAPrivateKey):
        raise SignError(f"cert {pfx_path} tem key {type(key).__name__}, esperado RSAPrivateKey")

    try:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(xml.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        raise SignError(f"XML mal formado: {exc}") from exc

    try:
        signer = _NFeXMLSigner(
            method=methods.enveloped,
            signature_algorithm=SignatureMethod.RSA_SHA1,
            digest_algorithm=DigestAlgorithm.SHA1,
            c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
        )
        # Regra 5: assina no namespace xmldsig DEFAULT (sem prefixo `ds:`).
        signer.namespaces = {None: _NS_DS}
        signed = signer.sign(root, key=key, cert=[cert], reference_uri=ref_id)
    except Exception as exc:  # noqa: BLE001 — signxml levanta várias; consolidamos
        raise SignError(f"falha ao assinar XML: {exc}") from exc

    # Regra 6: recolapsa o base64 (fora do SignedInfo) em linha única.
    for tag in _ONE_LINE_TAGS:
        for el in signed.iter(f"{{{_NS_DS}}}{tag}"):
            if el.text:
                el.text = "".join(el.text.split())

    return '<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(signed, encoding="unicode")

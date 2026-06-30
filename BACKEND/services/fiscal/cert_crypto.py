"""Cifragem da senha do certificado A1 (.pfx) para repouso no banco.

Decisão do dono: a senha do certificado de cada CMIG é arquivada CIFRADA no BD
(coluna `cmig_fiscal_config.cert_pass_encrypted`), nunca em claro. Usa Fernet
(AES-128-CBC + HMAC, da lib `cryptography`) com uma master key única do servidor
em `settings.NFE_CERT_MASTER_KEY` (env var, nunca commitada).

A master key configurada pode ser qualquer string aleatória — derivamos a chave
Fernet (32 bytes url-safe base64) por SHA-256, então o operador não precisa gerar
uma chave no formato exato do Fernet.

⚠️ Perder a master key inutiliza todas as senhas cifradas — fazer backup seguro.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


class CertCryptoError(Exception):
    """Falha de configuração/uso da cifragem da senha do certificado."""


def _derive_key(master: str) -> bytes:
    """Deriva uma chave Fernet (32 bytes url-safe base64) de uma master arbitrária."""
    digest = hashlib.sha256(master.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet(master: str | None = None) -> Fernet:
    key = master if master is not None else (get_settings().NFE_CERT_MASTER_KEY or "")
    if not key:
        raise CertCryptoError(
            "NFE_CERT_MASTER_KEY não configurada — impossível cifrar/decifrar a senha do certificado."
        )
    return Fernet(_derive_key(key))


def encrypt(plaintext: str, *, master: str | None = None) -> str:
    """Cifra a senha em claro → token (str) para gravar em cert_pass_encrypted."""
    if plaintext is None:
        raise CertCryptoError("Senha vazia não pode ser cifrada.")
    return _fernet(master).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str, *, master: str | None = None) -> str:
    """Decifra o token do banco → senha em claro (uso efêmero no handshake mTLS)."""
    if not token:
        raise CertCryptoError("Token cifrado vazio.")
    try:
        return _fernet(master).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:  # master key trocada/errada ou dado corrompido
        raise CertCryptoError(
            "Não foi possível decifrar a senha do certificado (master key incorreta?)."
        ) from e

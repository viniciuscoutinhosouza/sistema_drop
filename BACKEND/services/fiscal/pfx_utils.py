"""Validação de certificado A1 (.pfx) — compartilhada entre uploads (por-CMIG e central)."""

from __future__ import annotations


def validate_pfx(pfx_bytes: bytes, password: str):
    """Valida o .pfx + senha; retorna (expires_at, subject) ou (None, None) se inválido."""
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12

        _, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, password.encode("utf-8"))
        if cert is None:
            return None, None
        subject = cert.subject.rfc4514_string()
        expires = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
        return expires.replace(tzinfo=None) if expires.tzinfo else expires, subject
    except Exception:
        return None, None

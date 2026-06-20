"""Shared secrets access.

Usa Windows Credential Manager via `keyring` para armazenar API keys
localmente. Evita commitar chaves em arquivos junto ao código.

Naming:
- service: SistemaDrop
- username: <KEY_NAME>

Exemplo: SistemaDrop / CAPSOLVER_API_KEY
"""

from __future__ import annotations

from typing import Optional


SERVICE_NAME = "SistemaDrop"  # nome do projeto


def get_secret(name: str) -> Optional[str]:
    try:
        import keyring  # type: ignore
        v = keyring.get_password(SERVICE_NAME, str(name))
        return str(v).strip() if v else None
    except Exception:
        return None


def set_secret(name: str, value: str) -> bool:
    try:
        import keyring  # type: ignore
        keyring.set_password(SERVICE_NAME, str(name), str(value))
        return True
    except Exception:
        return False

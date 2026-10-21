"""Cifragem genérica de segredos em repouso (Fernet, master key única do servidor).

Reexporta o util do fiscal (`services/fiscal/cert_crypto`) para uso fora do domínio fiscal —
ex.: credenciais de gateway de pagamento (API Key do ASAAS por Galpão). Mesma master key
(`NFE_CERT_MASTER_KEY`), então perdê-la inutiliza TODOS os segredos cifrados (cert fiscal + banco).
"""

from services.fiscal.cert_crypto import CertCryptoError as CryptoError
from services.fiscal.cert_crypto import decrypt, encrypt

__all__ = ["encrypt", "decrypt", "CryptoError"]

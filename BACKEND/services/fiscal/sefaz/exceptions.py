"""Hierarquia de exceções do domínio fiscal (SEFAZ direto).

`FiscalError` é a raiz. A separação importante para a transmissão:
- `SefazError` (rede/TLS/timeout/SEFAZ fora) → transitório, pode reenviar (com N-6 antes).
- `FiscalError`/`SefazRejeicao` (XML inválido, UF não mapeada, rejeição de validação) →
  terminal, não adianta reenviar.
"""

from __future__ import annotations


class FiscalError(Exception):
    """Erro raiz do domínio fiscal."""


class ChaveAcessoError(FiscalError):
    """Falha ao montar ou validar a chave de acesso."""


class XmlBuildError(FiscalError):
    """Falha ao montar XML — dados inconsistentes ou faltando."""


class SignError(FiscalError):
    """Falha ao assinar XML — cert inválido, senha errada, etc."""


class CertError(FiscalError):
    """Falha de configuração/carregamento do certificado A1."""


class SefazError(FiscalError):
    """Falha de comunicação com a SEFAZ — TLS, timeout, HTTP 5xx (transitório)."""


class SefazRejeicao(FiscalError):
    """SEFAZ recebeu, processou e rejeitou — guarda cStat + xMotivo (terminal)."""

    def __init__(self, cstat: str, x_motivo: str, raw: str = "") -> None:
        super().__init__(f"SEFAZ rejeitou: cStat={cstat} — {x_motivo}")
        self.cstat = cstat
        self.x_motivo = x_motivo
        self.raw = raw

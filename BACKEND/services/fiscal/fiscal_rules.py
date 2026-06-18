"""Regras fiscais compartilhadas entre routers e services."""
import unicodedata


def is_simbolica(natureza: str | None) -> bool:
    """NF-e de movimentação SIMBÓLICA (ex.: 'Retorno Simbólico de Depósito') —
    documento puramente fiscal que NÃO movimenta estoque físico: nem LOCAL nem FULL.
    Só remessa e retorno REAL movimentam estoque (regra de negócio).

    Detecta 'simbolic' na natureza da operação, sem depender de acento/caixa.
    """
    n = unicodedata.normalize("NFKD", natureza or "").encode("ascii", "ignore").decode().lower()
    return "simbolic" in n

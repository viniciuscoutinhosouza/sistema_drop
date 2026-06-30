"""Chave de acesso da NFe — 44 dígitos com DV módulo 11.

A chave concatena:
    cUF (2) + AAMM (4) + CNPJ (14) + mod (2) + serie (3) + nNF (9)
    + tpEmis (1) + cNF (8) + cDV (1)

O cDV é módulo 11 sobre os 43 primeiros dígitos, pesos cíclicos 2..9 da direita
para a esquerda. Ref.: MOC NFe 4.0, "Algoritmo do Dígito Verificador da Chave".
"""

from __future__ import annotations

import re
import secrets

from services.fiscal.sefaz.exceptions import ChaveAcessoError

_PESOS_DV = (2, 3, 4, 5, 6, 7, 8, 9)


def calc_dv_chave(chave43: str) -> str:
    """DV (1 dígito) sobre os 43 primeiros dígitos da chave."""
    if len(chave43) != 43 or not chave43.isdigit():
        raise ChaveAcessoError(f"calc_dv_chave espera 43 dígitos, recebeu {len(chave43)} chars")
    soma = 0
    for i, d in enumerate(reversed(chave43)):
        soma += int(d) * _PESOS_DV[i % len(_PESOS_DV)]
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return str(dv)


def gerar_cnf() -> str:
    """cNF (8 dígitos) aleatório — `secrets` p/ imprevisibilidade. Gerar 1x e congelar."""
    return f"{secrets.randbelow(10**8):08d}"


def montar_chave(
    *,
    c_uf: str,
    aamm: str,
    cnpj: str,
    modelo: int,
    serie: int,
    n_nf: int,
    tp_emis: int,
    c_nf: str,
) -> str:
    """Monta os 44 dígitos da chave de acesso incluindo o DV."""
    _validar_componentes(c_uf, aamm, cnpj, modelo, serie, n_nf, tp_emis, c_nf)
    chave43 = f"{c_uf}{aamm}{cnpj}{modelo:0>2}{serie:0>3}{n_nf:0>9}{tp_emis:0>1}{c_nf}"
    return chave43 + calc_dv_chave(chave43)


def _validar_componentes(
    c_uf: str, aamm: str, cnpj: str, modelo: int, serie: int, n_nf: int, tp_emis: int, c_nf: str
) -> None:
    if not (len(c_uf) == 2 and c_uf.isdigit()):
        raise ChaveAcessoError(f"c_uf deve ter 2 dígitos, recebido {c_uf!r}")
    if not (len(aamm) == 4 and aamm.isdigit()):
        raise ChaveAcessoError(f"aamm deve ter 4 dígitos, recebido {aamm!r}")
    if not (len(cnpj) == 14 and cnpj.isdigit()):
        raise ChaveAcessoError(f"cnpj deve ter 14 dígitos, recebido {len(cnpj)} chars")
    if modelo not in (55, 65):
        raise ChaveAcessoError(f"modelo deve ser 55 ou 65, recebido {modelo}")
    if not 0 <= serie <= 999:
        raise ChaveAcessoError(f"serie fora de 0..999: {serie}")
    if not 1 <= n_nf <= 999_999_999:
        raise ChaveAcessoError(f"n_nf fora de 1..999_999_999: {n_nf}")
    if not 1 <= tp_emis <= 9:
        raise ChaveAcessoError(f"tp_emis fora de 1..9: {tp_emis}")
    if not (len(c_nf) == 8 and c_nf.isdigit()):
        raise ChaveAcessoError(f"c_nf deve ter 8 dígitos, recebido {c_nf!r}")


def parse_chave(chave: str) -> dict[str, str | int]:
    """Quebra a chave de 44 dígitos nos componentes nomeados (não valida DV)."""
    if not re.fullmatch(r"\d{44}", chave):
        raise ChaveAcessoError(f"chave deve ter 44 dígitos, recebido {chave!r}")
    return {
        "c_uf": chave[0:2],
        "aamm": chave[2:6],
        "cnpj": chave[6:20],
        "modelo": int(chave[20:22]),
        "serie": int(chave[22:25]),
        "n_nf": int(chave[25:34]),
        "tp_emis": int(chave[34:35]),
        "c_nf": chave[35:43],
        "c_dv": chave[43:44],
    }


def validar_chave(chave: str) -> bool:
    """True se a chave tem 44 dígitos e o DV bate."""
    if not re.fullmatch(r"\d{44}", chave):
        return False
    return calc_dv_chave(chave[:43]) == chave[43]

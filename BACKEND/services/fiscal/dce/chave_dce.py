"""Chave de acesso da DC-e — 44 dígitos, modelo 99, DV módulo 11.

Mesmo layout de 44 díg. da NF-e, mas:
  - o CNPJ é o do ASSINANTE (marketplace/MIG), NÃO o do remetente (vendedor CPF);
  - o modelo é 99.
Confirmado contra um DACE real (chave keyed ao CNPJ da EBAZAR/ML). Reaproveita `calc_dv_chave`
do NF-e (o algoritmo do DV é genérico sobre os 43 primeiros dígitos).

Layout (DFe DC-e, confirmado decompondo chaves reais autorizadas):
    cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nDC(9) tpEmis(1) tpEmit(1) nSiteAutoriz(1) cDC(6) cDV(1)
A chave INCLUI o tpEmit (tipo de emitente: 1=Marketplace) — diferente da NF-e.
nSiteAutoriz=0 para autorizador de site único (Ambiente Nacional PR).
"""

from __future__ import annotations

import re
import secrets

from services.fiscal.sefaz.chave import calc_dv_chave
from services.fiscal.sefaz.exceptions import ChaveAcessoError

MODELO_DCE = 99


def gerar_cdc() -> str:
    """cDC (6 dígitos) aleatório — código que compõe a chave. Gerar 1x e congelar."""
    return f"{secrets.randbelow(10**6):06d}"


def montar_chave_dce(
    *,
    c_uf: str,
    aamm: str,
    cnpj_assinante: str,
    serie: int,
    n_dc: int,
    tp_emis: int,
    c_dc: str,
    tp_emit: int = 1,
    n_site: str = "0",
) -> str:
    """Monta os 44 dígitos da chave de acesso da DC-e (modelo 99) incluindo o DV."""
    if not (len(c_uf) == 2 and c_uf.isdigit()):
        raise ChaveAcessoError(f"c_uf deve ter 2 dígitos, recebido {c_uf!r}")
    if not (len(aamm) == 4 and aamm.isdigit()):
        raise ChaveAcessoError(f"aamm deve ter 4 dígitos, recebido {aamm!r}")
    if not (len(cnpj_assinante) == 14 and cnpj_assinante.isdigit()):
        raise ChaveAcessoError(f"cnpj_assinante deve ter 14 dígitos, recebido {len(cnpj_assinante)} chars")
    if not 0 <= serie <= 999:
        raise ChaveAcessoError(f"serie fora de 0..999: {serie}")
    if not 1 <= n_dc <= 999_999_999:
        raise ChaveAcessoError(f"n_dc fora de 1..999_999_999: {n_dc}")
    if not 1 <= tp_emis <= 9:
        raise ChaveAcessoError(f"tp_emis fora de 1..9: {tp_emis}")
    if not 0 <= tp_emit <= 9:
        raise ChaveAcessoError(f"tp_emit fora de 0..9: {tp_emit}")
    if not (len(n_site) == 1 and n_site.isdigit()):
        raise ChaveAcessoError(f"n_site deve ter 1 dígito, recebido {n_site!r}")
    if not (len(c_dc) == 6 and c_dc.isdigit()):
        raise ChaveAcessoError(f"c_dc deve ter 6 dígitos, recebido {c_dc!r}")

    chave43 = (
        f"{c_uf}{aamm}{cnpj_assinante}{MODELO_DCE:0>2}{serie:0>3}"
        f"{n_dc:0>9}{tp_emis:0>1}{tp_emit:0>1}{n_site}{c_dc}"
    )
    return chave43 + calc_dv_chave(chave43)


def validar_chave_dce(chave: str) -> bool:
    """True se a chave tem 44 dígitos, modelo 99 na posição certa e o DV bate."""
    if not re.fullmatch(r"\d{44}", chave):
        return False
    if chave[20:22] != f"{MODELO_DCE:0>2}":
        return False
    return calc_dv_chave(chave[:43]) == chave[43]

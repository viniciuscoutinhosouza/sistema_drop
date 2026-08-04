"""is_full_cnpj: reconhecer filiais do FULL do ML pela raiz do CNPJ.

O FULL do ML (EBAZAR, raiz 03007331) usa muitas filiais; só algumas são cadastradas. Remessas às
filiais não cadastradas (ex.: NF-e 2371 → 03007331022978) precisam ser reconhecidas pela raiz,
senão o estoque FULL fica subcontado.
"""
import asyncio

from models.full_stock import FullCnpj
from services.full_stock_service import is_full_cnpj


def test_full_cnpj_match_por_raiz(mock_db):
    fc = FullCnpj(id=1, cnpj="03007331002438", marketplace_account_id=2, cmig_id=1, is_active=True)
    mock_db.set_result(None, rows=[fc])
    got = asyncio.run(is_full_cnpj(mock_db, "03007331022978", 1))  # outra filial da mesma raiz
    assert got is fc


def test_full_cnpj_match_exato(mock_db):
    fc = FullCnpj(id=1, cnpj="03007331002438", marketplace_account_id=2, cmig_id=1, is_active=True)
    mock_db.set_result(None, rows=[fc])
    got = asyncio.run(is_full_cnpj(mock_db, "03.007.331/0024-38", 1))  # formatado → normaliza
    assert got is fc


def test_full_cnpj_raiz_diferente_nao_casa(mock_db):
    fc = FullCnpj(id=1, cnpj="03007331002438", marketplace_account_id=2, cmig_id=1, is_active=True)
    mock_db.set_result(None, rows=[fc])
    got = asyncio.run(is_full_cnpj(mock_db, "12345678000199", 1))  # empresa diferente
    assert got is None

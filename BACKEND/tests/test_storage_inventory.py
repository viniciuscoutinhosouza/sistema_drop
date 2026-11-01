"""Testes do inventário por endereço (ADR-0039 Fase 3a).

A maior parte do `apply_count` toca Oracle (integração). Aqui cobrimos o que é puro: o passthrough de
`resolve_base_product` para produtos-base (não consulta o banco) — garante que o `base_product_*` do
movimento 'adjust' usa a MESMA semântica do débito (variante→base; base→ele mesmo)."""
import asyncio

from services.storage_inventory_service import divergence
from services.storage_service import resolve_base_product


def test_resolve_base_product_passthrough_base():
    # produto-base não consulta o banco (db pode ser None) e devolve a si mesmo
    assert asyncio.run(resolve_base_product(None, "pg", 5)) == ("pg", 5)
    assert asyncio.run(resolve_base_product(None, "cmig", 9)) == ("cmig", 9)


def test_resolve_base_product_normaliza_caixa():
    assert asyncio.run(resolve_base_product(None, "PG", 7)) == ("pg", 7)


def test_divergence_sem_endereco_positivo():
    # contábil 10, endereçado 8 → faltam 2 no endereço (fantasma "sem endereço"), não acionável
    d = divergence(10, 8)
    assert d == {"stock_quantity": 10, "addressed_total": 8, "unaddressed": 2, "over": False}


def test_divergence_over_e_acionavel():
    # endereçado 12 > contábil 10 → over (físico lançado além do saldo)
    d = divergence(10, 12)
    assert d["over"] is True and d["unaddressed"] == -2


def test_divergence_bate_certo():
    assert divergence(5, 5) == {"stock_quantity": 5, "addressed_total": 5, "unaddressed": 0, "over": False}


def test_divergence_saldo_desconhecido():
    d = divergence(None, 4)
    assert d["stock_quantity"] is None and d["unaddressed"] is None and d["over"] is False

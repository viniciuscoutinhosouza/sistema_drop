"""Testes da ordenação/fatiamento do plano de picking (ADR-0039 Fase 2) — função pura, sem Oracle."""
import datetime

from services.storage_picking import build_plan, order_allocations


def _row(**kw):
    base = {"lot_id": None, "lot_expiry": None, "alloc_pick_order": 0, "loose_units": 0,
            "location_pick_sequence": 0, "full_code": "X", "qty_units": 10}
    base.update(kw)
    return base


def _fc(rows):
    return [r["full_code"] for r in rows]


def test_fefo_validade_mais_proxima_primeiro():
    a = _row(full_code="A", lot_id=1, lot_expiry=datetime.date(2026, 1, 1))
    b = _row(full_code="B", lot_id=2, lot_expiry=datetime.date(2025, 6, 1))
    assert _fc(order_allocations([a, b], traceable=True)) == ["B", "A"]


def test_fefo_sem_validade_vai_por_ultimo():
    dated = _row(full_code="A", lot_id=1, lot_expiry=datetime.date(2026, 1, 1))
    no_exp = _row(full_code="B", lot_id=2, lot_expiry=None)
    assert _fc(order_allocations([no_exp, dated], traceable=True)) == ["A", "B"]


def test_rastreavel_sem_lote_identificado_vai_por_ultimo():
    ident = _row(full_code="A", lot_id=5, lot_expiry=datetime.date(2027, 1, 1))
    unknown = _row(full_code="B", lot_id=None)  # endereço sem lote informado
    assert _fc(order_allocations([unknown, ident], traceable=True)) == ["A", "B"]


def test_pick_order_desempata_mesma_validade():
    a = _row(full_code="A", lot_id=1, lot_expiry=datetime.date(2026, 1, 1), alloc_pick_order=2)
    b = _row(full_code="B", lot_id=1, lot_expiry=datetime.date(2026, 1, 1), alloc_pick_order=1)
    assert _fc(order_allocations([a, b], traceable=True)) == ["B", "A"]


def test_caixa_aberta_solta_antes_de_fechada():
    fechada = _row(full_code="A", loose_units=0)
    aberta = _row(full_code="B", loose_units=3)
    assert _fc(order_allocations([fechada, aberta], traceable=False)) == ["B", "A"]


def test_pick_sequence_e_fullcode_desempatam():
    a = _row(full_code="Z", location_pick_sequence=1)
    b = _row(full_code="A", location_pick_sequence=1)
    c = _row(full_code="C", location_pick_sequence=0)
    assert _fc(order_allocations([a, b, c], traceable=False)) == ["C", "A", "Z"]


def test_nao_rastreavel_ignora_lote():
    # validade não influencia quando o produto não é rastreável; pick_order manda
    a = _row(full_code="A", lot_expiry=datetime.date(2020, 1, 1), alloc_pick_order=9)
    b = _row(full_code="B", lot_expiry=datetime.date(2099, 1, 1), alloc_pick_order=1)
    assert _fc(order_allocations([a, b], traceable=False)) == ["B", "A"]


def test_build_plan_fatia_guloso_sem_falta():
    ordered = [_row(full_code="A", qty_units=10), _row(full_code="B", qty_units=8)]
    stops, short = build_plan(ordered, 15)
    assert [(s["full_code"], s["take"]) for s in stops] == [("A", 10), ("B", 5)]
    assert short == 0


def test_build_plan_sinaliza_falta():
    ordered = [_row(full_code="A", qty_units=10), _row(full_code="B", qty_units=8)]
    stops, short = build_plan(ordered, 25)
    assert [s["take"] for s in stops] == [10, 8]
    assert short == 7

"""⚠️ TEMPORÁRIO — testa a folha de CÓDIGOS DE TESTE da Separação (QR por SKU + tirar/fim foto).
Apagar junto com `services/test_codes_service.py` e a rota `POST /separation/test-codes.pdf`."""
import pytest

from services.test_codes_service import render_test_codes


def test_render_test_codes_gera_pdf():
    items = [
        {"code": "SKU-ABC", "label": "Produto A"},
        {"code": "7891234567895", "label": "Produto B"},
        {"code": "TIRAR-FOTO", "label": "TIRAR FOTO"},
        {"code": "FIM-FOTOS", "label": "FIM DAS FOTOS"},
    ]
    pdf = render_test_codes(items, title="Códigos de teste — 2 pedido(s)")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_render_test_codes_ignora_code_vazio_sem_quebrar():
    # Linha sem SKU nem EAN não tem código → é pulada, não quebra o render.
    pdf = render_test_codes([{"code": "", "label": "sem código"}])
    assert pdf[:4] == b"%PDF"


def test_render_test_codes_lista_vazia():
    pdf = render_test_codes([])
    assert pdf[:4] == b"%PDF"


def test_render_test_codes_pagina_muitos_itens():
    # 40 itens (4 col) força paginação — não pode levantar.
    items = [{"code": f"SKU-{i:03d}", "label": f"Item {i}"} for i in range(40)]
    pdf = render_test_codes(items)
    assert pdf[:4] == b"%PDF"

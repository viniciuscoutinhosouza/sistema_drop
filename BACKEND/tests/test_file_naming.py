"""Testes do nome de arquivo padronizado (sanitização ASCII anti header-injection)."""
import types

from services.file_naming import (
    TIPO_ETIQUETA,
    TIPO_NFE,
    order_download_filename,
    slugify_name,
)


def test_slug_remove_acento_e_especiais():
    assert slugify_name("Eláine C.") == "Elaine-C"
    assert slugify_name("João  //  Silva") == "Joao-Silva"


def test_slug_bloqueia_header_injection():
    # aspas, CR/LF e controle NÃO podem passar (protege o Content-Disposition)
    out = slugify_name('a"\r\nContent-Length: 0')
    assert '"' not in out and "\r" not in out and "\n" not in out
    assert out.isascii()


def test_slug_fallback_vazio():
    assert slugify_name("") == "sem-nome"
    assert slugify_name(None) == "sem-nome"
    assert slugify_name("   ") == "sem-nome"
    assert slugify_name("!!!") == "sem-nome"


def test_slug_trunca_sem_hifen_final():
    s = slugify_name("A" * 100, maxlen=10)
    assert len(s) == 10 and not s.endswith("-")
    assert slugify_name("abcdefghij-----", maxlen=11).rstrip("-") == "abcdefghij"


def test_filename_com_order():
    o = types.SimpleNamespace(platform_order_id="2000017318796590", buyer_name="Elaine C", id=1738)
    assert order_download_filename(TIPO_ETIQUETA, "pdf", order=o) == "Etiqueta_2000017318796590_Elaine-C.pdf"
    assert order_download_filename(TIPO_NFE, "xml", order=o) == "NF-e_2000017318796590_Elaine-C.xml"


def test_filename_sem_venda_usa_pedido_id():
    o = types.SimpleNamespace(platform_order_id=None, buyer_name="Fulano", id=99)
    assert order_download_filename(TIPO_ETIQUETA, "pdf", order=o) == "Etiqueta_pedido-99_Fulano.pdf"


def test_filename_venda_cliente_direto_e_fallback():
    assert order_download_filename(TIPO_NFE, "xml", venda="123", cliente=None) == "NF-e_123_sem-nome.xml"

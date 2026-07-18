"""Testes da Declaração de Conteúdo (ZPL) — funções puras (sem DB/rede)."""
import io

from services import content_declaration as cd


def test_dest_address_desembrulha_objetos_ml():
    """Endereço do ML manda bairro/cidade/estado como {id,name} — devem virar o NOME, não o dict.
    Era o bug que quebrava com 'unhashable type: slice'."""
    raw = (
        '{"street_name":"Rua Leopoldo","street_number":"SN",'
        '"neighborhood":{"id":null,"name":"Jardim California"},'
        '"city":{"id":"X","name":"Trindade"},'
        '"state":{"id":"BR-GO","name":"Goias"},"zip_code":"75383845"}'
    )
    lines = cd._dest_address_lines(raw)
    assert all(isinstance(x, str) for x in lines)  # nada de dict cru
    assert lines[0].startswith("Rua Leopoldo SN")
    assert "Jardim California" in lines
    assert any("Trindade/Goias" in x and "75383845" in x for x in lines)


def test_dest_address_formato_plano_e_vazio():
    lines = cd._dest_address_lines(
        {"logradouro": "Av X", "numero": "10", "bairro": "Centro", "cidade": "SP", "uf": "SP"}
    )
    assert lines[0] == "Av X 10"
    assert cd._dest_address_lines(None) == ["(endereco nao cadastrado)"]
    assert cd._dest_address_lines("texto livre") == ["texto livre"]


def test_wrap_quebra_por_palavras():
    linhas = cd._wrap("um dois tres quatro cinco", 9)
    assert linhas == ["um dois", "tres", "quatro", "cinco"]
    assert all(len(x) <= 9 for x in linhas)


def test_money_pt_br():
    assert cd._money(1234.5) == "R$ 1.234,50"
    assert cd._money(0) == "R$ 0,00"


def test_png_to_gfa_gera_campo_grafico():
    """Imagem → campo gráfico ZPL 1-bit (^GFA). É a única forma de imagem em ZPL."""
    from PIL import Image

    im = Image.new("RGB", (160, 120), "white")
    for x in range(160):
        for y in range(120):
            if (x // 8 + y // 8) % 2 == 0:
                im.putpixel((x, y), (0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    res = cd._png_to_gfa(buf.getvalue())
    assert res is not None
    cmd, h = res
    assert cmd.startswith("^GFA,")
    assert h > 0
    # largura fixa 96 dots → 12 bytes por linha
    assert f",{cd._THUMB_W // 8}," in cmd


def test_png_to_gfa_imagem_invalida_retorna_none():
    assert cd._png_to_gfa(b"nao eh imagem") is None


import pytest


@pytest.mark.asyncio
async def test_host_is_safe_bloqueia_interno():
    """Anti-SSRF: host que resolve p/ metadados/loopback/privado é recusado."""
    assert await cd._host_is_safe("169.254.169.254") is False  # metadados da nuvem
    assert await cd._host_is_safe("127.0.0.1") is False
    assert await cd._host_is_safe("10.0.0.1") is False


@pytest.mark.asyncio
async def test_fetch_thumb_recusa_esquema_e_host_interno():
    assert await cd._fetch_thumb("file:///etc/passwd") is None
    assert await cd._fetch_thumb("http://169.254.169.254/latest/meta-data/") is None
    assert await cd._fetch_thumb("notaurl") is None

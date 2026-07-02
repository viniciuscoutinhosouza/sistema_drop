"""Teste do empacotador do ZIP "Baixar tudo" da gaiola (função pura)."""
import io
import zipfile

from routers.separation import _assemble_bundle_zip


def test_assemble_bundle_zip_estrutura():
    chave = "33260659951479000194550010000000201453799230"
    docs = [("MLB123", chave, b"%PDF-1.4 danfe", b"<nfeProc/>")]
    labels = [("Etiquetas/ml_conta.pdf", b"%PDF-1.4 label")]
    avisos = ["Pedido #9 (Fulano): NF-e não disponível/autorizada — não incluído."]

    data = _assemble_bundle_zip("G-20260611-001", docs, labels, avisos)
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = set(zf.namelist())

    assert "G-20260611-001/Etiquetas/ml_conta.pdf" in names
    assert f"G-20260611-001/NF-e/MLB123-{chave}.pdf" in names
    assert f"G-20260611-001/NF-e/MLB123-{chave}.xml" in names
    assert "G-20260611-001/_avisos.txt" in names
    assert zf.read(f"G-20260611-001/NF-e/MLB123-{chave}.pdf") == b"%PDF-1.4 danfe"
    assert zf.read("G-20260611-001/_avisos.txt").decode("utf-8").startswith("Pedido #9")


def test_assemble_bundle_zip_sem_avisos_nao_cria_arquivo():
    data = _assemble_bundle_zip("G-1", [("1", "K", b"a", b"b")], [], [])
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert not any(n.endswith("_avisos.txt") for n in names)
    assert "G-1/NF-e/1-K.pdf" in names

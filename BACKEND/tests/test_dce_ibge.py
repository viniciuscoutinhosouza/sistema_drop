"""Teste da normalização de nome de município (função pura, sem DB/rede)."""
from services.fiscal.dce.ibge import normalize_nome


def test_normalize_remove_acento_e_caixa():
    assert normalize_nome("São Paulo") == "SAO PAULO"
    assert normalize_nome("Palmas") == "PALMAS"
    assert normalize_nome("  Rio  de   Janeiro ") == "RIO DE JANEIRO"
    assert normalize_nome("Açaí-Grão") == "ACAI-GRAO"


def test_normalize_casa_variacoes_de_acento():
    # o comprador pode vir sem acento do ML; deve casar com o oficial acentuado.
    assert normalize_nome("Sao Paulo") == normalize_nome("São Paulo")
    assert normalize_nome("BRASILIA") == normalize_nome("Brasília")


def test_normalize_vazio():
    assert normalize_nome("") == ""
    assert normalize_nome(None) == ""

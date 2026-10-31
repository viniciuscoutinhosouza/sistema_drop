"""Testes do Endereçamento Físico de Estoque (ADR-0039) — lógica pura, sem Oracle.

Cobre: dígito verificador EAN-13, geração em massa de códigos (named/numeric/letter + erros + teto)
e geração de código interno (formato/unicidade) com um db fake. Os fluxos que tocam o banco
(árvore, alocação, reconciliação, scan) são exercitados em integração.
"""
import pytest

from services import storage_service as ss


# ── EAN-13 ──────────────────────────────────────────────────────────────────
def test_ean13_check_digit_conhecidos():
    # Casos conhecidos (dígito verificador oficial)
    assert ss.ean13_check_digit("400638133393") == "1"   # 4006381333931
    assert ss.ean13_check_digit("978020137962") == "4"   # 9780201379624


def test_ean13_check_digit_fecha_com_recalculo():
    body = "200123456789"
    dv = ss.ean13_check_digit(body)
    full = body + dv
    assert ss.ean13_check_digit(full[:12]) == full[12]


# ── Geração em massa ────────────────────────────────────────────────────────
def test_bulk_numeric_com_pad_prefixo_sufixo():
    out = ss.generate_bulk_codes({"type": "numeric", "start": 1, "end": 3, "pad": 2, "prefix": "P", "suffix": "x"})
    assert out == ["P01x", "P02x", "P03x"]


def test_bulk_letter_inclusivo():
    assert ss.generate_bulk_codes({"type": "letter", "start": "A", "end": "C"}) == ["A", "B", "C"]
    assert ss.generate_bulk_codes({"type": "letter", "start": "a", "end": "f"}) == ["A", "B", "C", "D", "E", "F"]


def test_bulk_named_dedup_preserva_ordem():
    out = ss.generate_bulk_codes({"type": "named", "names": ["Mickey", "Pateta", "Mickey", " Donald "]})
    assert out == ["Mickey", "Pateta", "Donald"]


def test_bulk_irmaos_divergentes():
    # Sala Mickey 1..8 ; Sala Pateta 1..5 — chamadas independentes, contagens diferentes (comentário #1 do dono)
    assert len(ss.generate_bulk_codes({"type": "numeric", "start": 1, "end": 8})) == 8
    assert len(ss.generate_bulk_codes({"type": "numeric", "start": 1, "end": 5})) == 5


def test_bulk_erros_fail_loud():
    with pytest.raises(ValueError):
        ss.generate_bulk_codes({"type": "numeric", "start": 5, "end": 1})     # faixa invertida
    with pytest.raises(ValueError):
        ss.generate_bulk_codes({"type": "letter", "start": "F", "end": "A"})  # letras invertidas
    with pytest.raises(ValueError):
        ss.generate_bulk_codes({"type": "named", "names": []})                # sem nomes
    with pytest.raises(ValueError):
        ss.generate_bulk_codes({"type": "xpto"})                              # esquema inválido


def test_bulk_teto_maximo():
    with pytest.raises(ValueError):
        ss.generate_bulk_codes({"type": "numeric", "start": 1, "end": ss.MAX_BULK + 5})


# ── Código interno ────────────────────────────────────────────────────────────
class _Exec:
    def __init__(self, hits):
        self._hits = hits

    def first(self):
        return object() if self._hits else None


class _FakeDB:
    """db fake: as primeiras `collisions` consultas 'acham' um EAN existente, depois livram."""

    def __init__(self, collisions=0):
        self.collisions = collisions
        self.calls = 0

    async def execute(self, *a, **k):
        self.calls += 1
        hit = self.calls <= self.collisions
        return _Exec(hit)


@pytest.mark.asyncio
async def test_internal_ean_formato():
    code = await ss.generate_internal_ean(_FakeDB())
    assert len(code) == 13
    assert code[0] == "2"                               # faixa de uso interno
    assert ss.ean13_check_digit(code[:12]) == code[12]  # DV válido


@pytest.mark.asyncio
async def test_internal_ean_retenta_em_colisao():
    db = _FakeDB(collisions=3)
    code = await ss.generate_internal_ean(db)
    assert len(code) == 13 and db.calls == 4            # 3 colisões + 1 livre

"""Testes da elegibilidade da emissão automática de NF-e (ADR-0041).

Cobre `_light_eligible` — a decisão BARATA (sem I/O) do claim atômico `arm_if_eligible`. As checagens
caras (CPF por-pedido, ambiente de produção, rastreável) rodam no job e viram 'error' visível; aqui
blindamos a porta de entrada: conta sem opt-in, FULL, pedido com nota, já-armado.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("NFE_CERT_MASTER_KEY", "auto-fiscal-test-key-0123456789abcdef")

from services import auto_fiscal_dispatch as af  # noqa: E402


def _order(**kw):
    base = dict(
        id=1, shipping_mode="correios", shipping_method="drop_off",
        nfe_status=None, auto_fiscal_status=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _acc(**kw):
    base = dict(platform="mercadolivre", nfe_auto_emit=True)
    base.update(kw)
    return SimpleNamespace(**base)


def test_eligivel_feliz_ml():
    assert af._light_eligible(_order(), _acc()) is True


def test_eligivel_feliz_shopee():
    assert af._light_eligible(_order(), _acc(platform="shopee")) is True


def test_conta_sem_opt_in_nao_arma():
    assert af._light_eligible(_order(), _acc(nfe_auto_emit=False)) is False


def test_plataforma_fora_nao_arma():
    assert af._light_eligible(_order(), _acc(platform="bling")) is False


def test_full_nao_arma():
    # FULL pelo modo canônico OU pelo método cru (is_full_order)
    assert af._light_eligible(_order(shipping_mode="full"), _acc()) is False
    assert af._light_eligible(_order(shipping_method="fulfillment"), _acc()) is False


def test_pedido_com_nota_em_curso_nao_arma():
    for st in ("authorized", "pending", "in_process"):
        assert af._light_eligible(_order(nfe_status=st), _acc()) is False


def test_pedido_ja_na_lane_nao_rearma():
    for st in ("emitting", "emitted", "done", "error"):
        assert af._light_eligible(_order(auto_fiscal_status=st), _acc()) is False


def test_conta_none_nao_arma():
    assert af._light_eligible(_order(), None) is False


def test_sanitize_mascara_cpf_cnpj():
    # LGPD: rejeições da SEFAZ/Shopee ecoam o documento do comprador — não pode vazar p/ a UI/log.
    assert "12345678901" not in af.sanitize_fiscal_msg("CPF 12345678901 inválido")
    assert "***" in af.sanitize_fiscal_msg("CPF 12345678901 inválido")
    assert "123.456.789-00" not in af.sanitize_fiscal_msg("destinatário 123.456.789-00 recusado")
    assert "12.345.678/0001-99" not in af.sanitize_fiscal_msg("CNPJ 12.345.678/0001-99 divergente")
    # Não mutila números curtos legítimos (NCM 8 díg, cStat, etc.)
    assert af.sanitize_fiscal_msg("NCM 90183111 ausente") == "NCM 90183111 ausente"
    assert af.sanitize_fiscal_msg(None) == ""
    assert len(af.sanitize_fiscal_msg("x" * 900)) <= 500

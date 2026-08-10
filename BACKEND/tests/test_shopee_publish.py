"""Builder agnóstico da publicação Shopee (ADR-0020).

`build_item_payload` e `collect_blockers` são puros — dá para provar o contrato do
`add_item` sem Oracle e sem chamar a Shopee. Cobre justamente os defeitos que fizeram o
caminho anterior nunca publicar (tax_info ausente, estoque fixo em 1, sem item_sku,
limites de título/descrição errados).
"""

import json

from services.shopee_publish import (
    DESC_MAX,
    TITULO_MAX,
    ShopCtx,
    ShopeeProductInput,
    build_item_payload,
    build_shopee_attributes,
    collect_blockers,
)


def _ok(**over) -> ShopeeProductInput:
    base = {
        "title": "Puxador Estribo Pulley Fechado Pegada Emborrachada 15cm",
        "description": "Puxador estribo para pulley, pegada emborrachada, 15 cm.",
        "category_id": 101890,
        "price": 59.9,
        "stock": 7,
        "sku": "501RD",
        "ncm": "95069100",
        "weight_kg": 1.2,
        "length_cm": 20,
        "width_cm": 10,
        "height_cm": 8,
        "images": [{"url": "http://x/1.jpg", "is_primary": True, "sort_order": 0}],
    }
    base.update(over)
    return ShopeeProductInput(**base)


# ── Payload ───────────────────────────────────────────────────────────────────


def test_payload_envia_tax_info_com_ncm():
    """tax_info é obrigatório na loja 'invoice issued by Shopee' — sem ele o add_item
    falhava 100% das vezes."""
    item = build_item_payload(_ok(), ["img1"], [{"logistic_id": 91003, "enabled": True}])
    assert item["tax_info"]["ncm"] == "95069100"
    assert "cest" not in item["tax_info"]  # só quando cadastrado


def test_payload_inclui_cest_quando_cadastrado():
    item = build_item_payload(_ok(cest="2800300"), ["img1"], [])
    assert item["tax_info"]["cest"] == "2800300"


def test_payload_usa_estoque_real_e_nao_1():
    item = build_item_payload(_ok(stock=7), ["img1"], [])
    assert item["seller_stock"] == [{"stock": 7}]


def test_payload_estoque_negativo_vira_zero():
    item = build_item_payload(_ok(stock=-3), ["img1"], [])
    assert item["seller_stock"] == [{"stock": 0}]


def test_payload_envia_item_sku():
    """Sem item_sku o vínculo pedido→produto na baixa de estoque fica enfraquecido."""
    assert build_item_payload(_ok(), ["img1"], [])["item_sku"] == "501RD"


def test_payload_sem_sku_nao_envia_campo_vazio():
    assert "item_sku" not in build_item_payload(_ok(sku=None), ["img1"], [])


def test_payload_trunca_titulo_em_120_nao_100():
    item = build_item_payload(_ok(title="A" * 200), ["img1"], [])
    assert len(item["item_name"]) == TITULO_MAX == 120


def test_payload_trunca_descricao_em_5000_nao_3000():
    item = build_item_payload(_ok(description="D" * 9000), ["img1"], [])
    assert len(item["description"]) == DESC_MAX == 5000


def test_payload_sem_marca_manda_nobrand():
    item = build_item_payload(_ok(), ["img1"], [])
    assert item["brand"] == {"brand_id": 0, "original_brand_name": "NoBrand"}


def test_payload_com_marca_cadastrada_nao_manda_nobrand():
    attrs = json.dumps([{"id": "__SHOPEE_BRAND__", "value_id": 12345}])
    item = build_item_payload(_ok(attributes_json=attrs), ["img1"], [])
    assert item["brand"] == {"brand_id": 12345}


def test_payload_nunca_usa_description_type_extended():
    """A loja não está na whitelist: 'can only upload plain text'."""
    assert "description_type" not in build_item_payload(_ok(), ["img1"], [])


# ── Bloqueios (falhar alto) ───────────────────────────────────────────────────


def test_produto_completo_nao_tem_bloqueio():
    assert collect_blockers(_ok()) == []


def test_bloqueia_sem_ncm():
    b = collect_blockers(_ok(ncm=None))
    assert any("NCM" in x for x in b)


def test_bloqueia_descricao_curta():
    b = collect_blockers(_ok(description="curta"))
    assert any("Descrição muito curta" in x for x in b)


def test_bloqueia_categoria_de_outro_marketplace():
    """Categoria do ML (MLB…) chegava como número pequeno; a Shopee exige > 99999."""
    b = collect_blockers(_ok(category_id=1234))
    assert any("Categoria inválida" in x for x in b)


def test_bloqueia_sem_imagem_e_sem_peso():
    b = collect_blockers(_ok(images=[], weight_kg=None))
    assert any("imagens" in x for x in b)
    assert any("peso" in x for x in b)


def test_bloqueia_peso_acima_do_limite_do_canal():
    ctx = ShopCtx(logistic_info=[{"logistic_id": 1, "enabled": True}], limite_peso_kg=30)
    b = collect_blockers(_ok(weight_kg=45), ctx)
    assert any("acima do limite" in x for x in b)


def test_bloqueia_sem_canal_de_logistica():
    b = collect_blockers(_ok(), ShopCtx(logistic_info=[]))
    assert any("logística" in x for x in b)


def test_erro_de_consulta_vira_bloqueio_amigavel_nao_excecao():
    ctx = ShopCtx(erro_consulta="Não foi possível validar categoria/marca/canais na Shopee agora")
    assert any("Não foi possível validar" in x for x in collect_blockers(_ok(), ctx))


# ── Atributos ─────────────────────────────────────────────────────────────────


def test_atributos_ignoram_ids_nao_numericos_do_ml():
    """Cadastro feito com o picker do ML gravava {'id': 'BRAND'} — não é atributo Shopee."""
    attrs = json.dumps([
        {"id": "BRAND", "value_name": "Nike"},
        {"id": "101", "kind": "single", "value_id": 7},
    ])
    lista, brand, ids = build_shopee_attributes(attrs)
    assert ids == {101}
    assert lista == [{"attribute_id": 101,
                      "attribute_value_list": [
                          {"value_id": 7, "original_value_name": "", "value_unit": ""}]}]
    assert brand is None


def test_atributos_json_invalido_nao_estoura():
    assert build_shopee_attributes("{quebrado") == ([], None, set())


def test_atributo_multi_gera_varios_valores():
    attrs = json.dumps([{"id": "5", "kind": "multi", "value_ids": [1, 2]}])
    lista, _, _ = build_shopee_attributes(attrs)
    assert len(lista[0]["attribute_value_list"]) == 2


# ── Imagens ───────────────────────────────────────────────────────────────────


def test_imagens_capa_primeiro_e_maximo_9():
    imgs = [{"url": f"u{i}", "is_primary": False, "sort_order": i} for i in range(12)]
    imgs.append({"url": "capa", "is_primary": True, "sort_order": 99})
    ordenadas = _ok(images=imgs).imagens_ordenadas()
    assert ordenadas[0]["url"] == "capa"
    assert len(ordenadas) == 9

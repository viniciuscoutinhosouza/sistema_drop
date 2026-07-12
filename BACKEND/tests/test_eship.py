"""Testes do módulo isolado eShip — funções puras (sem rede/DB)."""
import pytest

from integrations.eship import service
from integrations.eship.status_map import map_status


def test_map_status_known_and_unknown():
    # Mapeamento por id numérico (status.id do eShip), não por texto.
    assert map_status(7) == ("shipped", "shipped")          # Em Expedição
    assert map_status(8) == ("shipped", "shipped")          # Concluída/Despachada
    assert map_status(6) == ("ready_to_ship", "separated")  # Aguardando Expedição
    assert map_status(1) == ("handling", None)              # Lançado
    assert map_status(10) == ("cancelled", None)            # Cancelada
    assert map_status("7") == ("shipped", "shipped")        # coage string numérica
    assert map_status(99) == (None, None)                   # desconhecido
    assert map_status(None) == (None, None)


def test_extract_order_id_shapes():
    # PostOrdem responde {"ordem": {"id": ...}} — o id é aninhado.
    assert service.extract_order_id({"ordem": {"id": 123, "status": {"id": 1}}}) == "123"
    assert service.extract_order_id({"idOrdem": 123}) == "123"
    assert service.extract_order_id({"id": "ABC"}) == "ABC"
    assert service.extract_order_id({"data": {"ordem": 99}}) == "99"
    assert service.extract_order_id({"nada": 1}) is None
    assert service.extract_order_id("texto") is None


def test_extract_status_envelope():
    # Envelope real: corpo.body.dados[0].status é o objeto {id, descricao, cor}.
    s, track, url = service.extract_status(
        {
            "corpo": {
                "body": {
                    "dados": [
                        {
                            "status": {"id": 7, "descricao": "Em Expedição"},
                            "codigoRastreamento": "BR123",
                            "urlRastreio": "http://x",
                        }
                    ]
                }
            }
        }
    )
    assert s == 7 and track == "BR123" and url == "http://x"

    # Fallback p/ formato plano antigo (status como string).
    s2, track2, url2 = service.extract_status({"data": {"status": "Entregue"}})
    assert s2 == "Entregue" and track2 is None and url2 is None

    assert service.extract_status({}) == (None, None, None)


def test_build_ordem_payload():
    from models.order import Order, OrderItem
    from integrations.eship.config import EShipCreds

    o = Order(platform_order_id="ML-1", platform="mercadolivre", buyer_name="Fulano")
    o.items = [OrderItem(sku="SKU1", quantity=2), OrderItem(sku="SKU2", quantity=1)]
    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="ARM1", cnpj="123")
    payload = service.build_ordem_payload(o, creds)
    assert payload["numeroOrigem"] == "ML-1"
    assert payload["codigoArmazemOrigem"] == "ARM1"
    assert payload["cadastroDestinatario"]["nomeDestinatario"] == "Fulano"
    assert [p["codigoProduto"] for p in payload["produtos"]] == ["SKU1", "SKU2"]
    assert [p["quantidadeProduto"] for p in payload["produtos"]] == [2, 1]


@pytest.mark.asyncio
async def test_push_order_idempotent_when_already_sent():
    from models.order import Order

    o = Order(platform_order_id="ML-2", eship_order_id="ESHIP-9")
    # db não é tocado porque já há eship_order_id (retorno antecipado)
    res = await service.push_order(db=None, order=o)
    assert res == {"already_sent": True, "eship_order_id": "ESHIP-9"}


def test_extract_order_id_envelope_real():
    # Envelope REAL do eShip (corpo.body.dados[]): era ignorado, e o id caia no fallback mentiroso.
    resp = {"corpo": {"body": {"dados": [{"id": 987654, "numeroOrigem": "ML-1"}]}}}
    assert service.extract_order_id(resp) == "987654"
    # Resposta sem id extraivel: NAO inventar id (antes gravava o numero do pedido do ML).
    assert service.extract_order_id({"corpo": {"body": {"dados": []}}}) is None


def test_order_was_pushed_guard():
    from models.order import Order

    # Ordem aceita pelo WMS sem id extraivel: ainda assim conta como enviada (nao pode duplicar).
    assert service.order_was_pushed(Order(eship_dispatch_status="sent")) is True
    assert service.order_was_pushed(Order(eship_dispatch_status="partial")) is True
    assert service.order_was_pushed(Order(eship_order_id="9")) is True
    # Falhou ou foi cancelada: liberado para novo envio.
    assert service.order_was_pushed(Order(eship_dispatch_status="failed")) is False
    assert service.order_was_pushed(Order(eship_dispatch_status="cancelled")) is False
    assert service.order_was_pushed(Order()) is False


@pytest.mark.asyncio
async def test_send_order_full_nao_deixa_pedido_preso_em_sending(monkeypatch):
    """O bug do dono: a Ordem falhava, o `return` pulava o `except`, e o pedido ficava eternamente
    em 'sending' - todo clique seguinte era recusado com "envio ja em andamento"."""
    from models.order import Order
    from integrations.eship.client import EShipError

    class FakeResult:
        rowcount = 1

    class FakeDB:
        async def execute(self, *_a, **_kw):
            return FakeResult()

        async def commit(self):
            return None

    async def falha_na_ordem(db, order):
        raise EShipError("eShip recusou a ordem")

    monkeypatch.setattr(service, "push_order", falha_na_ordem)

    o = Order(id=1, platform_order_id="ML-3", shipping_mode="flex")
    res = await service.send_order_full(FakeDB(), o)

    assert o.eship_dispatch_status == "failed"       # antes ficava "sending" (travado p/ sempre)
    assert "eShip recusou a ordem" in o.eship_dispatch_error
    assert res["erros"][0]["etapa"] == "ordem"
    # E como nao esta "sent"/"partial" nem tem id, o botao volta a permitir o envio:
    assert service.order_was_pushed(o) is False


def _creds_teste():
    from integrations.eship.config import EShipCreds
    return EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="123")


def test_payload_leva_cpf_ou_cnpj_do_destinatario():
    """O eShip EXIGE cpfDestinatario ou cnpjDestinatario. O tipo vem do ML (billing_info)."""
    from models.order import Order

    pf = Order(platform_order_id="ML-1", buyer_name="Raquel",
               buyer_document="25598286858", buyer_document_type="CPF")
    pf.items = []
    dest = service.build_ordem_payload(pf, _creds_teste())["cadastroDestinatario"]
    assert dest["cpfDestinatario"] == "25598286858"
    assert "cnpjDestinatario" not in dest

    pj = Order(platform_order_id="ML-2", buyer_name="Ezequiel ME",
               buyer_document="67763215000135", buyer_document_type="CNPJ")
    pj.items = []
    dest = service.build_ordem_payload(pj, _creds_teste())["cadastroDestinatario"]
    assert dest["cnpjDestinatario"] == "67763215000135"
    assert "cpfDestinatario" not in dest

    # Sem tipo (cadastro manual/legado): decide pelo comprimento.
    sem_tipo = Order(platform_order_id="ML-3", buyer_name="X", buyer_document="005.912.651-50")
    sem_tipo.items = []
    dest = service.build_ordem_payload(sem_tipo, _creds_teste())["cadastroDestinatario"]
    assert dest["cpfDestinatario"] == "00591265150"   # zero a esquerda preservado


@pytest.mark.asyncio
async def test_ensure_buyer_document_busca_no_billing_info(monkeypatch):
    """O ML tirou `buyer.identification` do GET /orders/{id} - o documento so vem do billing_info."""
    from models.order import Order

    class FakeAcc:
        id = 1
        access_token = "t"

    class FakeScalar:
        def scalar_one_or_none(self):
            return FakeAcc()

    class FakeDB:
        async def execute(self, *_a, **_kw):
            return FakeScalar()

        async def commit(self):
            return None

    # Resposta REAL do endpoint (x-version: 2), como capturada em producao.
    async def fake_billing(token, order_id):
        return {
            "site_id": "MLB",
            "buyer": {
                "cust_id": "143574469",
                "billing_info": {
                    "name": "Raquel Pereira",
                    "identification": {"type": "CPF", "number": "25598286858"},
                },
            },
        }

    async def fake_token(acc, db, **_kw):
        return "t"

    monkeypatch.setattr(service._ml, "get_order_billing_info", fake_billing)
    monkeypatch.setattr(service, "get_valid_token", fake_token)

    o = Order(id=1, platform="mercadolivre", platform_order_id="ML-9", account_id=1)
    doc = await service.ensure_buyer_document(FakeDB(), o)
    assert doc == "25598286858"
    assert o.buyer_document == "25598286858"
    assert o.buyer_document_type == "CPF"

    # Ja tem documento: nao chama o ML de novo (1 chamada por pedido, nao por envio).
    async def nunca(*_a, **_kw):
        raise AssertionError("nao deveria chamar o ML de novo")

    monkeypatch.setattr(service._ml, "get_order_billing_info", nunca)
    assert await service.ensure_buyer_document(FakeDB(), o) == "25598286858"


def test_extract_order_id_postordem_dados_objeto():
    """O PostOrdem devolve `dados` como OBJETO (as consultas devolvem LISTA). Tratar so a lista
    fazia o id se perder: o WMS criava a ordem, gravavamos id nulo, e o clique seguinte tentava
    criar de novo -> "MOR8003: N Ordem ja cadastrada". Resposta real de producao."""
    resp = {
        "erros": None,
        "corpo": {"body": {"dados": {"ordem": {
            "id": 3098257,
            "destinatario": {"id": 3068704, "nome": "ALVARO CORDEIRO DE ASSUMPCAO"},
        }}}},
    }
    assert service.extract_order_id(resp) == "3098257"

    # Consultas continuam devolvendo lista - os dois formatos precisam funcionar.
    assert service.extract_order_id(
        {"corpo": {"body": {"dados": [{"ordem": {"id": 42}}]}}}
    ) == "42"


def test_ja_cadastrada_reconhece_mor8003():
    from integrations.eship.client import EShipError

    e = EShipError("eShip webServicePostOrdem retornou erro MOR8003: N Ordem : '200001' ja cadastrada")
    assert service._ja_cadastrada(e) is True
    assert service._ja_cadastrada(EShipError("timeout")) is False


@pytest.mark.asyncio
async def test_push_order_recupera_ordem_existente_no_mor8003(monkeypatch):
    """Ordem ja existe no WMS: nao e falha. Recupera o id e segue para os anexos - antes isso
    abortava o envio, e a NF-e emitida depois nunca era anexada."""
    from models.order import Order
    from integrations.eship.client import EShipError
    from integrations.eship.config import EShipCreds

    class FakeDB:
        async def execute(self, *_a, **_kw):
            raise AssertionError("nao deveria consultar o banco aqui")

        async def commit(self):
            return None

    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="1")

    async def fake_creds(db, order):
        return creds, None

    async def fake_ensure_doc(db, order):
        return "25598286858"

    async def fake_upsert(*_a, **_kw):
        return None

    async def fake_call(_creds, funcao, _payload):
        if funcao == service.FUNC_POST_ORDEM:
            raise EShipError("eShip webServicePostOrdem retornou erro MOR8003: ja cadastrada")
        if funcao == service.FUNC_GET_ORDEM:
            return {"corpo": {"body": {"dados": [{"ordem": {"id": 3098258}}]}}}
        raise AssertionError(funcao)

    monkeypatch.setattr(service, "_creds_for_order", fake_creds)
    monkeypatch.setattr(service, "ensure_buyer_document", fake_ensure_doc)
    monkeypatch.setattr(service, "upsert_produto", fake_upsert)
    monkeypatch.setattr(service.client, "call", fake_call)

    o = Order(id=1, platform_order_id="ML-9", shipping_mode="flex", buyer_document="25598286858")
    o.items = []
    res = await service.push_order(FakeDB(), o)

    assert res["already_sent"] is True
    assert res["eship_order_id"] == "3098258"
    assert o.eship_order_id == "3098258"   # id recuperado -> o botao Excluir/Atualizar aparece


@pytest.mark.asyncio
async def test_cancel_order_devolve_o_status_ao_que_o_ml_diz(monkeypatch):
    """Cancelou a ordem no WMS -> o "Em Preparacao" (que veio do eShip) vira mentira. O status volta
    a ser o do marketplace ("Pronto p/ Envio"), perguntado ao ML, nao um valor chutado."""
    from models.order import Order
    from integrations.eship.config import EShipCreds

    class FakeAcc:
        id = 1
        platform_user_id = "123"
        access_token = "t"

    class FakeScalar:
        def scalar_one_or_none(self):
            return FakeAcc()

    class FakeDB:
        async def execute(self, *_a, **_kw):
            return FakeScalar()

        async def commit(self):
            return None

    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="1")

    async def fake_creds(db, order):
        return creds, None

    chamadas = []

    async def fake_call(_creds, funcao, _payload):
        chamadas.append(funcao)
        assert funcao == service.FUNC_DELETAR_ORDEM   # DELETE, nao apenas cancelar
        return {"ok": True}

    async def fake_token(acc, db, **_kw):
        return "t"

    async def fake_shipment(token, shipment_id, caller_id=None):
        return {"status": "ready_to_ship"}

    monkeypatch.setattr(service, "_creds_for_order", fake_creds)
    monkeypatch.setattr(service.client, "call", fake_call)
    monkeypatch.setattr(service, "get_valid_token", fake_token)
    monkeypatch.setattr(service._ml, "get_shipment", fake_shipment)

    o = Order(id=1, platform="mercadolivre", platform_order_id="ML-1", account_id=1,
              shipment_id="47504188589", shipment_status="handling",   # "Em Preparacao" (veio do eShip)
              eship_order_id="3098258", eship_dispatch_status="partial",
              eship_nfe_attached=0, eship_label_attached=1)
    await service.cancel_order(FakeDB(), o)

    assert chamadas == [service.FUNC_DELETAR_ORDEM]  # cancelar so nao libera o numeroOrigem
    assert o.shipment_status == "ready_to_ship"      # <- voltou a "Pronto p/ Envio"
    assert o.eship_order_id is None
    assert o.eship_dispatch_status == "cancelled"
    assert o.eship_label_attached == 0
    assert service.order_was_pushed(o) is False      # liberado para novo envio


@pytest.mark.asyncio
async def test_mor8003_com_ordem_cancelada_nao_finge_sucesso(monkeypatch):
    """O eShip NAO libera o numeroOrigem apos o cancelamento: o reenvio bate em MOR8003 e nada e
    criado. Reaproveitar o id da ordem cancelada faria o sistema mostrar sucesso apontando para uma
    ordem morta - foi o que aconteceu com o pedido 2000017373745064 (ordem 3098258, status 10)."""
    from models.order import Order
    from integrations.eship.client import EShipError
    from integrations.eship.config import EShipCreds

    class FakeDB:
        async def execute(self, *_a, **_kw):
            raise AssertionError("nao deveria tocar o banco")

        async def commit(self):
            return None

    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="1")

    async def fake_creds(db, order):
        return creds, None

    async def fake_ensure_doc(db, order):
        return "03577745665"

    async def fake_call(_creds, funcao, _payload):
        if funcao == service.FUNC_POST_ORDEM:
            raise EShipError("MOR8003: N Ordem : '2000017373745064' ja cadastrada")
        if funcao == service.FUNC_GET_ORDEM:
            # status 10 = Cancelada
            return {"corpo": {"body": {"dados": [{"id": 3098258, "status": {"id": 10}}]}}}
        raise AssertionError(funcao)

    monkeypatch.setattr(service, "_creds_for_order", fake_creds)
    monkeypatch.setattr(service, "ensure_buyer_document", fake_ensure_doc)
    monkeypatch.setattr(service.client, "call", fake_call)

    o = Order(id=1, platform_order_id="2000017373745064", shipping_mode="flex",
              buyer_document="03577745665")
    o.items = []

    with pytest.raises(EShipError) as exc:
        await service.push_order(FakeDB(), o)

    assert "cancelada" in str(exc.value).lower()
    assert o.eship_order_id is None          # nao grava o id da ordem morta
    assert service.order_was_pushed(o) is False


def test_eship_cancelada_reconhece_status_10():
    assert service._eship_cancelada(10) is True
    assert service._eship_cancelada(1) is False    # Lancado
    assert service._eship_cancelada(None) is False


@pytest.mark.asyncio
async def test_cancel_order_cancela_antes_se_o_delete_for_recusado(monkeypatch):
    """Se o WMS recusar o DELETE direto, cancela e repete o DELETE - o numeroOrigem PRECISA ser
    liberado, senao o reenvio bate em MOR8003 para sempre."""
    from models.order import Order
    from integrations.eship.client import EShipError
    from integrations.eship.config import EShipCreds

    class FakeDB:
        async def execute(self, *_a, **_kw):
            class R:
                def scalar_one_or_none(self):
                    return None
            return R()

        async def commit(self):
            return None

    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="1")

    async def fake_creds(db, order):
        return creds, None

    chamadas = []

    async def fake_call(_creds, funcao, _payload):
        chamadas.append(funcao)
        if funcao == service.FUNC_DELETAR_ORDEM and len(chamadas) == 1:
            raise EShipError("ordem ativa nao pode ser deletada")
        return {"ok": True}

    monkeypatch.setattr(service, "_creds_for_order", fake_creds)
    monkeypatch.setattr(service.client, "call", fake_call)

    o = Order(id=1, platform="mercadolivre", platform_order_id="ML-1",
              eship_order_id="99", eship_dispatch_status="sent")
    await service.cancel_order(FakeDB(), o)

    assert chamadas == [
        service.FUNC_DELETAR_ORDEM,     # tentou deletar
        service.FUNC_CANCELAR_ORDEM,    # recusado -> cancela
        service.FUNC_DELETAR_ORDEM,     # e deleta de novo
    ]
    assert o.eship_order_id is None
    assert service.order_was_pushed(o) is False


@pytest.mark.asyncio
async def test_touch_order_carimba_a_data_de_atualizacao(monkeypatch):
    """Sem o PUT, a grade do eShip mostra "Sem data de atualizacao registrada". O WMS exige a chave
    `id` (nao aceita `ordem`/`numeroOrigem`) e carimba a hora DELE."""
    from models.order import Order
    from integrations.eship.config import EShipCreds
    from integrations.eship.client import EShipError

    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="1")
    chamadas = []

    async def fake_call(_creds, funcao, payload):
        chamadas.append((funcao, payload))
        return {"ok": True}

    monkeypatch.setattr(service.client, "call", fake_call)

    o = Order(id=1, platform_order_id="ML-1", eship_order_id="3098270")
    assert await service.touch_order(creds, o) is True
    assert chamadas == [(service.FUNC_PUT_ORDEM, {"id": 3098270})]   # int, chave "id"

    # Sem ordem no WMS nao ha o que carimbar.
    assert await service.touch_order(creds, Order(id=2)) is False

    # Falha no carimbo NAO derruba o envio (e complementar).
    async def fake_erro(*_a, **_kw):
        raise EShipError("indisponivel")

    monkeypatch.setattr(service.client, "call", fake_erro)
    assert await service.touch_order(creds, o) is False


def test_zpl_do_zip_extrai_a_etiqueta_de_verdade():
    """O ML entrega o "zpl2" como ZIP (Etiqueta de envio.txt + Controle.pdf), nao como ZPL. Anexar
    o ZIP cru mandava lixo ao WMS."""
    import io, zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Etiqueta de envio.txt", "^XA\n^CI28\n^XZ")
        z.writestr("Controle.pdf", b"%PDF-1.4 fake")
    zpl = service._zpl_do_zip(buf.getvalue())
    assert zpl.startswith(b"^XA")

    assert service._zpl_do_zip(b"^XA direto") == b"^XA direto"   # ja veio ZPL puro
    assert service._zpl_do_zip(b"PKlixo") is None                # zip ilegivel


@pytest.mark.asyncio
async def test_attach_manda_idtipoanexo_inteiro(monkeypatch):
    """Sem idTipoAnexo o WMS RECUSA o ZPL (MIT5002). 7=ZPL, 2=PDF - e precisa ser INTEIRO."""
    from models.order import Order
    from integrations.eship.config import EShipCreds

    creds = EShipCreds(base_url="https://x/v3", api_key="k", warehouse_code="2", cnpj="1")
    enviados = []

    async def fake_creds(db, order):
        return creds, None

    async def fake_call(_creds, funcao, payload):
        enviados.append(payload)
        return {"ok": True}

    monkeypatch.setattr(service, "_creds_for_order", fake_creds)
    monkeypatch.setattr(service.client, "call", fake_call)

    o = Order(id=1, platform_order_id="ML-1")
    await service.attach_label(None, o, b"^XA", extensao="zpl", mime_type="text/plain",
                               id_tipo_anexo=service._ANEXO_ZPL)
    await service.attach_label(None, o, b"%PDF", extensao="pdf",
                               id_tipo_anexo=service._ANEXO_PDF)

    assert enviados[0]["idTipoAnexo"] == 7 and isinstance(enviados[0]["idTipoAnexo"], int)
    assert enviados[0]["extensao"] == "zpl"
    assert enviados[1]["idTipoAnexo"] == 2
    # base64 sempre (requisito do WMS)
    import base64
    assert base64.b64decode(enviados[0]["arquivoBase"]) == b"^XA"


@pytest.mark.asyncio
async def test_nao_reanexa_o_que_o_wms_ja_tem(monkeypatch):
    """A duplicidade do XML: o eShip guardava o arquivo mesmo devolvendo erro fiscal, nos zeravamos
    o selo local e o "Atualizar" anexava de novo. Agora o WMS e a fonte da verdade."""
    from models.order import Order

    class FakeResult:
        rowcount = 1

    class FakeDB:
        async def execute(self, *_a, **_kw):
            return FakeResult()

        async def commit(self):
            return None

    anexados = []

    async def fake_push(db, order):
        order.eship_order_id = "3098270"
        return {"already_sent": True, "eship_order_id": "3098270"}

    # O WMS ja tem TUDO: XML, os 2 PDFs e o ZPL.
    async def fake_cats(db, order):
        return {"xmldanfe": 1, "documentosItPop": 2, "etiqueta": 1}

    async def fake_attach(*_a, **_kw):
        anexados.append(_kw)
        raise AssertionError("nao deveria reanexar nada")

    async def fake_labels(db, order):
        return b"%PDF", b"^XA"

    async def fake_creds(db, order):
        return None, None

    monkeypatch.setattr(service, "push_order", fake_push)
    monkeypatch.setattr(service, "_categorias_anexadas", fake_cats)
    monkeypatch.setattr(service, "_resolve_labels", fake_labels)
    monkeypatch.setattr(service, "attach_label", fake_attach)
    monkeypatch.setattr(service, "attach_nfe_xml", fake_attach)
    monkeypatch.setattr(service, "_creds_for_order", fake_creds)

    o = Order(id=1, platform_order_id="ML-1", shipping_mode="flex")
    res = await service.send_order_full(FakeDB(), o)

    assert anexados == []                       # nada foi reanexado
    assert res["nfe"]["status"] == "already"
    assert res["zpl"]["status"] == "already"
    assert not res["erros"]
    assert o.eship_dispatch_status == "sent"

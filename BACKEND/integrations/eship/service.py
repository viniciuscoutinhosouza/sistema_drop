"""Regras de negócio da integração eShip (WMS).

Payloads e funções alinhados à spec BACKEND/integrations/eship-integracao-api.md.
Credenciais resolvidas por EMPRESA (CMIG): base_url + api_key + warehouse_code.

Fluxo (spec §9): cadastrar produto → criar ordem → anexar NF-e (XML) → anexar
etiqueta → monitorar status (GetOrdem/GetFalhasOrdem). Estoque via GetSaldoEstoque.
"""

import asyncio
import base64
import json
import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.cmig import CMIG
from models.order import Order, OrderItem

from . import client
from .client import EShipError
from .config import EShipCreds, creds_from_cmig
from .status_map import map_status

logger = logging.getLogger(__name__)

# Funções RPC (spec §3-§8)
FUNC_POST_PRODUTO = "webServicePostProduto"
FUNC_GET_PRODUTO = "webServiceGetProduto"
FUNC_POST_ORDEM = "webServicePostOrdem"
FUNC_POST_ORDEM_XML = "webServicePostOrdemPorXml"
FUNC_POST_ARQUIVO = "webServicePostArquivoOrdem"
FUNC_GET_ORDEM = "webServiceGetOrdem"
FUNC_GET_FALHAS = "webServiceGetFalhasOrdem"
FUNC_CANCELAR_ORDEM = "webServiceCancelarOrdem"
FUNC_GET_SALDO = "webServiceGetSaldoEstoque"

# idTipoAnexo (spec §6.3)
ANEXO_XML_NFE = 4   # XMLDANFE
ANEXO_ETIQUETA = 7  # ETIQUETA

# Cadastro em lote: nº máx. de chamadas simultâneas ao WMS (equilíbrio tempo × rajada)
_PUSH_CONCURRENCY = 5


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


async def _creds_for_order(db: AsyncSession, order: Order) -> tuple[EShipCreds | None, CMIG | None]:
    """Resolve credenciais eShip pela CMIG do pedido."""
    if not order.cmig_id:
        return None, None
    cmig = (await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))).scalar_one_or_none()
    if not cmig:
        return None, None
    return creds_from_cmig(cmig), cmig


# ─── Produto (spec §3) ───────────────────────────────────────────────────────


def _produto_payload(sku: str, descricao: str, gtin: str | None, creds: EShipCreds) -> dict:
    """Builder genérico do payload de Cadastrar Produto (spec §3).

    Obrigatórios: codigoSKU, descricao, cnpjCadastro, embalado. gtin opcional.
    """
    return {
        "codigoSKU": (sku or "")[:15],
        "descricao": (descricao or sku or "")[:200],
        "gtin": (gtin or "")[:15],
        "cnpjCadastro": _digits(creds.cnpj),
        "tipo": 1,        # 1 = Simples
        "status": 1,      # 1 = Normal
        "embalado": 1,    # 1 = Embalado (default operacional)
    }


def build_produto_payload(item: OrderItem, creds: EShipCreds, gtin: str | None = None) -> dict:
    """Payload de Cadastrar Produto a partir de um item de pedido.

    `gtin` (EAN) é resolvido pelo caller a partir do produto vinculado, pois o
    OrderItem não armazena o EAN.
    """
    return _produto_payload(item.sku or "", item.title or "", gtin, creds)


async def _resolve_item_ean(db: AsyncSession, item: OrderItem) -> str | None:
    """Resolve o EAN do item a partir do produto vinculado (CMIG ou PG)."""
    from models.cmig import CMIGProduct
    from models.product import CatalogProduct

    if item.cmig_product_id:
        ean = (
            await db.execute(select(CMIGProduct.ean).where(CMIGProduct.id == item.cmig_product_id))
        ).scalar_one_or_none()
        if ean:
            return ean
    if item.catalog_product_id:
        ean = (
            await db.execute(select(CatalogProduct.ean).where(CatalogProduct.id == item.catalog_product_id))
        ).scalar_one_or_none()
        if ean:
            return ean
    return None


async def upsert_produto(creds: EShipCreds, item: OrderItem, gtin: str | None = None) -> None:
    """Garante o produto no eShip antes da ordem (best-effort; não bloqueia)."""
    if not item.sku:
        return
    try:
        await client.call(creds, FUNC_POST_PRODUTO, build_produto_payload(item, creds, gtin))
    except EShipError as e:
        logger.warning("[eShip] upsert produto sku=%s falhou: %s", item.sku, e)


# ─── Cadastro em lote do catálogo da CMIG (pré-cadastro, sem pedido) ──────────


def _variant_descricao(product, variant) -> str:
    """Descrição da variação = título do produto + rótulo (tamanho/cor/voltagem)."""
    extra = " ".join(
        str(v) for v in (variant.size_label, variant.color, variant.voltage, variant.variant_name) if v
    ).strip()
    base = product.title or variant.sku or ""
    return f"{base} {extra}".strip() if extra else base


def _cmig_skus_to_register(products) -> list[dict]:
    """Lista de {sku, descricao, gtin} a cadastrar no WMS para os produtos da CMIG.

    Espelha o que o pedido envia (OrderItem.sku): produto COM variações → 1 entrada por
    variação (SKU da variação, gtin do produto-pai); SEM variações → o próprio produto.
    Ignora entradas sem SKU e dedup por SKU truncado em 15 (limite do WMS).
    """
    out: list[dict] = []
    seen: set[str] = set()
    for p in products:
        variants = list(getattr(p, "variants", None) or [])
        entries = (
            [{"sku": v.sku, "descricao": _variant_descricao(p, v), "gtin": p.ean} for v in variants if v.sku]
            if variants
            else ([{"sku": p.sku_cmig, "descricao": p.title, "gtin": p.ean}] if p.sku_cmig else [])
        )
        for e in entries:
            key = (e["sku"] or "")[:15]
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(e)
    return out


async def push_cmig_products(db: AsyncSession, cmig_id: int) -> dict:
    """Cadastra/atualiza em lote os produtos do catálogo da CMIG no eShip (WMS).

    Idempotente (upsert por SKU). Best-effort: uma falha não aborta as demais; o resultado
    reporta o que foi enviado e o que falhou. Não exige código de armazém (só cadastro).
    """
    from models.cmig import CMIGProduct

    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    creds = creds_from_cmig(cmig)
    if not creds:
        raise EShipError("CMIG sem integração eShip ativa/configurada.")

    products = (
        await db.execute(
            select(CMIGProduct)
            .where(CMIGProduct.cmig_id == cmig_id)
            .options(selectinload(CMIGProduct.variants))
        )
    ).scalars().all()

    skus = _cmig_skus_to_register(products)
    sent_skus: list[str] = []
    errors: list[dict] = []
    # Concorrência limitada: corta o tempo total (evita estourar o timeout do proxy num
    # catálogo grande) sem inundar o WMS de rajada. asyncio é cooperativo → append seguro.
    sem = asyncio.Semaphore(_PUSH_CONCURRENCY)

    async def _one(entry: dict) -> None:
        async with sem:
            try:
                await client.call(creds, FUNC_POST_PRODUTO, _produto_payload(
                    entry["sku"], entry["descricao"], entry["gtin"], creds
                ))
                sent_skus.append(entry["sku"])
            except EShipError as e:
                logger.warning("[eShip] cadastro produto sku=%s falhou: %s", entry["sku"], e)
                errors.append({"sku": entry["sku"], "error": str(e)})

    await asyncio.gather(*[_one(e) for e in skus])
    sent_skus.sort()
    return {
        "total": len(skus),
        "sent": len(sent_skus),
        "failed": len(errors),
        "sent_skus": sent_skus,
        "errors": errors,
    }


# ─── Ordem (spec §4) ─────────────────────────────────────────────────────────


def _parse_address(order: Order) -> dict:
    """Lê o endereço (CLOB JSON) do pedido com aliases tolerantes (ML/normalizado)."""
    raw = {}
    if order.shipping_address:
        try:
            raw = json.loads(order.shipping_address)
        except (ValueError, TypeError):
            raw = {}

    def g(*keys: str) -> str:
        for k in keys:
            v = raw.get(k)
            if v:
                return str(v)
        return ""

    return {
        "logradouro": g("street", "logradouro", "address_line"),
        "numero": g("number", "numero", "street_number"),
        "complemento": g("complement", "complemento", "comment"),
        "bairro": g("neighborhood", "bairro"),
        "municipio": g("city", "municipio", "cidade"),
        "estado": g("state", "estado", "uf", "state_id"),
        "cep": g("zip_code", "cep", "zip", "zip_code_str"),
        "telefone": g("phone", "telefone", "receiver_phone"),
    }


def build_ordem_payload(order: Order, creds: EShipCreds) -> dict:
    """Monta o payload de Inserir Ordem conforme a spec §4.

    Obrigatórios: numeroOrigem, codigoArmazemOrigem, cadastroDestinatario.
    """
    endereco = _parse_address(order)
    doc = _digits(order.buyer_document)
    dest: dict = {
        "nomeDestinatario": order.buyer_name or "",
        "contato": [
            {
                "nome": order.buyer_name or "",
                "email": order.buyer_email or "",
                "telefone": endereco["telefone"],
            }
        ],
        "endereco": endereco,
    }
    if len(doc) == 14:
        dest["cnpjDestinatario"] = doc
    elif len(doc) == 11:
        dest["cpfDestinatario"] = doc

    produtos = []
    for idx, it in enumerate(order.items or [], start=1):
        unit = float(it.unit_price) if it.unit_price is not None else 0.0
        produtos.append(
            {
                "codigoProduto": it.sku or "",
                "quantidadeProduto": it.quantity or 1,
                "infos": {
                    "valorunitrioproduto": f"{unit:.2f}",
                    "valortotalproduto": f"{unit * (it.quantity or 0):.2f}",
                    "nmerolinha": str(idx),
                    "identificadorexterno": str(it.id),
                },
            }
        )

    numero_origem = order.platform_order_id or str(order.id)
    infos_ordem = [
        {
            "ORDCanal de Venda": order.platform or "",
            "ORDValor da ordem": f"{float(order.sale_amount):.2f}" if order.sale_amount else "",
            "ORDNº da Compra Canal de Venda": order.platform_order_id or "",
            "ORDChave": order.nfe_key or "",
        }
    ]

    return {
        "numeroOrigem": numero_origem,
        "codigoArmazemOrigem": creds.warehouse_code or "",
        "cadastroDestinatario": dest,
        "infosOrdem": infos_ordem,
        "produtos": produtos,
    }


def extract_order_id(resp: dict) -> str | None:
    """Extrai o id da ordem da resposta do eShip (chaves tolerantes)."""
    if not isinstance(resp, dict):
        return None
    for key in ("idOrdem", "ordem", "id", "orderId", "codigo", "codigoOrdem"):
        if resp.get(key):
            return str(resp[key])
    data = resp.get("data") or resp.get("retorno") or {}
    if isinstance(data, dict):
        for key in ("idOrdem", "ordem", "id", "codigoOrdem"):
            if data.get(key):
                return str(data[key])
    return None


def extract_status(resp: dict) -> tuple[str | None, str | None, str | None]:
    """(status_eship, tracking_code, tracking_url) da resposta de GetOrdem."""
    if not isinstance(resp, dict):
        return None, None, None
    node = resp.get("data") or resp.get("retorno") or resp
    if isinstance(node, list) and node:
        node = node[0]
    if not isinstance(node, dict):
        return None, None, None
    status = node.get("status") or node.get("statusObjeto") or node.get("situacao")
    rastreio = node.get("rastreio") or node.get("codigoRastreio") or node.get("tracking")
    url = node.get("urlRastreio") or node.get("trackingUrl") or node.get("ORDUrl externa")
    return status, rastreio, url


# ─── Orquestração ────────────────────────────────────────────────────────────


async def push_order(db: AsyncSession, order: Order) -> dict:
    """Envia o pedido ao eShip da empresa (CMIG). Idempotente por eship_order_id."""
    if order.eship_order_id:
        return {"already_sent": True, "eship_order_id": order.eship_order_id}

    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    if not creds.warehouse_code:
        raise EShipError("Configure o código do armazém (codigoArmazemOrigem) na CMIG antes de enviar.")

    for item in order.items or []:
        ean = await _resolve_item_ean(db, item)
        await upsert_produto(creds, item, gtin=ean)

    resp = await client.call(creds, FUNC_POST_ORDEM, build_ordem_payload(order, creds))
    eship_id = extract_order_id(resp) or (order.platform_order_id or str(order.id))
    order.eship_order_id = eship_id
    await db.commit()
    return {"already_sent": False, "eship_order_id": eship_id, "response": resp}


async def push_order_by_xml(db: AsyncSession, order: Order, xml_content: str,
                            id_fila: int | None = None, tipo_ordem: int | None = None) -> dict:
    """Cria a ordem já processando o XML da NF-e (spec §5)."""
    if order.eship_order_id:
        return {"already_sent": True, "eship_order_id": order.eship_order_id}
    creds, cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")

    payload: dict = {
        "cnpjRemetente": _digits(creds.cnpj),
        "codigoArmazem": creds.warehouse_code or "",
        "conteudo": xml_content,
    }
    if tipo_ordem is not None:
        payload["tipoOrdem"] = tipo_ordem
    if id_fila is not None:
        payload["idFila"] = id_fila

    resp = await client.call(creds, FUNC_POST_ORDEM_XML, payload)
    eship_id = extract_order_id(resp) or (order.platform_order_id or str(order.id))
    order.eship_order_id = eship_id
    await db.commit()
    return {"already_sent": False, "eship_order_id": eship_id, "response": resp}


async def attach_file(db: AsyncSession, order: Order, *, content: bytes, extensao: str,
                      mime_type: str, id_tipo_anexo: int, inserir_fiscal: bool = False,
                      atualizar_transporte: bool = False) -> dict:
    """Anexa um arquivo (NF-e XML, DANFE PDF, etiqueta) a uma ordem existente (spec §6)."""
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    payload = {
        "numeroOrigem": order.platform_order_id or str(order.id),
        "arquivoBase": base64.b64encode(content).decode(),
        "extensao": extensao,
        "mimeType": mime_type,
        "idTipoAnexo": id_tipo_anexo,
    }
    if inserir_fiscal:
        payload["inserirFiscal"] = "1"
    if atualizar_transporte:
        payload["atualizarTransporte"] = "1"
        payload["cadastrarTransporte"] = "1"
    return await client.call(creds, FUNC_POST_ARQUIVO, payload)


async def attach_nfe_xml(db: AsyncSession, order: Order, xml_content: bytes) -> dict:
    """Anexa o XML da NF-e (idTipoAnexo=4) atualizando dados fiscais e transporte."""
    return await attach_file(
        db, order, content=xml_content, extensao="xml", mime_type="application/xml",
        id_tipo_anexo=ANEXO_XML_NFE, inserir_fiscal=True, atualizar_transporte=True,
    )


async def attach_label(db: AsyncSession, order: Order, content: bytes,
                       extensao: str = "pdf", mime_type: str = "application/pdf") -> dict:
    """Anexa a etiqueta de entrega (idTipoAnexo=7)."""
    return await attach_file(
        db, order, content=content, extensao=extensao, mime_type=mime_type,
        id_tipo_anexo=ANEXO_ETIQUETA,
    )


async def cancel_order(db: AsyncSession, order: Order) -> dict:
    """Cancela a ordem no eShip (spec §7)."""
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    resp = await client.call(
        creds, FUNC_CANCELAR_ORDEM,
        {"numeroOrigem": order.platform_order_id or str(order.id)},
    )
    return resp


async def get_falhas(db: AsyncSession, order: Order) -> dict:
    """Consulta falhas de processamento da ordem (spec §7)."""
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    return await client.call(
        creds, FUNC_GET_FALHAS,
        {"numeroOrigem": order.platform_order_id or str(order.id)},
    )


def _eship_produto_row(p: dict) -> dict:
    """Extrai os campos relevantes (info + estoque) de um produto do GetProduto."""
    cad = p.get("cadastro") if isinstance(p.get("cadastro"), dict) else {}
    st = p.get("status") if isinstance(p.get("status"), dict) else {}
    tp = p.get("tipo") if isinstance(p.get("tipo"), dict) else {}
    return {
        "codigo": p.get("codigo"),
        "codigo_barras": p.get("codigoBarras"),
        "descricao": p.get("descricao"),
        "empresa": cad.get("nome"),
        "status": st.get("descricao"),
        "tipo": tp.get("descricao"),
        "is_full": bool(p.get("itsFull")),
        "total_fisico": p.get("totalFisico"),
        "total_disponivel": p.get("totalDisponivel"),
        "total_reservado": p.get("totalReservado"),
        "total_enderecado": p.get("totalEnderecado"),
        "peso_bruto": p.get("pesoBruto"),
    }


async def list_eship_products(db: AsyncSession, cmig_id: int, page: int = 1) -> dict:
    """Lista os produtos cadastrados no eShip (WMS) com info + estoque, paginado.

    O eShip pagina por `pagina` (25/página) e não filtra por SKU/texto via API — a
    busca é feita no frontend sobre a página carregada.
    """
    creds = creds_from_cmig(
        (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    )
    if not creds:
        raise EShipError("CMIG sem integração eShip ativa/configurada.")
    resp = await client.call(creds, FUNC_GET_PRODUTO, {"pagina": max(1, int(page or 1))})
    body = ((resp or {}).get("corpo") or {}).get("body") or {}
    pag = body.get("dadosPaginacao") or {}
    return {
        "produtos": [_eship_produto_row(p) for p in (body.get("dados") or [])],
        "pagina": pag.get("paginaAtual") or page,
        "paginas": pag.get("quantidadePaginas"),
        "total": pag.get("totalObjetos"),
        "por_pagina": pag.get("registrosPorPagina"),
    }


async def get_saldo_estoque(db: AsyncSession, cmig_id: int, sku: str | None = None) -> dict:
    """Consulta saldo de estoque no eShip (WMS = fonte de verdade do físico). spec §8."""
    creds = creds_from_cmig(
        (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    )
    if not creds:
        raise EShipError("CMIG sem integração eShip ativa/configurada.")
    payload = {"codigoSKU": sku} if sku else {}
    return await client.call(creds, FUNC_GET_SALDO, payload)


async def sync_order_status(db: AsyncSession, order: Order) -> bool:
    """Consulta o status da ordem no eShip (GetOrdem) e atualiza o Order."""
    if not order.eship_order_id:
        return False
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        return False

    resp = await client.call(
        creds, FUNC_GET_ORDEM, {"numeroOrigem": order.platform_order_id or str(order.id)}
    )
    raw_status, tracking, url = extract_status(resp)
    ship_status, order_status = map_status(raw_status)

    changed = False
    if ship_status and ship_status != order.shipment_status:
        order.shipment_status = ship_status
        changed = True
    if tracking and tracking != order.tracking_code:
        order.tracking_code = tracking
        changed = True
    if url and url != order.tracking_url:
        order.tracking_url = url
        changed = True
    if order_status and order.status != order_status:
        order.status = order_status
        if order_status == "shipped" and not order.dispatched_at:
            order.dispatched_at = datetime.now(UTC)
        changed = True

    if changed:
        await db.commit()
    return changed

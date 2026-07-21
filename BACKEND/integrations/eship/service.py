"""Regras de negócio da integração eShip (WMS).

Payloads e funções alinhados à spec BACKEND/integrations/eship-integracao-api.md.
Credenciais resolvidas por EMPRESA (CMIG): base_url + api_key + warehouse_code.

Fluxo (spec §9): cadastrar produto → criar ordem → anexar NF-e (XML) → anexar
etiqueta → monitorar status (GetOrdem/GetFalhasOrdem). Estoque via GetSaldoEstoque.
"""

import asyncio
import base64
import io
import json
import logging
import re
import time
import zipfile
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.cmig import CMIG
from models.integration import MarketplaceAccount
from models.order import Order, OrderItem
from services import ml_service as _ml
from services.datetime_br import iso_utc
from services.fiscal.order_docs import resolve_nfe_xml
from services.ml_auth import get_valid_token

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
FUNC_GET_ANEXOS = "webServiceGetAnexosOrdem"   # arquivos anexados à ordem (conferência)
# Atualiza a ordem. Exige a chave `id` (o id do WMS — NÃO aceita `ordem`/`numeroOrigem`). Um PUT
# só com o `id` carimba o `dataHoraAtualizacao` ("Data da última atualização", coluna da grade do
# eShip) sem tocar em produtos/infos/anexos/status — verificado em produção.
FUNC_PUT_ORDEM = "webServicePutOrdem"

# `idTipoAnexo` do webServicePostArquivoOrdem — INTEIRO. Descoberto testando contra a API real:
#   2 → PDF  (etiqueta e DANFE) → cai na categoria `documentosItPop`
#   7 → ZPL  (etiqueta térmica)  → cai na categoria `etiqueta`
# Sem o `idTipoAnexo`, o ZPL é RECUSADO ("MIT5002 - Tipo de arquivo não aceito, zpl").
# O XML da NF-e não usa idTipoAnexo: vai por `inserirFiscal` e cai em `xmldanfe`.
_ANEXO_PDF = 2
_ANEXO_ZPL = 7
FUNC_GET_FALHAS = "webServiceGetFalhasOrdem"
# Nome real no spec: "webServiceCancelaOrdem" (SEM o "r" — webServiceCancelarOrdem não existe).
FUNC_CANCELAR_ORDEM = "webServiceCancelaOrdem"
# CANCELAR **não basta**: o eShip mantém o `numeroOrigem` ocupado pela ordem cancelada, e o reenvio
# bate em "MOR8003: Nº Ordem já cadastrada". Só o DELETE remove a ordem e libera o número (validado
# em produção: após o delete, o GetOrdem devolve 0 registros).
FUNC_DELETAR_ORDEM = "webServiceDeleteOrdem"
FUNC_GET_SALDO = "webServiceGetSaldoEstoque"

# O anexo NÃO usa `idTipoAnexo` (campo inexistente no spec real): o tipo é inferido pelas
# flags inserirFiscal/atualizarTransporte + a extensão do arquivo (xml/pdf/zpl).
_XML_PROLOG_RE = re.compile(rb"^\s*<\?xml[^>]*\?>\s*")

# TTL do lock de envio ("sending"): passado esse tempo, um lock órfão (processo morto no meio)
# pode ser retomado. Sem isso, um crash travava o pedido para sempre.
_LOCK_TTL = timedelta(minutes=10)

# Cadastro em lote: nº máx. de chamadas simultâneas ao WMS (equilíbrio tempo × rajada)
_PUSH_CONCURRENCY = 5
# Listagem do catálogo inteiro: concorrência de páginas, teto de segurança e cache
_PRODUTOS_FETCH_CONCURRENCY = 12
_PRODUTOS_MAX_PAGES = 300
# Registros por página do GetProduto: 100 é o teto que a API HONRA (200/500 são ignorados
# e caem p/ 25). Reduz o nº de páginas ~4x (ex.: 304→76) na varredura do catálogo.
_PRODUTOS_PAGE_SIZE = 100
_PRODUTOS_TOTAL_DEADLINE = 45  # segundos — teto agregado da carga (abaixo do proxy_read_timeout)
_PRODUTOS_CACHE_TTL = 300  # segundos — evita re-buscar o catálogo inteiro a cada abertura
# Varredura do saldo (GetSaldoEstoque já vem escopado ao depósito da conta — costuma ser 1 pág)
_SALDO_MAX_PAGES = 100
_produtos_cache: dict[int, tuple[float, dict]] = {}
# Cache curto da varredura de ORDENS por endpoint (base_url, api_key). Evita martelar o WMS em
# cliques repetidos de "Atualizar" e no consolidado (N CMIGs / 1 endpoint) — ainda "ao vivo".
_ORDENS_SCAN_TTL = 15  # segundos
_ordens_scan_cache: dict[tuple, tuple[float, dict]] = {}


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _produto_da_cmig(p: dict, cnpj: str, cpf: str) -> bool:
    """True se o produto (cadastro do WMS) pertence à empresa (CNPJ/CPF, só dígitos).

    O WMS é multi-tenant e a API **ignora** os filtros de empresa do `webServiceGetProduto`
    (comprovado ao vivo) — o escopo por empresa é feito aqui, no cliente, casando
    `cadastro.cnpj`/`cadastro.cpf` do produto. `cnpj`/`cpf` já devem vir só com dígitos.
    """
    cad = p.get("cadastro") if isinstance(p.get("cadastro"), dict) else {}
    return (bool(cnpj) and _digits(cad.get("cnpj")) == cnpj) or (
        bool(cpf) and _digits(cad.get("cpf")) == cpf
    )


def _num(v) -> float | int:
    """Converte '20.0000'/'0.00000' (string do saldo) em número (int se inteiro)."""
    try:
        f = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0
    return int(f) if f == int(f) else round(f, 3)


async def _fetch_saldo_indexes(creds: EShipCreds) -> tuple[dict, dict]:
    """Varre o `webServiceGetSaldoEstoque` (já escopado ao depósito da CONTA) e indexa o
    saldo por `pro_produto_id` e por `codigo` (SKU). Soma linhas (depósitos/lotes) do mesmo
    produto. O GetProduto NÃO traz estoque na listagem — o saldo real vem daqui.

    Retorna `(por_id, por_codigo)` onde cada valor é `[fisico, disponivel, reservado]`.
    Best-effort: se o saldo falhar, devolve mapas vazios (produtos ficam com 0).
    """
    por_id: dict[str, list] = {}
    por_cod: dict[str, list] = {}
    page = 1
    try:
        while page <= _SALDO_MAX_PAGES:
            r = await client.call(
                creds, FUNC_GET_SALDO, {"pagina": page, "quantidadeRegistros": _PRODUTOS_PAGE_SIZE}
            )
            body = ((r or {}).get("corpo") or {}).get("body") or {}
            for ln in (body.get("dados") or []):
                fis, dis, res = _num(ln.get("saldo")), _num(ln.get("saldodisponivel")), _num(ln.get("saldoreservado"))
                pid = str(ln.get("pro_produto_id") or "").strip()
                cod = str(ln.get("codigo") or "").strip()
                for key, index in ((pid, por_id), (cod, por_cod)):
                    if not key:
                        continue
                    t = index.setdefault(key, [0, 0, 0])
                    t[0] += fis
                    t[1] += dis
                    t[2] += res
            pag = body.get("dadosPaginacao") or {}
            try:
                total_pages = int(pag.get("quantidadePaginas") or 1)
            except (ValueError, TypeError):
                total_pages = 1
            if page >= total_pages:
                break
            page += 1
    except EShipError as e:
        logger.warning("[eShip] GetSaldoEstoque falhou: %s", e)
    return por_id, por_cod


def _saldo_for(p: dict, por_id: dict, por_cod: dict) -> list | None:
    """Saldo `[fisico, disponivel, reservado]` do produto, casando por id (== pro_produto_id)
    e caindo para o SKU (`codigo`) se preciso."""
    pid = str(p.get("id") or "").strip()
    cod = str(p.get("codigo") or "").strip()
    return por_id.get(pid) or por_cod.get(cod)


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


def _addr_text(v) -> str:
    """Texto de um campo de endereço que pode vir como string, dict `{id,name}` do ML,
    ou dict já serializado em string (bug antigo). Devolve o `name`/valor limpo."""
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(v.get("name") or v.get("id") or "").strip()
    s = str(v)
    if s.startswith("{") and "name" in s:
        try:
            import ast

            d = ast.literal_eval(s)
            if isinstance(d, dict):
                return str(d.get("name") or d.get("id") or "").strip()
        except (ValueError, SyntaxError):
            pass
    return s.strip()


def _uf_sigla(v) -> str:
    """UF (2 letras) do estado do ML: `{id:'BR-SP'}` → 'SP'; senão nome/sigla."""
    raw_id = v.get("id") if isinstance(v, dict) else ""
    raw_id = str(raw_id or "")
    if "-" in raw_id:
        cand = raw_id.split("-")[-1].strip()
        if len(cand) == 2:
            return cand.upper()
    name = _addr_text(v)
    return name.upper() if len(name) == 2 else name


def _parse_address(order: Order) -> dict:
    """Lê o endereço (CLOB JSON) do pedido com aliases tolerantes (ML/normalizado).

    Os campos do ML `city`/`state`/`neighborhood` chegam como objetos `{id, name}` — precisam
    ser desembrulhados (senão o WMS recebe o dict serializado). `estado` vai como UF (2 letras).
    """
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
                return _addr_text(v)
        return ""

    def gv(*keys: str):
        for k in keys:
            v = raw.get(k)
            if v:
                return v
        return None

    # O ML mascara o telefone do comprador ("XXXXXXX"). Mandar essa máscara ao WMS é pior que
    # mandar vazio (o exemplo oficial do eShip manda ""), então só vai telefone que tenha dígitos.
    telefone = g("phone", "telefone", "receiver_phone")
    if not any(ch.isdigit() for ch in telefone):
        telefone = ""

    return {
        "logradouro": g("street", "logradouro", "address_line"),
        "numero": g("number", "numero", "street_number"),
        "complemento": g("complement", "complemento", "comment"),
        "bairro": g("neighborhood", "bairro"),
        "municipio": g("city", "municipio", "cidade"),
        "estado": _uf_sigla(gv("state", "estado", "uf", "state_id")),
        "cep": g("zip_code", "cep", "zip", "zip_code_str"),
        "telefone": telefone,
    }


async def ensure_buyer_document(db: AsyncSession, order: Order) -> str:
    """Garante o CPF/CNPJ do comprador — o eShip exige `cpfDestinatario` OU `cnpjDestinatario`.

    O ML **não devolve mais** o documento em `GET /orders/{id}` (privacidade): `buyer.identification`
    sumiu, e por isso `order.buyer_document` nascia nulo em todos os pedidos. O documento vive em
    `GET /orders/{id}/billing_info` (x-version: 2) e é buscado aqui e persistido. Para destinatário
    **PJ** também capturamos a **razão social** (`billing_info.name`), que o eShip exige
    (`razaoSocialDestinatario`) — então buscamos o billing_info também quando o doc já existe mas a
    razão social ainda falta num CNPJ.

    Retorna o documento em dígitos ('' se indisponível).
    """
    doc = _digits(order.buyer_document)
    have_doc = len(doc) in (11, 14)
    is_pj = (order.buyer_document_type or "").upper() == "CNPJ" or (have_doc and len(doc) == 14)
    need_razao = is_pj and not (order.buyer_business_name or "").strip()
    if have_doc and not need_razao:
        return doc  # já temos tudo que o eShip precisa
    if order.platform != "mercadolivre" or not order.platform_order_id:
        return doc

    acc = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
        )
    ).scalar_one_or_none()
    if not acc or not acc.access_token:
        return doc

    # `get_valid_token` renova sob lock quando o token está vencido — o billing_info responde 401
    # com token velho, e aí o pedido iria ao WMS sem documento/razão social.
    try:
        token = await get_valid_token(acc, db)
    except Exception as exc:  # noqa: BLE001 — conta desconectada/refresh falhou
        logger.warning("[eShip] pedido=%s: token ML indisponível: %s", order.id, exc)
        return doc

    info = await _ml.get_order_billing_info(token, order.platform_order_id)
    billing = ((info.get("buyer") or {}).get("billing_info") or {})
    ident = billing.get("identification") or {}
    new_doc = _digits(ident.get("number"))
    tipo = (ident.get("type") or "").upper()
    changed = False
    if len(new_doc) in (11, 14):
        order.buyer_document = new_doc
        order.buyer_document_type = tipo if tipo in ("CPF", "CNPJ") else None
        doc = new_doc
        changed = True
    # Razão social do PJ: o eShip exige `razaoSocialDestinatario` p/ CNPJ ainda não cadastrado.
    # `billing_info.name` é o nome fiscal (razão social do PJ). Guardamos sempre que vier.
    razao = (billing.get("name") or "").strip()
    if razao and razao != (order.buyer_business_name or ""):
        order.buyer_business_name = razao[:255]
        changed = True
    if changed:
        await db.commit()
    return doc


# Código de transporte (codigoTransporte) do eShip é POR-CMIG (cada cadastro tem os SEUS transportes).
#
# Confirmado ao vivo (2026-07-21): a LPS (cmig 21) tem "01" (Correios) e o PostOrdem aceita; a MIG
# (cmig 1) NÃO tem "01" no cadastro dela e o PostOrdem **recusa** (MOR9347), derrubando o envio —
# mesmo a MIG mostrando CORREIOS nas ordens (esse vem do XML da NF-e, não de um codigoTransporte).
# Por isso: só enviamos o bloco `transporte` para CMIGs com código CONFIRMADO; as demais vão SEM
# transporte (comportamento antigo — a transportadora vem do XML da nota), para NÃO quebrar o envio.
#
# ATENÇÃO: código inexistente para a CMIG = MOR9347 (PostOrdem) ou timeout (PutOrdem). Nunca colocar
# um código aqui sem validar ao vivo naquela CMIG. Preencher conforme o dono confirmar cada cadastro.
_TRANSPORTE_POR_CMIG: dict[int, str] = {
    21: "01",   # LPS Mercado Place — Correios (validado ao vivo)
}


def transporte_code_for_order(order: Order) -> str | None:
    """codigoTransporte do eShip para a CMIG do pedido, ou None se não há código confirmado."""
    return _TRANSPORTE_POR_CMIG.get(order.cmig_id)


def build_ordem_payload(order: Order, creds: EShipCreds) -> dict:
    """Monta o payload de Inserir Ordem conforme a spec §4.

    Obrigatórios: numeroOrigem, codigoArmazemOrigem, cadastroDestinatario (com CPF **ou** CNPJ).
    """
    endereco = _parse_address(order)
    doc = _digits(order.buyer_document)
    dest: dict = {}

    # O documento vai PRIMEIRO, como no exemplo oficial (.claude/eSHIP.md). Em JSON a ordem das
    # chaves é irrelevante para o servidor, mas quem confere a prévia lê de cima para baixo — com o
    # CPF no fim do bloco, "cadê o cpfDestinatario?" vira uma dúvida recorrente.
    #
    # O tipo vem do ML (billing_info). Só caímos no comprimento quando o tipo não foi informado —
    # um CPF que tenha perdido o zero à esquerda em algum cadastro manual não vira "CNPJ" por engano.
    tipo = (order.buyer_document_type or "").upper()
    is_cnpj = tipo == "CNPJ" or (not tipo and len(doc) == 14)
    if is_cnpj:
        dest["cnpjDestinatario"] = doc
        # Destinatário PJ: o eShip recusa (MCA9102) se `razaoSocialDestinatario` vier vazio
        # quando o CNPJ ainda não tem cadastro no WMS. Razão social = billing_info.name (PJ);
        # cai p/ buyer_name se, por algum motivo, a razão social não foi capturada.
        dest["razaoSocialDestinatario"] = order.buyer_business_name or order.buyer_name or ""
    elif tipo == "CPF" or (not tipo and len(doc) == 11):
        dest["cpfDestinatario"] = doc

    dest["nomeDestinatario"] = order.buyer_name or ""
    dest["contato"] = [
        {
            "nome": order.buyer_name or "",
            "email": order.buyer_email or "",
            "telefone": endereco["telefone"],
        }
    ]
    dest["endereco"] = endereco

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

    payload = {
        "numeroOrigem": numero_origem,
        "codigoArmazemOrigem": creds.warehouse_code or "",
    }
    # `idTipo` e `tipoOrdem` vêm do cadastro da empresa DENTRO do eShip (variam por CMIG —
    # ex. MIG: 104 / "MIG IMPORTACOES"). Só entram quando configurados; ver .claude/eSHIP.md.
    if creds.id_tipo is not None:
        payload["idTipo"] = creds.id_tipo
    if creds.tipo_ordem:
        payload["tipoOrdem"] = creds.tipo_ordem

    payload["cadastroDestinatario"] = dest
    payload["infosOrdem"] = infos_ordem
    payload["produtos"] = produtos
    # Transporte (transportadora): bloco `transporte.codigoTransporte`. Só entra quando há código
    # CONFIRMADO para a CMIG (ver transporte_code_for_order) — código inexistente para o cadastro
    # faz o PostOrdem recusar (MOR9347) e derruba o envio. Sem código → ordem vai sem transporte
    # (como antes; a transportadora vem do XML da NF-e).
    _cod_transp = transporte_code_for_order(order)
    if _cod_transp:
        payload["transporte"] = {"codigoTransporte": _cod_transp}
    return payload


def _coax_id(v) -> str | None:
    """Normaliza um valor de id que pode vir como escalar ou objeto aninhado (`{id: ...}`)."""
    if isinstance(v, dict):
        v = v.get("id")
    return str(v) if v not in (None, "") else None


_APIKEY_PLACEHOLDER = "SUA_APIKEY_ESHIP"


async def preview_ordem(db: AsyncSession, order: Order) -> dict:
    """Monta a PRÉVIA do `webServicePostOrdem` (payload + curl) SEM executar nada.

    Para depurar o envio: mostra exatamente o corpo que o `push_order` mandaria. A apikey
    NUNCA é exposta (princípio do módulo — a apikey não sai do backend); o curl traz um
    placeholder. Para testar de fato, cole a Função + Body no Console de API do eShip
    (que injeta a apikey no header) ou substitua o placeholder no curl.
    """
    creds, cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    # Busca/persiste o CPF/CNPJ para que a prévia mostre o MESMO corpo que o envio real mandaria
    # (sem isso a prévia sairia sem o documento, escondendo o problema).
    await ensure_buyer_document(db, order)
    body = build_ordem_payload(order, creds)

    # A prévia PRECISA denunciar o que falta — antes ela apenas omitia o campo em silêncio, e o
    # erro só aparecia lá no WMS. Cada bloqueio vira um aviso explícito na tela.
    dest = body.get("cadastroDestinatario") or {}
    bloqueios: list[str] = []
    if not (dest.get("cpfDestinatario") or dest.get("cnpjDestinatario")):
        bloqueios.append(
            "Falta o CPF/CNPJ do destinatário (obrigatório no eShip). O documento vem do Mercado "
            "Livre (billing_info) e só existe após o pagamento aprovado — se o pedido já está pago, "
            "verifique se a conta ML está conectada (Integrações)."
        )
    # Destinatário PJ sem razão social: o eShip recusa (MCA9102) ao criar o cadastro do CNPJ.
    if dest.get("cnpjDestinatario") and not (dest.get("razaoSocialDestinatario") or "").strip():
        bloqueios.append(
            "Destinatário é CNPJ (PJ) mas falta a razão social (razaoSocialDestinatario) — o eShip "
            "recusa (MCA9102) ao cadastrar o CNPJ. A razão social vem do Mercado Livre "
            "(billing_info) e só existe após o pagamento aprovado; confirme se a conta ML está "
            "conectada (Integrações)."
        )
    if not creds.warehouse_code:
        bloqueios.append("Falta o código do armazém (codigoArmazemOrigem) na configuração da CMIG.")
    if not body.get("produtos"):
        bloqueios.append("O pedido não tem itens para enviar.")

    # AVISOS (não impedem, mas exigem confirmação): a Ordem pode ser criada sem NF-e/etiqueta, e
    # foi o que aconteceu — pedidos foram parar no WMS sem documento nem etiqueta. Usa as MESMAS
    # funções do envio real, então o que a prévia diz é o que o envio faria, não um palpite.
    avisos: list[str] = []
    if not order.eship_nfe_attached and not await resolve_nfe_xml(db, order):
        avisos.append("NF-e ainda não autorizada — a ordem irá ao WMS SEM o XML da nota.")
    if not order.eship_label_attached and not (await _resolve_labels(db, order))[0]:
        avisos.append("Etiqueta ainda não liberada pelo Mercado Livre — a ordem irá SEM etiqueta.")

    url = f"{(creds.base_url or '').rstrip('/')}/?api&funcao={FUNC_POST_ORDEM}"
    body_json = json.dumps(body, ensure_ascii=False)
    curl = (
        f"curl -s '{url}' \\\n"
        f"  -H 'api: {_APIKEY_PLACEHOLDER}' -H 'Content-Type: application/json' \\\n"
        f"  -d '{body_json}'"
    )
    return {
        "funcao": FUNC_POST_ORDEM,
        "url": url,
        "cmig_id": getattr(cmig, "id", None),
        "warehouse_code": creds.warehouse_code,
        "bloqueios": bloqueios,
        "avisos": avisos,
        "body": body,
        "curl": curl,
    }


def extract_order_id(resp: dict) -> str | None:
    """Extrai o id da ordem da resposta do eShip.

    O `webServicePostOrdem` responde `{"ordem": {"id": ..., "status": {...}}}` — o id é
    **aninhado** em `ordem.id`. Mantém a cadeia tolerante para outros formatos, mas só
    aceita o valor quando resolve para um escalar (nunca serializa o dict inteiro).
    """
    if not isinstance(resp, dict):
        return None
    _CHAVES = ("idOrdem", "ordem", "id", "orderId", "codigo", "codigoOrdem")

    for key in _CHAVES:
        if key in resp:
            got = _coax_id(resp[key])
            if got:
                return got

    # Envelope REAL do eShip: `corpo.body.dados`. ATENÇÃO: no PostOrdem o `dados` vem como
    # **objeto** (`{"ordem": {"id": 3098257, ...}}`), enquanto nas consultas vem como **lista**.
    # Tratar só a lista fazia o id da ordem se perder: o WMS criava a ordem, o sistema gravava
    # id nulo, e o clique seguinte tentava criar de novo → "MOR8003: Nº Ordem já cadastrada".
    corpo = resp.get("corpo")
    body = corpo.get("body") if isinstance(corpo, dict) else None
    dados = body.get("dados") if isinstance(body, dict) else None
    if isinstance(dados, list) and dados:
        dados = dados[0]
    if isinstance(dados, dict):
        for key in _CHAVES:
            if key in dados:
                got = _coax_id(dados[key])
                if got:
                    return got

    data = resp.get("data") or resp.get("retorno") or {}
    if isinstance(data, dict):
        for key in ("idOrdem", "ordem", "id", "codigoOrdem"):
            if key in data:
                got = _coax_id(data[key])
                if got:
                    return got
    return None


def extract_status(resp: dict) -> tuple[int | str | None, str | None, str | None]:
    """(status_id, tracking_code, tracking_url) da resposta do GetOrdem.

    O envelope real é `corpo.body.dados[]` e o status é o **objeto** `{id, descricao, cor}`;
    devolvemos o `status.id` (numérico) para mapear por id (nunca por texto/acento).
    """
    if not isinstance(resp, dict):
        return None, None, None
    node = None
    corpo = resp.get("corpo")
    body = corpo.get("body") if isinstance(corpo, dict) else None
    dados = body.get("dados") if isinstance(body, dict) else None
    if isinstance(dados, list) and dados:
        node = dados[0]
    elif isinstance(dados, dict):
        node = dados
    if node is None:
        # Fallbacks p/ formatos antigos/planos.
        node = resp.get("ordem") or resp.get("data") or resp.get("retorno") or resp
        if isinstance(node, list) and node:
            node = node[0]
    if not isinstance(node, dict):
        return None, None, None
    status = node.get("status")
    status_id = status.get("id") if isinstance(status, dict) else status
    rastreio = (
        node.get("codigoRastreamento")
        or node.get("rastreio")
        or node.get("codigoRastreio")
        or node.get("tracking")
    )
    url = node.get("urlRastreio") or node.get("trackingUrl") or node.get("ORDUrl externa")
    return status_id, rastreio, url


# ─── Orquestração ────────────────────────────────────────────────────────────


def _is_full_order(order: Order) -> bool:
    """Pedido FULL (fulfillment) é gerido pelo ML e NÃO vai ao WMS (ADR-0008/0010)."""
    return (order.shipping_mode or "").lower() == "full" or "fulfillment" in (
        order.shipping_method or ""
    ).lower()


def order_was_pushed(order: Order) -> bool:
    """A ordem já existe no WMS? Não basta olhar o `eship_order_id`: o eShip pode aceitar a ordem
    sem devolver um id extraível. Nesse caso o despacho fica 'sent'/'partial' com id nulo — e
    recriar a ordem duplicaria no WMS."""
    return bool(order.eship_order_id) or (order.eship_dispatch_status in ("sent", "partial"))


def _ja_cadastrada(err: Exception) -> bool:
    """O eShip recusou porque a ordem JÁ EXISTE lá (código MOR8003)."""
    msg = str(err).lower()
    return "mor8003" in msg or "já cadastrada" in msg or "ja cadastrada" in msg


def _eship_cancelada(status_id) -> bool:
    """A ordem no eShip está cancelada? (status 10 = Cancelada — ver status_map)."""
    ship_status, _ = map_status(status_id)
    return ship_status == "cancelled"


async def _fetch_eship_order(creds: EShipCreds, order: Order) -> tuple[str | None, object]:
    """Consulta a ordem já existente no eShip → (id, status_id). (None, None) se não descobrir."""
    try:
        resp = await client.call(
            creds,
            FUNC_GET_ORDEM,
            {
                "numeroOrigem": order.platform_order_id or str(order.id),
                "incluirInfo": True,
                "pagina": 1,
            },
        )
        status_id, _tracking, _url = extract_status(resp)
        return extract_order_id(resp), status_id
    except EShipError as exc:
        logger.warning("[eShip] pedido=%s: falha ao consultar a ordem existente: %s", order.id, exc)
        return None, None


async def push_order(db: AsyncSession, order: Order) -> dict:
    """Envia o pedido ao eShip da empresa (CMIG). Idempotente (ver `order_was_pushed`)."""
    if _is_full_order(order):
        raise EShipError("Pedido FULL é gerido pelo Mercado Livre — não vai ao WMS (eShip).")
    if order_was_pushed(order):
        return {"already_sent": True, "eship_order_id": order.eship_order_id}

    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    if not creds.warehouse_code:
        raise EShipError("Configure o código do armazém (codigoArmazemOrigem) na CMIG antes de enviar.")

    # CPF/CNPJ do destinatário é OBRIGATÓRIO no eShip. Falha aqui, com motivo claro, em vez de
    # deixar o WMS recusar uma ordem incompleta.
    if not await ensure_buyer_document(db, order):
        raise EShipError(
            "CPF/CNPJ do comprador indisponível — o eShip exige o documento do destinatário. "
            "O Mercado Livre só o fornece após o pagamento aprovado (billing_info)."
        )

    for item in order.items or []:
        ean = await _resolve_item_ean(db, item)
        await upsert_produto(creds, item, gtin=ean)

    try:
        resp = await client.call(creds, FUNC_POST_ORDEM, build_ordem_payload(order, creds))
    except EShipError as e:
        # "MOR8003: Nº Ordem já cadastrada" NÃO é falha: a ordem existe no WMS (foi criada num
        # envio anterior cujo id se perdeu). Recupera o id pela consulta e segue para os anexos —
        # antes isso abortava o envio e a NF-e emitida depois nunca era anexada.
        if not _ja_cadastrada(e):
            raise
        eship_id, status_id = await _fetch_eship_order(creds, order)

        # A ordem existente pode estar CANCELADA. O eShip não libera o `numeroOrigem` depois do
        # cancelamento — ele fica ocupado para sempre —, então o reenvio bate em MOR8003 e NADA é
        # criado. Reaproveitar esse id seria mentir: o sistema mostraria sucesso apontando para uma
        # ordem morta (foi o que aconteceu com o pedido 2000017373745064 / ordem 3098258).
        if _eship_cancelada(status_id):
            raise EShipError(
                f"O eShip já tem uma ordem CANCELADA com este número ({eship_id or 's/ id'}) e não "
                f"libera o mesmo numeroOrigem para uma nova ordem. Nada foi criado no WMS. Peça a "
                f"exclusão definitiva da ordem no eShip para reenviar este pedido."
            )

        order.eship_order_id = eship_id
        order.eship_last_response = f"MOR8003 (ordem já existia no WMS): {e}"[:32000]
        await db.commit()
        logger.info(
            "[eShip] pedido=%s: ordem já existia no WMS (MOR8003) — id recuperado=%s status=%s",
            order.id, eship_id, status_id,
        )
        return {"already_sent": True, "eship_order_id": eship_id}

    # O código da ordem é o que o dono usa para CONFERIR o envio no painel do eShip. Antes havia
    # um fallback (`or platform_order_id`) que, quando a extração falhava, gravava o número do
    # pedido do ML como se fosse o id do WMS — um id FALSO, impossível de localizar no eShip.
    # Agora: se não der para extrair, o id fica NULO e a resposta CRUA é guardada para conferência.
    eship_id = extract_order_id(resp)
    order.eship_order_id = eship_id
    try:
        order.eship_last_response = json.dumps(resp, ensure_ascii=False)[:32000]
    except (TypeError, ValueError):
        order.eship_last_response = str(resp)[:32000]
    if not eship_id:
        logger.warning(
            "[eShip] pedido=%s: ordem aceita mas sem id extraível na resposta: %.300s",
            order.id, order.eship_last_response,
        )
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
                      mime_type: str, inserir_fiscal: bool = False,
                      atualizar_transporte: bool = False,
                      id_tipo_anexo: int | None = None) -> dict:
    """Anexa um arquivo (NF-e XML, DANFE PDF, etiqueta) a uma ordem existente (spec §6).

    O tipo do anexo vem das FLAGS + extensão + `idTipoAnexo` (testado contra a API real):
      - NF-e (XML): `inserir_fiscal=True` + `atualizar_transporte=True` + `extensao="xml"`
        → categoria `xmldanfe` no WMS.
      - PDF (etiqueta e DANFE): `id_tipo_anexo=2` → categoria `documentosItPop`.
      - ZPL: `id_tipo_anexo=7` → categoria `etiqueta`. **Sem o idTipoAnexo o WMS recusa o ZPL**
        ("MIT5002 - Tipo de arquivo não aceito, zpl").
    """
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    if isinstance(content, str):
        content = content.encode("utf-8")
    if extensao == "xml":
        # O WMS recusa o prolog `<?xml?>` embutido (mesma armadilha do SAAJ na DC-e).
        content = _XML_PROLOG_RE.sub(b"", content)
    if not creds.warehouse_code:
        raise EShipError(
            "Configure o código do armazém (codigoArmazem) na CMIG antes de anexar arquivos ao eShip."
        )
    payload = {
        # O anexo é endereçado pelo ARMAZÉM + numeroOrigem. Sem `codigoArmazem` o eShip não
        # localiza a ordem (era a causa da falha no envio — ver .claude/eSHIP.md).
        "codigoArmazem": creds.warehouse_code,
        "numeroOrigem": order.platform_order_id or str(order.id),
        "arquivoBase": base64.b64encode(content).decode(),
        "extensao": extensao,
        "mimeType": mime_type,
    }
    if id_tipo_anexo is not None:
        payload["idTipoAnexo"] = int(id_tipo_anexo)   # INTEIRO — o WMS recusa a string
    if inserir_fiscal:
        payload["inserirFiscal"] = "1"
    if atualizar_transporte:
        payload["atualizarTransporte"] = "1"
        payload["cadastrarTransporte"] = "1"
    return await client.call(creds, FUNC_POST_ARQUIVO, payload)


async def attach_nfe_xml(db: AsyncSession, order: Order, xml_content: bytes) -> dict:
    """Anexa o XML da NF-e (flags fiscais + transporte)."""
    return await attach_file(
        db, order, content=xml_content, extensao="xml", mime_type="application/xml",
        inserir_fiscal=True, atualizar_transporte=True,
    )


async def attach_label(db: AsyncSession, order: Order, content: bytes,
                       extensao: str = "pdf", mime_type: str = "application/pdf",
                       id_tipo_anexo: int | None = None) -> dict:
    """Anexa etiqueta/DANFE (pdf ou zpl, sem flag fiscal)."""
    return await attach_file(
        db, order, content=content, extensao=extensao, mime_type=mime_type,
        id_tipo_anexo=id_tipo_anexo,
    )


def _render_danfe(order: Order, xml_bytes: bytes) -> bytes | None:
    """Gera o DANFE (PDF) a partir do XML autorizado. `None` se não der para renderizar.

    Reusa o gerador da emissão própria (`services/fiscal/sefaz/danfe.gerar_danfe`) — não
    reimplementa layout. O XML do Faturador ML já vem como `nfeProc` (com protocolo).
    """
    try:
        from services.fiscal.sefaz.danfe import gerar_danfe

        return gerar_danfe(xml_bytes.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 — DANFE é complementar; o XML é o que vale fiscalmente
        logger.warning("[eShip] pedido=%s: não foi possível gerar o DANFE: %s", order.id, exc)
        return None


async def touch_order(creds: EShipCreds, order: Order) -> bool:
    """Carimba a "Data da última atualização" da ordem no eShip (`webServicePutOrdem`).

    Sem isso, a coluna da grade do eShip mostra "Sem data de atualização registrada" — o galpão
    não enxerga que a ordem foi mexida (anexo de NF-e, etiqueta, reenvio).

    O WMS grava a hora DELE e ignora qualquer valor que a gente mande no `dataHoraAtualizacao`;
    o que importa é o PUT acontecer. O PUT só com o `id` não altera produtos/infos/anexos/status.
    """
    if not order.eship_order_id:
        return False
    try:
        await client.call(creds, FUNC_PUT_ORDEM, {"id": int(order.eship_order_id)})
        return True
    except (EShipError, ValueError) as exc:
        # Carimbo é complementar: nunca derruba um envio que deu certo.
        logger.warning(
            "[eShip] pedido=%s: não foi possível carimbar a data de atualização: %s", order.id, exc
        )
        return False


def _real_eship_order_id(resp: dict) -> int | None:
    """Extrai o id INTERNO real da ordem de uma resposta do GetOrdem (`corpo.body.dados[0].id`).

    O `order.eship_order_id` guardado é NÃO confiável (muitas vezes é o fallback = nº do ML); o
    PutOrdem exige o id interno real do WMS.
    """
    if not isinstance(resp, dict):
        return None
    dados = ((resp.get("corpo") or {}).get("body") or {}).get("dados")
    d = dados[0] if isinstance(dados, list) and dados else (dados if isinstance(dados, dict) else None)
    rid = d.get("id") if isinstance(d, dict) else None
    try:
        return int(rid) if rid not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def ensure_order_transport(
    db: AsyncSession, order: Order, creds: EShipCreds, *, resp: dict | None = None
) -> dict:
    """Garante o transporte (codigoTransporte) na ordem do eShip via PutOrdem. Idempotente.

    - Selo `order.eship_transporte_codigo`: se já é o código atual, não faz nada (não martela o WMS
      a cada ciclo de sync do scheduler).
    - Resolve o id INTERNO real via GetOrdem (o `eship_order_id` guardado não serve p/ o PutOrdem).
      `resp` = uma resposta de GetOrdem já obtida (o sync reaproveita a dele, evita 2ª chamada).
    - PutOrdem só com {id, transporte} — não toca produtos/anexos/status (ver touch_order). É a
      "última palavra" sobre o transporte, mesmo que o anexo do XML da NF-e tenha reprocessado.
    """
    if _is_full_order(order):
        return {"ok": False, "reason": "full"}
    codigo = transporte_code_for_order(order)
    if not codigo:
        # CMIG sem código de transporte confirmado — não mexe (transporte vem do XML da nota).
        return {"ok": False, "reason": "sem_codigo_p_cmig"}
    if (order.eship_transporte_codigo or "") == codigo:
        return {"ok": True, "skipped": "already_set", "codigo": codigo}

    if resp is None:
        try:
            resp = await client.call(
                creds, FUNC_GET_ORDEM,
                {"numeroOrigem": order.platform_order_id or str(order.id),
                 "incluirInfo": True, "pagina": 1},
            )
        except EShipError as e:
            logger.warning("[eShip] pedido=%s: GetOrdem p/ transporte falhou: %s", order.id, e)
            return {"ok": False, "reason": "getordem_falhou"}

    real_id = _real_eship_order_id(resp)
    if not real_id:
        # Ordem não localizada no WMS por numeroOrigem — falhar alto (precisa reenviar).
        logger.warning("[eShip] pedido=%s: ordem não localizada no WMS p/ aplicar transporte", order.id)
        return {"ok": False, "reason": "nao_encontrada_no_wms"}

    try:
        await client.call(
            creds, FUNC_PUT_ORDEM,
            {"id": real_id, "transporte": {"codigoTransporte": codigo}},
        )
    except EShipError as e:
        logger.warning("[eShip] pedido=%s: PutOrdem transporte=%s falhou: %s", order.id, codigo, e)
        return {"ok": False, "reason": str(e)[:200]}

    order.eship_transporte_codigo = codigo
    await db.commit()
    logger.info("[eShip] pedido=%s: transporte %s aplicado na ordem %s", order.id, codigo, real_id)
    return {"ok": True, "codigo": codigo, "eship_order_id": real_id}


async def _categorias_anexadas(db: AsyncSession, order: Order) -> dict[str, int]:
    """`{categoria: nº de arquivos}` do que o eShip JÁ TEM na ordem — o antiduplicidade."""
    return {a["categoria"]: a["quantidade"] for a in await get_anexos(db, order)}


async def get_anexos(db: AsyncSession, order: Order) -> list[dict]:
    """Lista os arquivos ANEXADOS na ordem, direto do eShip (`webServiceGetAnexosOrdem`).

    Devolve `[{categoria, quantidade, tamanho_kb}]` — o conteúdo vem em base64 e é pesado
    (centenas de KB por arquivo), então nunca é repassado ao frontend: o que o usuário precisa
    é a CONFERÊNCIA de que o arquivo está lá.
    """
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    resp = await client.call(
        creds, FUNC_GET_ANEXOS, {"numeroOrigem": order.platform_order_id or str(order.id)}
    )
    dados = (((resp or {}).get("corpo") or {}).get("body") or {}).get("dados") or []
    out: list[dict] = []
    for node in dados if isinstance(dados, list) else [dados]:
        anexos = (node or {}).get("anexos") or {}
        for categoria, arquivos in anexos.items():
            if not isinstance(arquivos, list):
                arquivos = [arquivos] if arquivos else []
            # A lista vem com SLOTS VAZIOS ("") entre os arquivos — contar o tamanho da lista
            # inflava o número (a categoria `etiqueta` aparecia com "6 arquivos" tendo 1).
            arquivos = [a for a in arquivos if isinstance(a, str) and a]
            total = sum(len(a) for a in arquivos)
            out.append({
                "categoria": categoria,
                "quantidade": len(arquivos),
                # base64 → ~3/4 do tamanho em bytes
                "tamanho_kb": round(total * 3 / 4 / 1024, 1) if total else 0,
            })
    return out


def _zpl_do_zip(raw: bytes) -> bytes | None:
    """O ML entrega o "zpl2" como um ZIP (`Etiqueta de envio.txt` + `Controle.pdf`), não como ZPL.

    Anexar o ZIP cru marcado como .zpl mandava lixo ao WMS. Aqui abrimos o pacote e devolvemos o
    ZPL de verdade (o `.txt`, que começa com `^XA`).
    """
    if raw[:2] != b"PK":
        return raw  # já veio ZPL puro
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for nome in z.namelist():
                if nome.lower().endswith(".txt"):
                    return z.read(nome)
    except (zipfile.BadZipFile, KeyError) as exc:
        logger.warning("[eShip] etiqueta ZPL: zip ilegível: %s", exc)
    return None


async def _resolve_labels(db: AsyncSession, order: Order) -> tuple[bytes | None, bytes | None]:
    """Baixa a etiqueta do ML. Retorna `(pdf, zpl)` — cada um `None` se indisponível.

    Reusa `ml_service.get_shipment_label` (não reimplementa a chamada ML). Etiqueta ainda não
    liberada (ML 400) volta como `None`.
    """
    if not order.shipment_id:
        return None, None
    acc = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
        )
    ).scalar_one_or_none()
    if not acc or not acc.access_token:
        return None, None

    async def baixar(fmt: str) -> bytes | None:
        try:
            content, _ctype = await _ml.get_shipment_label(acc.access_token, order.shipment_id, fmt)
            return content
        except Exception as exc:  # noqa: BLE001 — etiqueta indisponível nesse formato agora
            logger.warning("[eShip] etiqueta %s pedido=%s: %s", fmt, order.id, exc)
            return None

    pdf = await baixar("pdf")
    bruto = await baixar("zpl2")
    return pdf, (_zpl_do_zip(bruto) if bruto else None)


async def cancel_order(db: AsyncSession, order: Order) -> dict:
    """Exclui a ordem no eShip — DELETE, não apenas cancelamento.

    Cancelar deixa a ordem morta ocupando o `numeroOrigem`: o reenvio do mesmo pedido bate em
    "MOR8003: Nº Ordem já cadastrada" e nada é criado. Só o `webServiceDeleteOrdem` remove a ordem
    e devolve o número, permitindo reenviar o pedido com o MESMO número da venda.

    Tenta o DELETE direto (funciona inclusive em ordem já cancelada). Se o WMS exigir o
    cancelamento antes, cancela e repete o DELETE.
    """
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    numero_origem = order.platform_order_id or str(order.id)
    try:
        resp = await client.call(creds, FUNC_DELETAR_ORDEM, {"numeroOrigem": numero_origem})
    except EShipError as exc:
        logger.info(
            "[eShip] pedido=%s: delete direto recusado (%s) — cancelando antes e repetindo",
            order.id, exc,
        )
        await client.call(creds, FUNC_CANCELAR_ORDEM, {"numeroOrigem": numero_origem})
        resp = await client.call(creds, FUNC_DELETAR_ORDEM, {"numeroOrigem": numero_origem})

    order.eship_order_id = None
    order.eship_nfe_attached = 0
    order.eship_label_attached = 0
    # 'cancelled' NÃO conta como "já enviada" (ver order_was_pushed) → libera novo envio.
    order.eship_dispatch_status = "cancelled"
    order.eship_dispatch_error = None
    order.eship_dispatch_at = None
    await _restore_shipment_status_from_ml(db, order)
    await db.commit()
    return resp


async def _restore_shipment_status_from_ml(db: AsyncSession, order: Order) -> None:
    """Devolve o status de envio ao que o MARKETPLACE diz — a ordem no WMS não existe mais.

    Enquanto a ordem viveu no eShip, o sync sobrescreveu o `shipment_status` com o estado do WMS
    ("Em Preparação"). Cancelada a ordem, esse estado passa a ser mentira: o pedido volta a ser o
    que o Mercado Livre diz que ele é (tipicamente "Pronto p/ Envio"). Reperguntamos ao ML em vez
    de chutar um valor fixo — chutar erraria em pedido já despachado/entregue.
    """
    if order.platform != "mercadolivre" or not order.shipment_id:
        return
    acc = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
        )
    ).scalar_one_or_none()
    if not acc:
        return
    try:
        token = await get_valid_token(acc, db)
        ship = await _ml.get_shipment(token, order.shipment_id, caller_id=acc.platform_user_id)
        novo = (ship or {}).get("status")
        if novo and novo != order.shipment_status:
            logger.info(
                "[eShip] pedido=%s: ordem cancelada — shipment_status %s → %s (fonte: ML)",
                order.id, order.shipment_status, novo,
            )
            order.shipment_status = novo
    except Exception as exc:  # noqa: BLE001 — o cancelamento no WMS já ocorreu; não desfazer por isso
        logger.warning(
            "[eShip] pedido=%s: não foi possível restaurar o shipment_status pelo ML: %s",
            order.id, exc,
        )


async def send_order_full(db: AsyncSession, order: Order) -> dict:
    """Envio COMPLETO ao eShip: Ordem → NF-e (XML) → Etiqueta (ZPL + PDF).

    Idempotente e tolerante a parcial: cada etapa é pulada se já concluída (selos
    `eship_nfe_attached`/`eship_label_attached`), e a falha de uma etapa não impede as
    demais. Retorna o estado granular por etapa (`erros[]` descreve o que ficou pendente).
    """
    result: dict = {"ordem": None, "nfe": None, "etiquetas": [], "erros": []}

    if _is_full_order(order):
        result["erros"].append({
            "etapa": "ordem",
            "erro": "Pedido FULL é gerido pelo Mercado Livre — não vai ao WMS (eShip).",
        })
        return result

    # Single-flight: claim atômico de "sending" para não anexar em duplicidade sob duplo-clique
    # ou reenvio concorrente do mesmo pedido (asyncio + AsyncSyncSession não serializam sozinhos).
    #
    # O claim aceita RETOMAR um lock órfão (processo morto no meio do envio): se o pedido está em
    # "sending" há mais de _LOCK_TTL, o lock é considerado expirado. Sem isso, um crash deixava o
    # pedido travado para sempre (era o sintoma: "envio já em andamento" em todo clique).
    agora = datetime.now(UTC)
    expirado = agora - _LOCK_TTL
    claim = await db.execute(
        sa_update(Order)
        .where(
            Order.id == order.id,
            or_(
                Order.eship_dispatch_status.is_(None),
                Order.eship_dispatch_status != "sending",
                Order.eship_dispatch_at.is_(None),
                Order.eship_dispatch_at < expirado,
            ),
        )
        .values(
            eship_dispatch_status="sending",
            eship_dispatch_at=agora,
            eship_dispatch_attempts=func.coalesce(Order.eship_dispatch_attempts, 0) + 1,
        )
    )
    await db.commit()
    if not getattr(claim, "rowcount", 0):
        result["erros"].append({
            "etapa": "lock",
            "erro": "Envio ao eShip já em andamento para este pedido — aguarde alguns instantes.",
        })
        return result
    order.eship_dispatch_status = "sending"
    order.eship_dispatch_at = agora

    try:
        # 1) Garante a Ordem (push_order é idempotente por eship_order_id).
        try:
            push = await push_order(db, order)
            result["ordem"] = {
                "eship_order_id": push.get("eship_order_id"),
                "already_sent": push.get("already_sent", False),
            }
        except EShipError as e:
            result["erros"].append({"etapa": "ordem", "erro": str(e)})
            return result  # sem Ordem não há onde anexar

        # 2/3) Anexos — o WMS é a FONTE DA VERDADE, não o selo local.
        #
        # O selo mentia: quando o eShip recusava o processamento fiscal (ex. MNF0917/CFOP), ele
        # devolvia erro MAS guardava o arquivo. Nós zerávamos o selo e, no "Atualizar", anexávamos
        # de novo → o XML da NF-e ficava DUPLICADO na ordem. Agora, antes de cada anexo,
        # perguntamos ao eShip o que ele já tem (webServiceGetAnexosOrdem).
        #
        # Categorias (descobertas testando contra a API real):
        #   xmldanfe        ← XML da NF-e (inserirFiscal)
        #   documentosItPop ← PDFs (etiqueta e DANFE, idTipoAnexo=2)
        #   etiqueta        ← ZPL (idTipoAnexo=7)
        try:
            no_wms = await _categorias_anexadas(db, order)
        except EShipError as e:
            no_wms = {}
            logger.warning("[eShip] pedido=%s: não deu p/ conferir os anexos no WMS: %s", order.id, e)

        xml_bytes = None
        # --- NF-e (XML) ---
        if no_wms.get("xmldanfe", 0) > 0:
            order.eship_nfe_attached = 1
            result["nfe"] = {"status": "already"}
        else:
            doc = await resolve_nfe_xml(db, order)
            if not doc:
                result["erros"].append({
                    "etapa": "nfe",
                    "erro": "NF-e ainda não autorizada / indisponível para este pedido.",
                })
            else:
                xml_bytes, chave, kind = doc
                try:
                    await attach_nfe_xml(db, order, xml_bytes)
                    order.eship_nfe_attached = 1
                    result["nfe"] = {"status": "attached", "chave": chave, "kind": kind}
                except EShipError as e:
                    order.eship_nfe_attached = 0
                    result["erros"].append({"etapa": "nfe", "erro": str(e)})

        # --- PDFs: etiqueta + DANFE (mesma categoria no WMS, `documentosItPop`) ---
        pdfs_no_wms = no_wms.get("documentosItPop", 0)
        etiqueta_pdf, zpl = await _resolve_labels(db, order)

        if pdfs_no_wms >= 2:
            result["etiquetas"] = [{"status": "already"}]
        else:
            # O DANFE precisa do XML — que pode não ter sido carregado acima (quando o WMS já
            # tinha o xmldanfe). Busca só agora, e só se for mesmo anexar.
            if xml_bytes is None and pdfs_no_wms + (1 if etiqueta_pdf else 0) < 2:
                doc = await resolve_nfe_xml(db, order)
                xml_bytes = doc[0] if doc else None
            danfe = _render_danfe(order, xml_bytes) if xml_bytes else None

            anexados = pdfs_no_wms
            for conteudo, etapa in ((etiqueta_pdf, "etiqueta:pdf"), (danfe, "danfe")):
                if not conteudo or anexados >= 2:
                    continue
                try:
                    await attach_label(db, order, conteudo, extensao="pdf",
                                       mime_type="application/pdf", id_tipo_anexo=_ANEXO_PDF)
                    result["etiquetas"].append({"status": "attached", "formato": etapa})
                    anexados += 1
                except EShipError as e:
                    result["erros"].append({"etapa": etapa, "erro": str(e)})
            order.eship_label_attached = 1 if anexados else 0
            if not etiqueta_pdf:
                result["erros"].append({
                    "etapa": "etiqueta",
                    "erro": "Etiqueta ainda não liberada pelo Mercado Livre.",
                })

        # --- ZPL da etiqueta (categoria própria no WMS) ---
        if no_wms.get("etiqueta", 0) > 0:
            result["zpl"] = {"status": "already"}
        elif zpl:
            try:
                await attach_label(db, order, zpl, extensao="zpl", mime_type="text/plain",
                                   id_tipo_anexo=_ANEXO_ZPL)
                result["zpl"] = {"status": "attached"}
            except EShipError as e:
                result["erros"].append({"etapa": "etiqueta:zpl", "erro": str(e)})

        # 4) Transporte + carimbo da "Data da última atualização".
        # O transporte é aplicado por ÚLTIMO (após os anexos), como palavra final sobre a
        # transportadora — mesmo que o anexo do XML da NF-e tenha reprocessado o transporte. É
        # idempotente (selo `eship_transporte_codigo`). O carimbo garante que a grade do eShip
        # mostre "atualizada" (senão o galpão não vê que a ordem foi mexida).
        if order.eship_order_id:
            creds, _cmig = await _creds_for_order(db, order)
            if creds:
                try:
                    result["transporte"] = await ensure_order_transport(db, order, creds)
                except Exception as e:  # noqa: BLE001 — transporte é complementar, não derruba envio
                    logger.warning("[eShip] pedido=%s: ensure_order_transport falhou: %s", order.id, e)
                result["atualizada_em_eship"] = await touch_order(creds, order)
    except Exception as e:  # noqa: BLE001 — registra e não deixa o pedido preso em "sending"
        result["erros"].append({"etapa": "interno", "erro": str(e)})
        logger.exception("[eShip] send_order_full pedido=%s falhou", order.id)
    finally:
        # O desfecho é resolvido AQUI, sempre. O `finally` roda inclusive quando a etapa da Ordem
        # falha e sai por `return` — era exatamente esse caminho que deixava o pedido preso em
        # "sending" (o `except` não roda num `return`), bloqueando todo clique posterior.
        if order.eship_dispatch_status == "sending":
            if not result["erros"]:
                order.eship_dispatch_status = "sent"
            elif order.eship_order_id:
                order.eship_dispatch_status = "partial"   # ordem criada, mas algo faltou
            else:
                order.eship_dispatch_status = "failed"    # nem a ordem foi criada
        order.eship_dispatch_error = ("; ".join(x["erro"] for x in result["erros"]) or None)
        if order.eship_dispatch_error:
            order.eship_dispatch_error = order.eship_dispatch_error[:500]
        await db.commit()

    return result


async def get_falhas(db: AsyncSession, order: Order) -> dict:
    """Consulta falhas de processamento da ordem (spec §7)."""
    creds, _cmig = await _creds_for_order(db, order)
    if not creds:
        raise EShipError("A empresa (CMIG) do pedido não tem integração eShip ativa/configurada.")
    return await client.call(
        creds, FUNC_GET_FALHAS,
        {"numeroOrigem": order.platform_order_id or str(order.id)},
    )


def _eship_produto_row(p: dict, saldo: list | None = None) -> dict:
    """Extrai os campos relevantes (info + estoque) de um produto do GetProduto.

    `saldo` = `[fisico, disponivel, reservado]` vindo do GetSaldoEstoque (fonte real do
    estoque; o GetProduto traz 0 na listagem). Se None, usa os totais do próprio produto.
    """
    cad = p.get("cadastro") if isinstance(p.get("cadastro"), dict) else {}
    st = p.get("status") if isinstance(p.get("status"), dict) else {}
    tp = p.get("tipo") if isinstance(p.get("tipo"), dict) else {}
    fisico = saldo[0] if saldo is not None else p.get("totalFisico")
    disponivel = saldo[1] if saldo is not None else p.get("totalDisponivel")
    reservado = saldo[2] if saldo is not None else p.get("totalReservado")
    return {
        "codigo": p.get("codigo"),
        "codigo_barras": p.get("codigoBarras"),
        "descricao": p.get("descricao"),
        "empresa": cad.get("nome"),
        "status": st.get("descricao"),
        "tipo": tp.get("descricao"),
        "is_full": bool(p.get("itsFull")),
        "total_fisico": fisico,
        "total_disponivel": disponivel,
        "total_reservado": reservado,
        "total_enderecado": p.get("totalEnderecado"),
        "peso_bruto": p.get("pesoBruto"),
    }


async def list_eship_products(db: AsyncSession, cmig_id: int, page: int = 1) -> dict:
    """Lista os produtos do eShip (WMS) com info + estoque, paginado e ESCOPADO à empresa.

    O WMS é multi-tenant e a API não filtra por empresa (nem por SKU/texto) — o escopo por
    CMIG é feito no cliente (`cadastro.cnpj`/`cpf`). Usado apenas como fallback paginado; a
    tela usa `list_all_eship_products`.
    """
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    creds = creds_from_cmig(cmig)
    if not creds:
        raise EShipError("CMIG sem integração eShip ativa/configurada.")
    cnpj, cpf = _digits(getattr(cmig, "cnpj", None)), _digits(getattr(cmig, "cpf", None))
    if not cnpj and not cpf:
        # Sem CNPJ/CPF não há como isolar a empresa no WMS multi-tenant → NÃO consulta o
        # WMS (mesma barreira anti-vazamento de list_all_eship_products).
        return {
            "produtos": [], "pagina": 1, "paginas": 0, "total": 0,
            "por_pagina": _PRODUTOS_PAGE_SIZE, "escopo_indefinido": True,
        }
    resp = await client.call(
        creds, FUNC_GET_PRODUTO,
        {"pagina": max(1, int(page or 1)), "quantidadeRegistros": _PRODUTOS_PAGE_SIZE},
    )
    body = ((resp or {}).get("corpo") or {}).get("body") or {}
    pag = body.get("dadosPaginacao") or {}
    dados = [p for p in (body.get("dados") or []) if _produto_da_cmig(p, cnpj, cpf)]
    por_id, por_cod = await _fetch_saldo_indexes(creds)
    return {
        "produtos": [_eship_produto_row(p, _saldo_for(p, por_id, por_cod)) for p in dados],
        "pagina": pag.get("paginaAtual") or page,
        "paginas": pag.get("quantidadePaginas"),
        "total": pag.get("totalObjetos"),
        "por_pagina": pag.get("registrosPorPagina"),
        "escopo_indefinido": False,
    }


async def list_all_eship_products(db: AsyncSession, cmig_id: int, force: bool = False) -> dict:
    """Busca os produtos do eShip da EMPRESA (CMIG), varrendo o catálogo do WMS.

    Como o WMS é multi-tenant e a API ignora o filtro de empresa no GetProduto, varremos
    todas as páginas (100/pág; concorrência limitada; best-effort por página) e filtramos
    no cliente por `cadastro.cnpj`/`cpf` da CMIG. `total` = nº de produtos da empresa;
    `total_catalogo` = tamanho do catálogo inteiro do WMS (contexto). Cacheado por
    `_PRODUTOS_CACHE_TTL` s por CMIG (use `force=True` p/ recarregar).
    """
    now = time.monotonic()
    if not force:
        cached = _produtos_cache.get(cmig_id)
        if cached and (now - cached[0]) < _PRODUTOS_CACHE_TTL:
            return cached[1]

    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    creds = creds_from_cmig(cmig)
    if not creds:
        raise EShipError("CMIG sem integração eShip ativa/configurada.")

    cnpj, cpf = _digits(getattr(cmig, "cnpj", None)), _digits(getattr(cmig, "cpf", None))
    if not cnpj and not cpf:
        # Sem CNPJ/CPF não há como isolar a empresa no WMS multi-tenant → NÃO devolve o
        # catálogo de terceiros. A tela deve pedir o cadastro do documento na CMIG.
        return {
            "produtos": [], "total": 0, "total_catalogo": None, "paginas": 0,
            "truncado": False, "parcial": False, "paginas_falhas": 0, "escopo_indefinido": True,
        }

    first = await client.call(
        creds, FUNC_GET_PRODUTO, {"pagina": 1, "quantidadeRegistros": _PRODUTOS_PAGE_SIZE}
    )
    body = ((first or {}).get("corpo") or {}).get("body") or {}
    pag = body.get("dadosPaginacao") or {}
    try:
        total_pages = int(pag.get("quantidadePaginas") or 1)
    except (ValueError, TypeError):
        total_pages = 1
    cap = min(max(total_pages, 1), _PRODUTOS_MAX_PAGES)

    # by_page[pg] = lista (ok, pode ser []) ou None (falhou/não buscada → buraco no catálogo)
    by_page: dict[int, list | None] = {1: body.get("dados") or []}
    if cap > 1:
        sem = asyncio.Semaphore(_PRODUTOS_FETCH_CONCURRENCY)

        async def _fetch(pg: int) -> None:
            async with sem:
                try:
                    r = await client.call(
                        creds, FUNC_GET_PRODUTO, {"pagina": pg, "quantidadeRegistros": _PRODUTOS_PAGE_SIZE}
                    )
                    by_page[pg] = (((r or {}).get("corpo") or {}).get("body") or {}).get("dados") or []
                except EShipError as e:
                    logger.warning("[eShip] GetProduto página %s falhou: %s", pg, e)
                    by_page[pg] = None  # distingue falha de página vazia

        try:
            await asyncio.wait_for(
                asyncio.gather(*[_fetch(pg) for pg in range(2, cap + 1)]),
                timeout=_PRODUTOS_TOTAL_DEADLINE,
            )
        except TimeoutError:
            logger.warning("[eShip] carga do catálogo cmig=%s excedeu %ss; retornando parcial",
                           cmig_id, _PRODUTOS_TOTAL_DEADLINE)

    # Páginas com None (falha) ou ausentes (timeout) = buracos → resultado PARCIAL.
    paginas_falhas = sum(1 for pg in range(1, cap + 1) if by_page.get(pg) is None)
    # Escopo por empresa (client-side): a API ignora o filtro de cadastro no GetProduto.
    da_empresa = [
        p for pg in range(1, cap + 1) for p in (by_page.get(pg) or [])
        if _produto_da_cmig(p, cnpj, cpf)
    ]
    # Enriquece com o estoque real (GetProduto traz 0 na listagem; o saldo vem do
    # GetSaldoEstoque, já escopado ao depósito da conta). Junção por id/SKU.
    por_id, por_cod = await _fetch_saldo_indexes(creds)
    rows = [_eship_produto_row(p, _saldo_for(p, por_id, por_cod)) for p in da_empresa]
    result = {
        "produtos": rows,
        "total": len(rows),
        "total_catalogo": pag.get("totalObjetos"),
        "paginas": total_pages,
        "truncado": total_pages > cap,
        "parcial": paginas_falhas > 0,
        "paginas_falhas": paginas_falhas,
        "escopo_indefinido": False,
    }
    # Só cacheia carga COMPLETA (sem páginas falhas) — não fixa um catálogo furado por 5min.
    if not result["parcial"]:
        _produtos_cache[cmig_id] = (now, result)
    return result


def _ordem_da_cmig(o: dict, cnpj: str, cpf: str) -> bool:
    """True se a ordem do WMS pertence à empresa (casa `remetente.cnpj`/`cpf`, só dígitos).

    O WMS é multi-tenant e o GetOrdem devolve ordens de TODAS as empresas — o escopo é feito
    aqui, no cliente, como em `_produto_da_cmig`. Sem isso a tela vazaria ordens de terceiros.
    """
    rem = o.get("remetente") if isinstance(o.get("remetente"), dict) else {}
    return (bool(cnpj) and _digits(rem.get("cnpj")) == cnpj) or (
        bool(cpf) and _digits(rem.get("cpf")) == cpf
    )


def _eship_dt_to_iso(node) -> str | None:
    """Converte o dataHora do eShip para ISO UTC (ADR-0013 — transporte em UTC aware).

    O eShip devolve `{"date": "2026-07-18 19:57:15.000000", "timezone": "America/Fortaleza"}`:
    hora LOCAL naive + o nome do fuso (UTC-3). Sem localizar, o front trataria a string naive
    como UTC e exibiria 3h a menos. Aqui, na borda de entrada, viramos UTC aware.
    """
    if not isinstance(node, dict):
        return None
    raw = node.get("date")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))  # 3.11 aceita separador espaço + microssegundos
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(node.get("timezone") or "America/Sao_Paulo"))
        except (ZoneInfoNotFoundError, ValueError):
            dt = dt.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return iso_utc(dt)


def _eship_ordem_row(o: dict) -> dict:
    infos = o.get("infos") if isinstance(o.get("infos"), dict) else {}
    st = o.get("status") if isinstance(o.get("status"), dict) else {}
    dest = o.get("destinatario") if isinstance(o.get("destinatario"), dict) else {}
    return {
        "numero_origem": str(infos.get("norigem") or o.get("numeroOrigem") or "").strip(),
        "eship_order_id": _coax_id(o.get("id")),
        "status_id": st.get("id"),
        "status_desc": st.get("descricao"),
        "destinatario": dest.get("nome"),
        "data_hora": _eship_dt_to_iso(o.get("dataHora")),
    }


async def _scan_ordens(creds: EShipCreds, use_cache: bool = True) -> dict:
    """Varre o webServiceGetOrdem paginado de UM endpoint (best-effort) e devolve as ordens CRUAS.

    Espelha `list_all_eship_products`: concorrência limitada, deadline; `parcial` (páginas
    falhas) / `truncado` (mais páginas que o teto). O filtro por empresa (CNPJ/CPF/idTipo) e a
    serialização ficam a cargo de quem chama — este helper só busca. Cache curto por endpoint
    (`_ORDENS_SCAN_TTL`) para não martelar o WMS; varredura parcial NÃO é cacheada.
    """
    cache_key = (creds.base_url, creds.api_key)
    now = time.monotonic()
    if use_cache:
        cached = _ordens_scan_cache.get(cache_key)
        if cached and (now - cached[0]) < _ORDENS_SCAN_TTL:
            return cached[1]

    payload = {"incluirInfo": True, "quantidadeRegistros": _PRODUTOS_PAGE_SIZE}
    first = await client.call(creds, FUNC_GET_ORDEM, {**payload, "pagina": 1})
    body = ((first or {}).get("corpo") or {}).get("body") or {}
    pag = body.get("dadosPaginacao") or {}
    try:
        total_pages = int(pag.get("quantidadePaginas") or 1)
    except (ValueError, TypeError):
        total_pages = 1
    cap = min(max(total_pages, 1), _PRODUTOS_MAX_PAGES)

    def _dados(b) -> list:
        d = b.get("dados") or []
        return [d] if isinstance(d, dict) else (d or [])

    by_page: dict[int, list | None] = {1: _dados(body)}
    if cap > 1:
        sem = asyncio.Semaphore(_PRODUTOS_FETCH_CONCURRENCY)

        async def _fetch(pg: int) -> None:
            async with sem:
                try:
                    r = await client.call(creds, FUNC_GET_ORDEM, {**payload, "pagina": pg})
                    by_page[pg] = _dados(((r or {}).get("corpo") or {}).get("body") or {})
                except EShipError as e:
                    logger.warning("[eShip] GetOrdem página %s falhou: %s", pg, e)
                    by_page[pg] = None

        try:
            await asyncio.wait_for(
                asyncio.gather(*[_fetch(pg) for pg in range(2, cap + 1)]),
                timeout=_PRODUTOS_TOTAL_DEADLINE,
            )
        except TimeoutError:
            logger.warning("[eShip] varredura de ordens excedeu %ss; parcial",
                           _PRODUTOS_TOTAL_DEADLINE)

    paginas_falhas = sum(1 for pg in range(1, cap + 1) if by_page.get(pg) is None)
    raw = [o for pg in range(1, cap + 1) for o in (by_page.get(pg) or []) if isinstance(o, dict)]
    result = {
        "raw": raw,
        "total_wms": pag.get("totalObjetos"),
        "paginas": total_pages,
        "truncado": total_pages > cap,
        "parcial": paginas_falhas > 0,
    }
    if not result["parcial"]:  # não fixa uma varredura furada no cache
        _ordens_scan_cache[cache_key] = (now, result)
    return result


async def list_eship_orders(db: AsyncSession, cmig_id: int) -> dict:
    """Lista as ORDENS do eShip (WMS) da EMPRESA (CMIG), varrendo o GetOrdem paginado.

    WMS multi-tenant → varre as páginas (`_scan_ordens`) e filtra no cliente por
    `remetente.cnpj`/`cpf`. Marca `parcial`/`truncado` quando não deu para varrer tudo.
    """
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    creds = creds_from_cmig(cmig)
    if not creds:
        raise EShipError("CMIG sem integração eShip ativa/configurada.")

    cnpj, cpf = _digits(getattr(cmig, "cnpj", None)), _digits(getattr(cmig, "cpf", None))
    if not cnpj and not cpf:
        return {"ordens": [], "total": 0, "total_wms": None, "paginas": 0,
                "truncado": False, "parcial": False, "escopo_indefinido": True}

    scan = await _scan_ordens(creds)
    ordens = [_eship_ordem_row(o) for o in scan["raw"] if _ordem_da_cmig(o, cnpj, cpf)]
    return {
        "ordens": ordens,
        "total": len(ordens),
        "total_wms": scan["total_wms"],
        "paginas": scan["paginas"],
        "truncado": scan["truncado"],
        "parcial": scan["parcial"],
        "escopo_indefinido": False,
    }


def _attribute_cmig(o: dict, cmigs: list):
    """Atribui uma ordem do WMS a UMA CMIG do grupo (mesmo endpoint eShip).

    ESCOPO (anti-vazamento LGPD): só é "nossa" a ordem cujo `remetente` casa o CNPJ/CPF de
    alguma CMIG acessível — o WMS é multi-tenant e devolve ordens de EMPRESAS DE TERCEIROS que
    NÃO são CMIGs do sistema; essas são descartadas. O `idTipo` é apenas DESEMPATE entre CMIGs
    acessíveis que compartilham o mesmo documento (mesmo lojista) — nunca cruza documentos.

    Devolve `(cmig|None, ambiguo, in_scope)`:
    - `in_scope=False` → ordem de terceiro, NÃO exibir;
    - `(cmig, False, True)` → atribuída a uma CMIG acessível;
    - `(None, True, True)` → é de alguma CMIG acessível (documento casa) mas não dá para dizer
      qual (documento+idTipo compartilhados) — rótulo "(compartilhado)", sem vazamento.
    """
    rem = o.get("remetente") if isinstance(o.get("remetente"), dict) else {}
    dcnpj, dcpf = _digits(rem.get("cnpj")), _digits(rem.get("cpf"))
    matched = [
        c for c in cmigs
        if (dcnpj and _digits(getattr(c, "cnpj", None)) == dcnpj)
        or (dcpf and _digits(getattr(c, "cpf", None)) == dcpf)
    ]
    if not matched:
        return None, False, False  # externa/terceiro → fora de escopo
    if len(matched) == 1:
        return matched[0], False, True
    idt = o.get("idTipo")  # desempate entre CMIGs que compartilham o documento
    if idt is not None:
        by_idt = [c for c in matched if getattr(c, "eship_id_tipo", None) == idt]
        if len(by_idt) == 1:
            return by_idt[0], False, True
    return None, True, True  # dentro do escopo, mas indistinguível → compartilhado


async def list_eship_orders_multi(db: AsyncSession, cmigs: list) -> dict:
    """Varre o WMS de TODAS as CMIGs dadas, UMA vez por endpoint (base_url+api_key).

    Várias CMIGs podem ser o MESMO lojista no eShip (mesmo apikey + mesmo idTipo). Para não
    duplicar, agrupamos por endpoint e varremos cada um só uma vez (em paralelo, com teto de
    concorrência e DEADLINE AGREGADO); cada ordem é escopada+atribuída por `_attribute_cmig`
    (ordens de terceiros são descartadas — anti-vazamento). Best-effort.

    Retorna também `by_cmig[cmig_id]` = confiabilidade da varredura do grupo daquela CMIG —
    a conciliação usa isso para não marcar "só no sistema" (divergência) quando o WMS do grupo
    veio parcial/truncado/erro/deadline (a ausência é INDETERMINADA, não real).
    """
    endpoints: dict[tuple, list] = {}
    for c in cmigs:
        creds = creds_from_cmig(c)
        if not creds:
            continue  # inativa/sem credencial → não entra na varredura do WMS
        endpoints.setdefault((creds.base_url, creds.api_key), [creds, []])[1].append(c)

    # Varre os endpoints em paralelo (teto de concorrência), com deadline AGREGADO — evita
    # N×deadline sequencial estourando o proxy quando há muitas apikeys distintas.
    results: dict[tuple, dict] = {}
    sem = asyncio.Semaphore(_PRODUTOS_FETCH_CONCURRENCY)

    async def _work(ck: tuple, creds: EShipCreds) -> None:
        async with sem:
            try:
                results[ck] = {"scan": await _scan_ordens(creds)}
            except EShipError as e:
                results[ck] = {"error": str(e)}

    try:
        await asyncio.wait_for(
            asyncio.gather(*[_work(ck, creds) for ck, (creds, _grp) in endpoints.items()]),
            timeout=_PRODUTOS_TOTAL_DEADLINE,
        )
    except TimeoutError:
        logger.warning("[eShip] conciliação consolidada excedeu deadline agregado (%ss)",
                       _PRODUTOS_TOTAL_DEADLINE)

    ordens: list = []
    seen: set = set()
    by_cmig: dict[int, dict] = {}
    errors: list = []
    for ck, (_creds, grp) in endpoints.items():
        r = results.get(ck)
        if r is None:  # não terminou dentro do deadline agregado
            for c in grp:
                by_cmig[c.id] = {"parcial": True, "truncado": False,
                                 "error": None, "confiavel": False}
            continue
        if "error" in r:
            errors.append(r["error"])
            for c in grp:
                by_cmig[c.id] = {"parcial": False, "truncado": False,
                                 "error": r["error"], "confiavel": False}
            continue
        scan = r["scan"]
        rel = {"parcial": scan["parcial"], "truncado": scan["truncado"],
               "error": None, "confiavel": not scan["parcial"] and not scan["truncado"]}
        for c in grp:
            by_cmig[c.id] = rel
        for o in scan["raw"]:
            cmig, ambiguo, in_scope = _attribute_cmig(o, grp)
            if not in_scope:
                continue  # ordem de terceiro (documento não casa nenhuma CMIG acessível)
            row = _eship_ordem_row(o)
            key = row.get("eship_order_id") or row.get("numero_origem")
            if key in seen:  # dedup (defensivo)
                continue
            seen.add(key)
            row["id_tipo"] = o.get("idTipo")
            row["cmig_id"] = cmig.id if cmig else None
            row["cmig_name"] = cmig.company_name if cmig else None
            row["cmig_ambiguo"] = ambiguo
            ordens.append(row)
    # CMIGs sem credencial/varredura → confiabilidade desconhecida (indeterminado, não divergência).
    for c in cmigs:
        by_cmig.setdefault(c.id, {"parcial": False, "truncado": False,
                                  "error": None, "confiavel": False, "sem_scan": True})
    return {
        "ordens": ordens,
        "total": len(ordens),
        "by_cmig": by_cmig,
        "errors": errors,
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
        creds,
        FUNC_GET_ORDEM,
        {
            "numeroOrigem": order.platform_order_id or str(order.id),
            "incluirInfo": True,  # obrigatório no schema do GetOrdem
            "pagina": 1,
        },
    )
    status_id, tracking, url = extract_status(resp)
    ship_status, order_status = map_status(status_id)

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

    # Garante o transporte na ordem do WMS (idempotente via selo `eship_transporte_codigo`).
    # Reaproveita o `resp` do GetOrdem acima — sem chamada extra p/ resolver o id interno real.
    # Best-effort: nunca derruba o sync de status. É o "quando eu sincronizar, atualiza o transporte
    # dos já enviados" — roda uma vez por pedido (depois o selo pula, sem martelar o scheduler).
    try:
        await ensure_order_transport(db, order, creds, resp=resp)
    except Exception as e:  # noqa: BLE001
        logger.warning("[eShip] pedido=%s: transporte no sync falhou: %s", order.id, e)

    return changed

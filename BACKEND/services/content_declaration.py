"""Declaração de Conteúdo (SEM VALOR FISCAL) em ZPL — uma por pedido.

Gerada JUNTO com as etiquetas dos marketplaces no ZIP da tela de Pedidos. Segue o modelo da
Declaração de Conteúdo dos Correios: remetente + destinatário + itens do pedido (com a miniatura
da foto de capa de cada produto) + o texto legal + linha de assinatura. NÃO tem efeito fiscal —
é declaração postal, não nota fiscal.

Isolado de propósito: reaproveita os helpers ZPL de `label_service` (`_zpl_text`, `_format_address`)
mas NÃO altera o renderizador das etiquetas de envio. A imagem vira ^GFA 1-bit (PIL) — em térmico
sai pontilhada; é a única forma de imagem em ZPL.
"""
from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG
from models.order import Order, OrderItem
import json

from services.label_meta import resolve_item_base
from services.label_service import _zpl_text

logger = logging.getLogger(__name__)

ZPL_W = 800  # 100 mm @ 8 dots/mm

# Texto legal exato do modelo de Declaração de Conteúdo (art. 4º LC 87/1996 + art. 13 Lei 6.538/78).
DECLARACAO_TEXT = (
    "Declaro que nao me enquadro no conceito de contribuinte previsto no art. 4o da Lei "
    "Complementar no 87/1996, uma vez que nao realizo, com habitualidade ou em volume que "
    "caracterize intuito comercial, operacoes de circulacao de mercadoria, ainda que se iniciem "
    "no exterior, ou estou dispensado da emissao da nota fiscal por forca da legislacao tributaria "
    "vigente, responsabilizando-me, nos termos da lei e a quem de direito, por informacoes "
    "inveridicas. Declaro ainda que nao estou postando conteudo inflamavel, explosivo, causador de "
    "combustao espontanea, toxico, corrosivo, gas ou qualquer outro conteudo que constitua perigo, "
    "conforme o art. 13 da Lei Postal no 6.538/78."
)
OBSERVACAO_TEXT = (
    "OBSERVACAO: Constitui crime contra a ordem tributaria suprimir ou reduzir tributo, ou "
    "contribuicao social e qualquer acessorio (Lei 8.137/90 Art. 1o, V)."
)

_THUMB_W = 96          # largura da miniatura em dots (12 mm) — múltiplo de 8
_THUMB_MAX_H = 104     # teto de altura da miniatura
_IMG_MAX_BYTES = 3_000_000  # teto anti-imagem-gigante no download
_FETCH_TIMEOUT = 5.0        # por imagem
_BATCH_IMAGE_BUDGET = 60    # teto de imagens baixadas por ZIP em lote (anti-DoS)


async def _host_is_safe(host: str) -> bool:
    """Bloqueia SSRF: recusa host que resolva para IP privado/loopback/link-local/reservado.

    Sem isso, uma URL de imagem vinda do banco (`CMIGProductImage.url` etc.) poderia apontar para
    `169.254.169.254` (metadados da nuvem, expõe credenciais IAM) ou para o IP interno do host.
    """
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified
        ):
            return False
    return True


def _atxt(v) -> str:
    """Desembrulha valores de endereço do ML: `{"id":..,"name":..}` → o nome; str → str."""
    if isinstance(v, dict):
        return str(v.get("name") or v.get("id") or "").strip()
    return str(v or "").strip()


def _dest_address_lines(raw) -> list[str]:
    """Linhas legíveis do endereço do destinatário, robustas ao formato do ML (`{id,name}` em
    bairro/cidade/estado) e ao formato plano (Shopee/manual). NÃO usa o `_format_address`
    compartilhado, que não desembrulha esses objetos (bug latente que a etiqueta manual não toca).
    """
    data: dict = {}
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return [raw.strip()] if raw.strip() else []
    elif isinstance(raw, dict):
        data = raw
    if not data:
        return ["(endereco nao cadastrado)"]

    def g(*keys):
        for k in keys:
            if data.get(k):
                return _atxt(data[k])
        return ""

    rua = g("street_name", "logradouro", "street", "address_line")
    numero = g("street_number", "number", "numero")
    comp = g("comment", "complement", "complemento")
    bairro = g("neighborhood", "bairro")
    cidade = g("city", "municipio", "cidade")
    uf = g("state", "estado", "uf")
    cep = g("zip_code", "cep", "zip")

    lines: list[str] = []
    l1 = " ".join(x for x in [rua, numero] if x)
    if comp:
        l1 = f"{l1} - {comp}" if l1 else comp
    if l1:
        lines.append(l1)
    if bairro:
        lines.append(bairro)
    cidade_uf = "/".join(x for x in [cidade, uf] if x)
    tail = " - ".join(x for x in [cidade_uf, f"CEP {cep}" if cep else ""] if x)
    if tail:
        lines.append(tail)
    return lines or ["(endereco nao cadastrado)"]


def _wrap(text: str, max_chars: int) -> list[str]:
    """Quebra por palavras em linhas de até `max_chars`."""
    out: list[str] = []
    line = ""
    for word in (text or "").split():
        if len(line) + len(word) + (1 if line else 0) <= max_chars:
            line = f"{line} {word}".strip()
        else:
            if line:
                out.append(line)
            line = word[:max_chars]
    if line:
        out.append(line)
    return out


def _money(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cmig_address_lines(cmig: CMIG) -> list[str]:
    lines: list[str] = []
    rua = " ".join(x for x in [cmig.street, cmig.address_number] if x)
    if rua:
        lines.append(rua)
    cidade = "/".join(x for x in [cmig.city, cmig.state] if x)
    cep = f"CEP {cmig.zip_code}" if cmig.zip_code else ""
    tail = " - ".join(x for x in [cidade, cep] if x)
    if tail:
        lines.append(tail)
    return lines


async def _resolve_cover_url(db: AsyncSession, base: dict) -> str | None:
    """URL da foto de CAPA do produto vinculado (imagem primária). `order_items.thumbnail_url`
    vive vazio no sistema, então a capa vem das imagens do produto CMIG/PG."""
    kind = base.get("kind")
    pid = base.get("product_id")
    if not pid:
        return None
    if kind == "cmig":
        from models.cmig import CMIGProductImage as Img

        q = select(Img.url).where(Img.cmig_product_id == pid)
    elif kind == "pg":
        from models.product import CatalogProductImage as Img

        q = select(Img.url).where(Img.product_id == pid)
    else:
        return None
    q = q.order_by(Img.is_primary.desc(), Img.sort_order).limit(1)
    return (await db.execute(q)).scalar_one_or_none()


async def _fetch_thumb(url: str) -> bytes | None:
    """Baixa a imagem da capa (best-effort). None em qualquer falha — a declaração sai sem foto.

    Endurecido (auditoria): valida esquema http(s), bloqueia host interno (anti-SSRF), não segue
    redirect, e baixa em STREAM cortando ao exceder `_IMG_MAX_BYTES` (não bufferiza corpo gigante).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if not await _host_is_safe(parsed.hostname):
        logger.warning("[declaracao] host de imagem bloqueado (anti-SSRF): %.80s", url)
        return None
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                clen = resp.headers.get("content-length")
                if clen and clen.isdigit() and int(clen) > _IMG_MAX_BYTES:
                    return None
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > _IMG_MAX_BYTES:
                        return None
                return bytes(buf)
    except Exception as exc:  # noqa: BLE001 — imagem é complementar, nunca derruba a declaração
        logger.warning("[declaracao] falha ao baixar miniatura %.80s: %s", url, exc)
        return None


def _png_to_gfa(png: bytes) -> tuple[str, int] | None:
    """Converte a imagem em campo gráfico ZPL 1-bit (^GFA). Retorna (comando_gfa, altura) ou None."""
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(png)).convert("L")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[declaracao] imagem ilegivel: %s", exc)
        return None
    w0, h0 = im.size
    tw = _THUMB_W
    th = max(1, min(_THUMB_MAX_H, round(h0 * tw / max(1, w0))))
    im = im.resize((tw, th)).convert("1")  # 1-bit (dither)
    px = im.load()
    bpr = tw // 8
    data = bytearray()
    for y in range(th):
        acc = 0
        bit = 0
        for x in range(tw):
            # PIL '1': 0=preto, 255=branco. ZPL ^GF: bit 1 = ponto preto → inverte.
            acc = (acc << 1) | (1 if px[x, y] == 0 else 0)
            bit += 1
            if bit == 8:
                data.append(acc)
                acc = 0
                bit = 0
    total = bpr * th
    return f"^GFA,{total},{total},{bpr},{data.hex().upper()}", th


def _render(order: Order, cmig: CMIG | None, rows: list[dict], total: float) -> str:
    body: list[str] = []
    y = 24

    body.append(_zpl_text(20, y, 40, "DECLARACAO DE CONTEUDO"))
    body.append(_zpl_text(560, y + 10, 26, "SEM VALOR FISCAL"))
    y += 56
    body.append(f"^FO20,{y}^GB760,3,3^FS")
    y += 16

    # REMETENTE sempre visível — o modelo dos Correios exige remetente; sem CMIG, deixa explícito
    # o que falta (não some em silêncio).
    body.append(_zpl_text(20, y, 24, "REMETENTE"))
    y += 30
    if cmig:
        body.append(_zpl_text(20, y, 24, (cmig.company_name or "")[:52]))
        y += 28
        if cmig.cnpj:
            body.append(_zpl_text(20, y, 22, f"CNPJ: {cmig.cnpj}"))
            y += 26
        for ln in _cmig_address_lines(cmig)[:2]:
            body.append(_zpl_text(20, y, 22, ln[:56]))
            y += 26
    else:
        body.append(_zpl_text(20, y, 22, "(remetente nao informado - vincule a CMIG ao pedido)"))
        y += 26
    y += 6
    body.append(f"^FO20,{y}^GB760,2,2^FS")
    y += 14

    body.append(_zpl_text(20, y, 24, "DESTINATARIO"))
    y += 30
    body.append(_zpl_text(20, y, 26, (order.buyer_name or "(sem nome)")[:48]))
    y += 30
    doc = (order.buyer_document or "").strip()
    if doc:
        body.append(_zpl_text(20, y, 22, f"CPF/CNPJ: {doc}"))
        y += 26
    for ln in _dest_address_lines(order.shipping_address)[:5]:
        body.append(_zpl_text(20, y, 22, ln[:56]))
        y += 26
    y += 6
    body.append(f"^FO20,{y}^GB760,2,2^FS")
    y += 14

    body.append(_zpl_text(20, y, 24, f"PEDIDO: {order.platform_order_id or order.id}"))
    y += 34
    body.append(_zpl_text(20, y, 22, "PRODUTOS"))
    body.append(_zpl_text(600, y, 22, "QTD"))
    body.append(_zpl_text(680, y, 22, "VALOR"))
    y += 30

    for r in rows:
        top = y
        if r.get("gfa"):
            body.append(f"^FO20,{top}{r['gfa']}^FS")
        tx = 130
        ty = top
        for tl in _wrap(r["title"], 40)[:2]:
            body.append(_zpl_text(tx, ty, 22, tl))
            ty += 26
        body.append(_zpl_text(tx, ty, 20, f"SKU: {r['sku'] or '-'}"))
        ty += 24
        body.append(_zpl_text(600, top, 22, str(r["qty"])))
        body.append(_zpl_text(680, top, 22, _money(r["value"])))
        row_h = max(r.get("gfa_h", 0) + 10, ty - top)
        y = top + row_h + 10

    body.append(f"^FO20,{y}^GB760,2,2^FS")
    y += 14
    body.append(_zpl_text(470, y, 26, f"TOTAL: {_money(total)}"))
    y += 42

    for ln in _wrap(DECLARACAO_TEXT, 62):
        body.append(_zpl_text(20, y, 20, ln))
        y += 24
    y += 20

    body.append(f"^FO40,{y + 30}^GB300,2,2^FS")
    body.append(_zpl_text(60, y + 36, 18, "Local / Data"))
    body.append(f"^FO440,{y + 30}^GB340,2,2^FS")
    body.append(_zpl_text(450, y + 36, 18, "Assinatura do Declarante/Remetente"))
    y += 78

    for ln in _wrap(OBSERVACAO_TEXT, 66):
        body.append(_zpl_text(20, y, 18, ln))
        y += 22
    y += 20

    header = ["^XA", "^CI28", f"^PW{ZPL_W}", f"^LL{y}", "^LH0,0"]
    return "".join(header + [c for c in body if c] + ["^XZ"])


async def _resolve_listing_thumb(db: AsyncSession, order: Order, item: OrderItem) -> str | None:
    """Fallback de capa: `ProductListing.thumbnail` do anúncio (901 preenchidos), quando o produto
    não tem imagem própria. Casa pelo item do marketplace na conta do pedido."""
    ml_item_id = getattr(item, "ml_item_id", None)
    if not ml_item_id or not order.account_id:
        return None
    from models.product import ProductListing

    return (
        await db.execute(
            select(ProductListing.thumbnail).where(
                ProductListing.account_id == order.account_id,
                ProductListing.platform_item_id == str(ml_item_id),
                ProductListing.thumbnail.isnot(None),
            ).limit(1)
        )
    ).scalar_one_or_none()


async def build_order_declaration_zpl(
    db: AsyncSession, order: Order, *, image_budget: list[int] | None = None
) -> bytes:
    """ZPL (bytes) da Declaração de Conteúdo de UM pedido — destinatário + produtos (com
    miniatura) + texto legal. Serve qualquer plataforma (ML, Shopee, manual).

    `image_budget`: contador mutável [n] compartilhado no lote — quando zera, para de baixar
    imagens (o texto ainda sai). Protege contra baixar N×M imagens num ZIP grande.
    """
    items = (
        await db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
        )
    ).scalars().all()
    cmig = None
    if order.cmig_id:
        cmig = (await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))).scalar_one_or_none()

    rows: list[dict] = []
    total = 0.0
    for it in items:
        base = await resolve_item_base(db, it, order)
        qty = it.quantity or 1
        value = float(it.unit_price or 0) * qty
        total += value
        gfa = None
        gfa_h = 0
        if image_budget is None or image_budget[0] > 0:
            cover_url = (
                it.thumbnail_url
                or await _resolve_cover_url(db, base)
                or await _resolve_listing_thumb(db, order, it)
            )
            if cover_url:
                if image_budget is not None:
                    image_budget[0] -= 1
                png = await _fetch_thumb(cover_url)
                if png:
                    res = _png_to_gfa(png)
                    if res:
                        gfa, gfa_h = res
        rows.append({
            "title": (it.title or base.get("title") or "").strip(),
            "sku": (it.sku or base.get("sku") or "").strip(),
            "qty": qty,
            "value": value,
            "gfa": gfa,
            "gfa_h": gfa_h,
        })

    return _render(order, cmig, rows, total).encode("utf-8")


def declaration_filename(order: Order) -> str:
    """Nome do arquivo .txt da Declaração de Conteúdo no ZIP (evita colisão com a DC-e fiscal)."""
    from services.file_naming import TIPO_DECLARACAO_POSTAL, order_download_filename

    return order_download_filename(TIPO_DECLARACAO_POSTAL, "txt", order=order)


async def append_declaration(
    db: AsyncSession,
    order: Order,
    files: list[tuple[str, bytes]],
    warnings: list[str],
    *,
    image_budget: list[int] | None = None,
) -> None:
    """Anexa a Declaração de Conteúdo (ZPL .txt) do pedido à lista de arquivos do ZIP. Best-effort:
    falhar não derruba o ZIP (vira aviso). Reutilizável por qualquer fluxo que baixe etiquetas
    (Pedidos e Separação/Carrinho Gaiola)."""
    try:
        dec = await build_order_declaration_zpl(db, order, image_budget=image_budget)
        files.append((declaration_filename(order), dec))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Pedido {order.id}: declaração de conteúdo não gerada ({exc}).")

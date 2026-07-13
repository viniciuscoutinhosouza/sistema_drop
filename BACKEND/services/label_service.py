"""Geracao de etiqueta de envio para pedidos diretos/manuais.

Layout: A4 com 4 etiquetas por pagina (2x2 grid). Cada etiqueta ocupa 1/4 da
pagina com borda em todos os lados e ~10mm de espacamento (gap) entre elas.
Quando o pedido tem mais de 4 itens, o PDF tem multiplas paginas.

Conteudo de cada etiqueta:
  - Cabecalho: VENDA DIRETA - sem marketplace + razao social/CNPJ da CMIG
  - Numero do pedido (Order.id) em texto grande + barcode CODE128
  - SKU do produto + barcode CODE128
  - EAN do produto + barcode EAN13 (apenas quando 13 digitos numericos)
  - Nome do produto
  - Nome do cliente + endereco completo
"""

from __future__ import annotations

import io
import json
from typing import Any

from barcode import EAN13, Code128
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# A4 = 210 x 297 mm
PAGE_W, PAGE_H = A4
PAGE_MARGIN = 10 * mm  # margem da pagina inteira
GAP = 10 * mm  # ~1 cm entre etiquetas

# Cada etiqueta: (areaUtil - gap) / 2 em cada eixo
LABEL_W = (PAGE_W - 2 * PAGE_MARGIN - GAP) / 2
LABEL_H = (PAGE_H - 2 * PAGE_MARGIN - GAP) / 2

# Padding interno de cada etiqueta (entre a borda e o conteudo)
INNER_PAD = 3 * mm


def _barcode_png(value: str, kind: str = "code128") -> bytes | None:
    """Renderiza um codigo de barras como PNG em memoria. Retorna None se invalido."""
    if not value:
        return None
    try:
        opts = {"write_text": False, "module_height": 8.0, "quiet_zone": 1.0}
        buf = io.BytesIO()
        if kind == "ean13":
            digits = "".join(c for c in str(value) if c.isdigit())
            if len(digits) not in (12, 13):
                return None
            EAN13(digits[:12], writer=ImageWriter()).write(buf, options=opts)
        else:
            Code128(str(value), writer=ImageWriter()).write(buf, options=opts)
        return buf.getvalue()
    except Exception:
        return None


def _draw_barcode(c: canvas.Canvas, x: float, y: float, w: float, h: float, png: bytes | None):
    if not png:
        return
    img = ImageReader(io.BytesIO(png))
    c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask="auto")


def _format_address(shipping_address_raw: Any) -> list[str]:
    """Converte shipping_address (CLOB json) em linhas legíveis."""
    if not shipping_address_raw:
        return ["(endereço não cadastrado)"]
    data: dict = {}
    if isinstance(shipping_address_raw, str):
        try:
            data = json.loads(shipping_address_raw)
        except Exception:
            return [shipping_address_raw]
    elif isinstance(shipping_address_raw, dict):
        data = shipping_address_raw
    lines: list[str] = []
    rua = data.get("street") or data.get("rua") or ""
    numero = data.get("number") or data.get("address_number") or data.get("numero") or ""
    complemento = data.get("complement") or data.get("complemento") or ""
    bairro = data.get("neighborhood") or data.get("bairro") or ""
    cidade = data.get("city") or data.get("cidade") or ""
    uf = data.get("state") or data.get("uf") or ""
    cep = data.get("zip_code") or data.get("cep") or ""
    if rua or numero:
        parte = f"{rua}, {numero}".strip(", ")
        if complemento:
            parte += f" - {complemento}"
        lines.append(parte)
    if bairro:
        lines.append(bairro)
    if cidade or uf:
        lines.append(f"{cidade}/{uf}".strip("/"))
    if cep:
        lines.append(f"CEP: {cep}")
    return lines or ["(endereço não cadastrado)"]


# Posicoes (origem inferior-esquerda) das 4 etiquetas na pagina A4
def _label_origin(slot: int) -> tuple[float, float]:
    """Retorna (x, y) do canto inferior-esquerdo da etiqueta no slot 0..3.

    Slots:
      0 1
      2 3
    """
    col = slot % 2
    row = slot // 2
    # row 0 = topo da pagina, row 1 = fundo
    x = PAGE_MARGIN + col * (LABEL_W + GAP)
    y_top = PAGE_H - PAGE_MARGIN - row * (LABEL_H + GAP)
    y = y_top - LABEL_H
    return x, y


def _draw_label(
    c: canvas.Canvas,
    slot: int,
    *,
    order,
    item,
    item_meta: dict,
    cmig,
    volume_idx: int,
    total_volumes: int,
):
    """Desenha 1 etiqueta dentro do slot (0..3) da pagina atual."""
    x0, y0 = _label_origin(slot)

    # --- Borda da etiqueta ---
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.7)
    c.rect(x0, y0, LABEL_W, LABEL_H)

    # Area interna (descontando padding)
    ix = x0 + INNER_PAD
    iw = LABEL_W - 2 * INNER_PAD
    iy_top = y0 + LABEL_H - INNER_PAD

    # --- Cabecalho ---
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(ix, iy_top - 3 * mm, "VENDA DIRETA — sem marketplace")
    c.setFont("Helvetica", 6.5)
    empresa = (cmig.company_name if cmig else "") or ""
    cnpj = (cmig.cnpj if cmig else "") or ""
    if empresa:
        c.drawString(ix, iy_top - 5.6 * mm, empresa[:50])
    if cnpj:
        c.drawString(ix, iy_top - 7.7 * mm, f"CNPJ: {cnpj}")
    # Volume X de N (canto sup direito)
    c.setFont("Helvetica-Bold", 7)
    c.drawRightString(x0 + LABEL_W - INNER_PAD, iy_top - 3 * mm, f"Vol {volume_idx} de {total_volumes}")

    # Linha separadora abaixo do cabecalho
    sep_y = iy_top - 9.5 * mm
    c.setStrokeColorRGB(0.4, 0.4, 0.4)
    c.setLineWidth(0.4)
    c.line(ix, sep_y, ix + iw, sep_y)

    # --- Numero do pedido ---
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 6)
    c.drawString(ix, sep_y - 3 * mm, "PEDIDO")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(ix, sep_y - 9 * mm, f"#{order.id}")
    png_pedido = _barcode_png(str(order.id), "code128")
    _draw_barcode(c, ix, sep_y - 18 * mm, iw, 7.5 * mm, png_pedido)

    # --- Destinatario ---
    y_dst = sep_y - 21 * mm
    c.setFont("Helvetica", 6)
    c.drawString(ix, y_dst, "DESTINATÁRIO")
    c.setFont("Helvetica-Bold", 8)
    buyer = (order.buyer_name or "(cliente sem nome)").strip()
    c.drawString(ix, y_dst - 4 * mm, buyer[:48])
    c.setFont("Helvetica", 6.5)
    y_addr = y_dst - 7 * mm
    addr_lines = _format_address(order.shipping_address)
    for line in addr_lines[:4]:  # max 4 linhas de endereco
        c.drawString(ix, y_addr, line[:55])
        y_addr -= 2.6 * mm

    # --- Produto ---
    y_prod = y_addr - 2 * mm
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.setLineWidth(0.3)
    c.line(ix, y_prod, ix + iw, y_prod)
    c.setFont("Helvetica", 6)
    c.drawString(ix, y_prod - 3 * mm, "PRODUTO")
    c.setFont("Helvetica-Bold", 7.5)
    title = (item.title or item_meta.get("title") or "")[:55]
    c.drawString(ix, y_prod - 6 * mm, title)
    c.setFont("Helvetica", 6.5)
    c.drawString(ix, y_prod - 9 * mm, f"Qtd: {item.quantity}")

    # SKU + EAN (lado a lado)
    sku = (item.sku or "").strip()
    ean = (item_meta.get("ean") or "").strip()
    y_sku = y_prod - 12 * mm
    half_w = (iw - 2 * mm) / 2

    c.setFont("Helvetica", 6)
    c.drawString(ix, y_sku, f"SKU: {sku or '-'}")
    if sku:
        png_sku = _barcode_png(sku, "code128")
        _draw_barcode(c, ix, y_sku - 7.5 * mm, half_w, 6.5 * mm, png_sku)

    x_ean = ix + half_w + 2 * mm
    c.drawString(x_ean, y_sku, f"EAN: {ean or '-'}")
    if ean:
        png_ean = _barcode_png(ean, "ean13") or _barcode_png(ean, "code128")
        _draw_barcode(c, x_ean, y_sku - 7.5 * mm, half_w, 6.5 * mm, png_ean)


def render_manual_order_label(*, order, items, cmig, items_meta: list[dict]) -> bytes:
    """Renderiza PDF de etiquetas. Retorna bytes do arquivo.

    Layout: A4 com 4 etiquetas por pagina (2x2). Cada item vira 1 etiqueta
    (Volume X de N). Pedidos com mais de 4 itens geram multiplas paginas.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    total_volumes = len(items)
    for idx, (item, meta) in enumerate(zip(items, items_meta, strict=False)):
        slot = idx % 4
        if idx > 0 and slot == 0:
            c.showPage()
        _draw_label(
            c,
            slot,
            order=order,
            item=item,
            item_meta=meta,
            cmig=cmig,
            volume_idx=idx + 1,
            total_volumes=total_volumes,
        )

    c.save()
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Etiquetas de envio multi-pedido com layout configurável (módulo SEPARAÇÃO)
# ─────────────────────────────────────────────────────────────────────────────
# Tamanho da etiqueta térmica padrão 10x15 (100x150mm).
THERMAL_W, THERMAL_H = 100 * mm, 150 * mm


def _flatten_volumes(orders_meta: list[dict]):
    """Achata (order, item, meta, cmig, volume_idx, total) de N pedidos.

    `orders_meta`: lista de dicts {order, items, cmig, items_meta}.
    Volume é por-pedido (1..N de cada pedido), não global.
    """
    for om in orders_meta:
        order = om["order"]
        items = om.get("items") or []
        metas = om.get("items_meta") or [{} for _ in items]
        cmig = om.get("cmig")
        total = len(items)
        for vidx, (item, meta) in enumerate(zip(items, metas, strict=False), start=1):
            yield order, item, meta, cmig, vidx, total


def _render_a4_4up(orders_meta: list[dict]) -> bytes:
    """A4 com 4 etiquetas por página (2x2), N pedidos em sequência."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    idx = 0
    for order, item, meta, cmig, vidx, total in _flatten_volumes(orders_meta):
        slot = idx % 4
        if idx > 0 and slot == 0:
            c.showPage()
        _draw_label(
            c, slot, order=order, item=item, item_meta=meta, cmig=cmig,
            volume_idx=vidx, total_volumes=total,
        )
        idx += 1
    if idx == 0:
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, A4[1] - 20 * mm, "Nenhum volume para etiquetar.")
    c.save()
    return buf.getvalue()


def _draw_thermal_label(c: canvas.Canvas, *, order, item, item_meta, cmig, volume_idx, total_volumes):
    """Desenha 1 etiqueta ocupando a página inteira (100x150mm térmica)."""
    pad = 5 * mm
    ix = pad
    iw = THERMAL_W - 2 * pad
    top = THERMAL_H - pad

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.8)
    c.rect(pad / 2, pad / 2, THERMAL_W - pad, THERMAL_H - pad)

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(ix, top - 5 * mm, "VENDA DIRETA — sem marketplace")
    c.setFont("Helvetica", 8)
    empresa = (cmig.company_name if cmig else "") or ""
    cnpj = (cmig.cnpj if cmig else "") or ""
    if empresa:
        c.drawString(ix, top - 9 * mm, empresa[:55])
    if cnpj:
        c.drawString(ix, top - 12.5 * mm, f"CNPJ: {cnpj}")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(ix + iw, top - 5 * mm, f"Vol {volume_idx}/{total_volumes}")

    sep_y = top - 16 * mm
    c.setLineWidth(0.5)
    c.line(ix, sep_y, ix + iw, sep_y)

    # Pedido
    c.setFont("Helvetica", 8)
    c.drawString(ix, sep_y - 5 * mm, "PEDIDO")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(ix, sep_y - 14 * mm, f"#{order.id}")
    _draw_barcode(c, ix, sep_y - 26 * mm, iw, 10 * mm, _barcode_png(str(order.id), "code128"))

    # Destinatário
    y = sep_y - 32 * mm
    c.setFont("Helvetica", 8)
    c.drawString(ix, y, "DESTINATÁRIO")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(ix, y - 5 * mm, (order.buyer_name or "(cliente sem nome)").strip()[:45])
    c.setFont("Helvetica", 8.5)
    y_addr = y - 10 * mm
    for line in _format_address(order.shipping_address)[:5]:
        c.drawString(ix, y_addr, line[:60])
        y_addr -= 4 * mm

    # Produto
    y_prod = y_addr - 4 * mm
    c.setLineWidth(0.4)
    c.line(ix, y_prod, ix + iw, y_prod)
    c.setFont("Helvetica", 8)
    c.drawString(ix, y_prod - 5 * mm, "PRODUTO")
    c.setFont("Helvetica-Bold", 9.5)
    title = (item.title or item_meta.get("title") or "")[:60]
    c.drawString(ix, y_prod - 10 * mm, title)
    c.setFont("Helvetica", 8.5)
    c.drawString(ix, y_prod - 14 * mm, f"Qtd: {item.quantity}")

    sku = (item.sku or "").strip()
    ean = (item_meta.get("ean") or "").strip()
    y_sku = y_prod - 20 * mm
    half_w = (iw - 4 * mm) / 2
    c.setFont("Helvetica", 8)
    c.drawString(ix, y_sku, f"SKU: {sku or '-'}")
    if sku:
        _draw_barcode(c, ix, y_sku - 9 * mm, half_w, 8 * mm, _barcode_png(sku, "code128"))
    x_ean = ix + half_w + 4 * mm
    c.drawString(x_ean, y_sku, f"EAN: {ean or '-'}")
    if ean:
        png = _barcode_png(ean, "ean13") or _barcode_png(ean, "code128")
        _draw_barcode(c, x_ean, y_sku - 9 * mm, half_w, 8 * mm, png)


def _render_10x15(orders_meta: list[dict]) -> bytes:
    """Etiqueta térmica 100x150mm — 1 página por volume."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(THERMAL_W, THERMAL_H))
    drawn = 0
    for order, item, meta, cmig, vidx, total in _flatten_volumes(orders_meta):
        if drawn > 0:
            c.showPage()
        _draw_thermal_label(
            c, order=order, item=item, item_meta=meta, cmig=cmig,
            volume_idx=vidx, total_volumes=total,
        )
        drawn += 1
    if drawn == 0:
        c.setFont("Helvetica", 10)
        c.drawString(8 * mm, THERMAL_H - 12 * mm, "Nenhum volume.")
    c.save()
    return buf.getvalue()


# Registry de layouts — extensível: basta adicionar `"chave": funcao`.
LABEL_LAYOUTS = {
    "10x15": _render_10x15,
    "a4_4up": _render_a4_4up,
}
LABEL_LAYOUT_LABELS = {
    "10x15": "Térmica 10x15",
    "a4_4up": "A4 (4 por página)",
}


def render_shipping_labels(orders_meta: list[dict], layout: str = "10x15") -> bytes:
    """Renderiza etiquetas de N pedidos no layout escolhido. Retorna bytes do PDF."""
    fn = LABEL_LAYOUTS.get(layout) or LABEL_LAYOUTS["10x15"]
    return fn(orders_meta)


# ─────────────────────────────────────────────────────────────────────────────
# Etiqueta ZPL nativa (impressora térmica Zebra) — 10x15 @ 203 dpi
# ─────────────────────────────────────────────────────────────────────────────
# 100x150mm = 800x1200 dots (8 dots/mm). Um rótulo (^XA..^XZ) por volume.
# ZPL é sempre por-volume/térmico — o layout A4/4-up (papel) não tem análogo aqui.
ZPL_W, ZPL_H = 800, 1200


def _zpl_escape(s: Any) -> str:
    """Neutraliza os caracteres de controle do ZPL (^ ~ \\) e quebras de linha."""
    if not s:
        return ""
    out = str(s).replace("\\", " ").replace("^", " ").replace("~", " ")
    return out.replace("\r", " ").replace("\n", " ").strip()


def _zpl_text(x: int, y: int, h: int, s: Any, w: int | None = None) -> str:
    txt = _zpl_escape(s)
    if not txt:
        return ""
    return f"^FO{x},{y}^A0N,{h},{w or h}^FD{txt}^FS"


def _zpl_barcode128(x: int, y: int, h: int, data: Any) -> str:
    # Imprimíveis ASCII, MAS removendo ^ ~ \ (metacaracteres do ZPL): um SKU como
    # "X^XZ^XA..." encerraria a etiqueta e injetaria comandos na impressora se entrasse cru.
    clean = "".join(c for c in str(data or "") if 32 <= ord(c) < 127 and c not in "^~\\")
    if not clean:
        return ""
    return f"^FO{x},{y}^BY2^BCN,{h},N,N,N^FD{clean}^FS"


def _zpl_barcode_ean(x: int, y: int, h: int, data: Any) -> str | None:
    """EAN-13; retorna None quando não há 12/13 dígitos (o chamador cai no Code128)."""
    digits = "".join(c for c in str(data or "") if c.isdigit())
    if len(digits) not in (12, 13):
        return None
    return f"^FO{x},{y}^BY2^BEN,{h},N,N^FD{digits[:12]}^FS"


def _zpl_one_label(*, order, item, item_meta: dict, cmig, volume_idx: int, total_volumes: int) -> str:
    """Monta 1 etiqueta ZPL (10x15) de um volume."""
    p: list[str] = ["^XA", "^CI28", f"^PW{ZPL_W}", f"^LL{ZPL_H}", "^LH0,0"]
    empresa = (cmig.company_name if cmig else "") or ""
    cnpj = (cmig.cnpj if cmig else "") or ""

    # Cabeçalho
    p.append(_zpl_text(20, 20, 30, "VENDA DIRETA - sem marketplace"))
    p.append(_zpl_text(560, 22, 26, f"Vol {volume_idx}/{total_volumes}"))
    if empresa:
        p.append(_zpl_text(20, 58, 24, empresa[:48]))
    if cnpj:
        p.append(_zpl_text(20, 88, 22, f"CNPJ: {cnpj}"))
    p.append("^FO20,118^GB760,2,2^FS")

    # Pedido + código de barras
    p.append(_zpl_text(20, 132, 22, "PEDIDO"))
    p.append(_zpl_text(20, 158, 64, f"#{order.id}"))
    p.append(_zpl_barcode128(20, 232, 90, str(order.id)))

    # Destinatário
    p.append(_zpl_text(20, 340, 22, "DESTINATARIO"))
    p.append(_zpl_text(20, 368, 30, (order.buyer_name or "(cliente sem nome)").strip()[:40]))
    y = 405
    for line in _format_address(order.shipping_address)[:5]:
        p.append(_zpl_text(20, y, 24, line[:52]))
        y += 30
    y += 6
    p.append(f"^FO20,{y}^GB760,2,2^FS")
    y += 16

    # Produto
    p.append(_zpl_text(20, y, 22, "PRODUTO"))
    y += 28
    title = (item.title or item_meta.get("title") or "")[:46]
    p.append(_zpl_text(20, y, 26, title))
    y += 32
    p.append(_zpl_text(20, y, 24, f"Qtd: {item.quantity}"))
    y += 42

    sku = (item.sku or "").strip()
    ean = (item_meta.get("ean") or "").strip()
    p.append(_zpl_text(20, y, 22, f"SKU: {sku or '-'}"))
    if sku:
        p.append(_zpl_barcode128(20, y + 26, 70, sku))
    p.append(_zpl_text(420, y, 22, f"EAN: {ean or '-'}"))
    if ean:
        bc = _zpl_barcode_ean(420, y + 26, 70, ean) or _zpl_barcode128(420, y + 26, 70, ean)
        if bc:
            p.append(bc)

    p.append("^XZ")
    return "".join(part for part in p if part)


def render_shipping_labels_zpl(orders_meta: list[dict]) -> bytes:
    """Etiquetas térmicas em ZPL (uma por volume) de N pedidos. Sempre 10x15 (ignora layout)."""
    labels = [
        _zpl_one_label(
            order=order, item=item, item_meta=meta, cmig=cmig,
            volume_idx=vidx, total_volumes=total,
        )
        for order, item, meta, cmig, vidx, total in _flatten_volumes(orders_meta)
    ]
    if not labels:
        labels.append("^XA^CI28^FO40,40^A0N,30,30^FDNenhum volume.^FS^XZ")
    return "\n".join(labels).encode("utf-8")


def render_manual_order_label_zpl(*, order, items, cmig, items_meta: list[dict]) -> bytes:
    """ZPL das etiquetas de um pedido manual/direto (uma por item/volume)."""
    return render_shipping_labels_zpl(
        [{"order": order, "items": items, "cmig": cmig, "items_meta": items_meta}]
    )

"""Geração do PDF da lista de picking (separação) consolidada por catálogo.

Lista o que o Operador Logístico deve buscar no galpão, somando as quantidades
de todos os pedidos selecionados (kits já expandidos em componentes pelo router).
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm


def render_picking_list(rows: list[dict], *, title: str = "Lista de Separação") -> bytes:
    """`rows`: [{title, sku, ean, qty}] já consolidados. Retorna bytes do PDF A4."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Colunas: # | Produto | SKU | EAN | Qtd | [ ]
    x_idx = MARGIN
    x_prod = MARGIN + 10 * mm
    x_sku = MARGIN + 95 * mm
    x_ean = MARGIN + 130 * mm
    x_qty = PAGE_W - MARGIN - 20 * mm
    x_chk = PAGE_W - MARGIN - 6 * mm

    total_units = sum(int(r.get("qty") or 0) for r in rows)

    def header(page_no: int):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN, PAGE_H - MARGIN, title)
        c.setFont("Helvetica", 8)
        c.drawRightString(
            PAGE_W - MARGIN, PAGE_H - MARGIN,
            datetime.now().strftime("%d/%m/%Y %H:%M") + f"  ·  pág. {page_no}",
        )
        c.setFont("Helvetica", 9)
        c.drawString(
            MARGIN, PAGE_H - MARGIN - 6 * mm,
            f"{len(rows)} itens distintos  ·  {total_units} unidades a buscar",
        )
        y = PAGE_H - MARGIN - 13 * mm
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x_idx, y, "#")
        c.drawString(x_prod, y, "PRODUTO")
        c.drawString(x_sku, y, "SKU")
        c.drawString(x_ean, y, "EAN")
        c.drawRightString(x_qty, y, "QTD")
        c.drawString(x_chk - 2 * mm, y, "OK")
        c.setLineWidth(0.5)
        c.line(MARGIN, y - 2 * mm, PAGE_W - MARGIN, y - 2 * mm)
        return y - 7 * mm

    page_no = 1
    y = header(page_no)
    c.setFont("Helvetica", 8.5)

    for i, r in enumerate(rows, start=1):
        if y < MARGIN + 10 * mm:
            c.showPage()
            page_no += 1
            y = header(page_no)
            c.setFont("Helvetica", 8.5)

        c.setFont("Helvetica", 8.5)
        c.drawString(x_idx, y, str(i))
        title_txt = (r.get("title") or "").strip()[:55]
        c.drawString(x_prod, y, title_txt or "(sem título)")
        c.drawString(x_sku, y, (r.get("sku") or "-")[:22])
        c.drawString(x_ean, y, (r.get("ean") or "-")[:16])
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(x_qty, y, str(int(r.get("qty") or 0)))
        # checkbox
        c.setLineWidth(0.6)
        c.rect(x_chk - 3.5 * mm, y - 1 * mm, 4 * mm, 4 * mm)
        c.setFont("Helvetica", 8.5)

        # separador leve
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(0.3)
        c.line(MARGIN, y - 2.5 * mm, PAGE_W - MARGIN, y - 2.5 * mm)
        c.setStrokeColorRGB(0, 0, 0)
        y -= 6.5 * mm

    if not rows:
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, "Nenhum item para separar.")

    c.save()
    return buf.getvalue()

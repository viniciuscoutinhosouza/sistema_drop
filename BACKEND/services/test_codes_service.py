"""Seção/folha de CÓDIGOS DE TESTE da Separação (CODE128 por SKU + tirar/fim foto).

⚠️ TEMPORÁRIO — uso exclusivo de TESTE a pedido do dono ("depois vou excluir").
Mantido isolado de propósito: para remover, apague este módulo, o trecho `test_code_items`
em `picking_list_service.render_picking_list` e o `include_test_codes` em
`routers/separation.py::picking_list_pdf`.

Usa CODE128 (código de barras 1D) como primário — compatível com leitor laser de bancada,
que NÃO lê QR. O texto do código vai embaixo para digitação/conferência manual.
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from services.label_service import _barcode_png

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
COLS = 2
CELL_W = (PAGE_W - 2 * MARGIN) / COLS
BC_W = CELL_W - 8 * mm       # largura do código de barras na célula
BC_H = 16 * mm               # altura do código de barras
CELL_H = BC_H + 12 * mm      # barras + 2 linhas de legenda


def draw_code_grid(c: canvas.Canvas, items: list[dict], *, title: str, start_new_page: bool = False) -> None:
    """Desenha uma grade de CODE128 (com legenda) num canvas JÁ aberto, paginando sozinho.
    `items`: [{code, label}]. Pula code vazio. Se `start_new_page`, abre página antes de começar."""
    if start_new_page:
        c.showPage()

    def header(page_no: int) -> float:
        c.setFont("Helvetica-Bold", 13)
        c.drawString(MARGIN, PAGE_H - MARGIN, title)
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColorRGB(0.6, 0.2, 0.2)
        c.drawString(MARGIN, PAGE_H - MARGIN - 5 * mm,
                     "Folha de TESTE — remover depois. Bipe o código de barras p/ localizar/fotografar.")
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN, f"pág. {page_no}")
        return PAGE_H - MARGIN - 12 * mm  # topo da 1ª fileira de células

    page_no = 1
    top = header(page_no)
    col = 0
    row_top = top
    desenhou = False

    for it in items:
        code = (it.get("code") or "").strip()
        if not code:
            continue
        desenhou = True
        if col == 0 and row_top - CELL_H < MARGIN:
            page_no += 1
            c.showPage()
            row_top = header(page_no)
        x = MARGIN + col * CELL_W
        cxc = x + CELL_W / 2
        png = _barcode_png(code, "code128")
        by = row_top - BC_H
        if png:
            c.drawImage(ImageReader(io.BytesIO(png)), x + 4 * mm, by, width=BC_W, height=BC_H,
                        preserveAspectRatio=True, mask="auto")
        else:
            c.rect(x + 4 * mm, by, BC_W, BC_H)
        label = (it.get("label") or "").strip()[:40]
        c.setFont("Helvetica", 7)
        if label:
            c.drawCentredString(cxc, by - 4 * mm, label)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(cxc, by - 9 * mm, code[:40])

        col += 1
        if col >= COLS:
            col = 0
            row_top -= CELL_H

    if not desenhou:
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, top, "Nenhum SKU/EAN para gerar código de teste.")


def render_test_codes(items: list[dict], *, title: str = "Códigos de teste — Separação") -> bytes:
    """Folha A4 autônoma de códigos de teste (CODE128). Retorna bytes do PDF."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_code_grid(c, items, title=title)
    c.save()
    return buf.getvalue()

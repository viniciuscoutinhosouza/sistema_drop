"""Folha de CÓDIGOS DE TESTE da Separação (QR por SKU + tirar-foto + fim-fotos).

⚠️ TEMPORÁRIO — uso exclusivo de TESTE a pedido do dono ("depois vou excluir").
Mantido isolado de propósito: para remover, apague este módulo, a rota
`POST /separation/test-codes.pdf` e o botão no front — sem tocar no
`picking_list_service` (compartilhado com o link público).
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from services.label_service import _qr_png

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
COLS = 4
QR_SIZE = 34 * mm
CELL_W = (PAGE_W - 2 * MARGIN) / COLS
CELL_H = QR_SIZE + 12 * mm  # QR + 2 linhas de legenda


def render_test_codes(items: list[dict], *, title: str = "Códigos de teste — Separação") -> bytes:
    """`items`: [{code, label}] já filtrados (code não-vazio). Desenha uma grade de QR Codes
    com legenda (label + code) para bipagem de teste. Retorna bytes do PDF A4."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def header(page_no: int):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN, PAGE_H - MARGIN, title)
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColorRGB(0.6, 0.2, 0.2)
        c.drawString(MARGIN, PAGE_H - MARGIN - 5 * mm,
                     "Folha de TESTE — remover depois. Bipe os QR para localizar/fotografar.")
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN, f"pág. {page_no}")
        return PAGE_H - MARGIN - 12 * mm  # topo da 1ª fileira de células

    page_no = 1
    top = header(page_no)
    col = 0
    row_top = top

    for it in items:
        code = (it.get("code") or "").strip()
        if not code:
            continue
        if col == 0 and row_top - CELL_H < MARGIN:
            c.showPage()
            page_no += 1
            row_top = header(page_no)
        x = MARGIN + col * CELL_W
        # QR centralizado na célula
        png = _qr_png(code)
        qx = x + (CELL_W - QR_SIZE) / 2
        qy = row_top - QR_SIZE
        if png:
            c.drawImage(ImageReader(io.BytesIO(png)), qx, qy, width=QR_SIZE, height=QR_SIZE,
                        preserveAspectRatio=True, mask="auto")
        else:
            c.rect(qx, qy, QR_SIZE, QR_SIZE)
        # legenda
        cxc = x + CELL_W / 2
        label = (it.get("label") or "").strip()[:28]
        c.setFont("Helvetica", 7)
        if label:
            c.drawCentredString(cxc, qy - 4 * mm, label)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cxc, qy - 8.5 * mm, code[:28])

        col += 1
        if col >= COLS:
            col = 0
            row_top -= CELL_H

    if not any((it.get("code") or "").strip() for it in items):
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, top, "Nenhum SKU/EAN para gerar código de teste.")

    c.save()
    return buf.getvalue()

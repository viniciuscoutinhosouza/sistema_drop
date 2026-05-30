"""Geração de PDFs de relatórios CMIG (tabela de preços e estoque)."""

import asyncio
import io
import logging
import os
from datetime import datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException
from PIL import Image as PILImage
from reportlab.lib import colors

logger = logging.getLogger(__name__)
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.user import User

_STATIC_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"
)


# ── Auth + data fetching ────────────────────────────────────────────────────────


async def _get_cmig_or_403(db: AsyncSession, cmig_id: int, user: User) -> CMIG:
    cmig = (
        await db.execute(select(CMIG).where(CMIG.id == cmig_id))
    ).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")

    if user.role == "admin":
        return cmig
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        return cmig
    if user.role == "ac":
        admin = (
            await db.execute(
                select(CMIGAdministrator).where(
                    and_(
                        CMIGAdministrator.user_id == user.id,
                        CMIGAdministrator.cmig_id == cmig.id,
                    )
                )
            )
        ).scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        return cmig
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


async def _fetch_products(
    db: AsyncSession, cmig_id: int, include_zero_stock: bool
) -> list[CMIGProduct]:
    # Mesmo critério do GET /cmigs/{id}/products: sem filtro por is_active,
    # já que registros legados podem ter is_active NULL no Oracle.
    stmt = (
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.images))
        .where(CMIGProduct.cmig_id == int(cmig_id))
    )
    if not include_zero_stock:
        stmt = stmt.where(CMIGProduct.stock_quantity > 0)
    result = await db.execute(stmt)
    products = list(result.scalars().all())
    products.sort(key=lambda p: (p.title or "").lower())

    print(
        f"[CMIG-REPORT] cmig_id={cmig_id!r} (type={type(cmig_id).__name__}) "
        f"include_zero_stock={include_zero_stock} -> {len(products)} produtos",
        flush=True,
    )
    if products:
        sample = products[0]
        print(
            f"[CMIG-REPORT] amostra: id={sample.id} sku={sample.sku_cmig!r} "
            f"title={sample.title!r} stock={sample.stock_quantity}",
            flush=True,
        )
    return products


# ── Helpers de renderização ─────────────────────────────────────────────────────


def _resolve_cover_url(product: CMIGProduct) -> str | None:
    if not product.images:
        return None
    primary = [i for i in product.images if i.is_primary]
    chosen = (
        primary[0]
        if primary
        else min(
            product.images,
            key=lambda x: x.sort_order if x.sort_order is not None else 9999,
        )
    )
    return (chosen.url or "").strip() or None


def _read_local_static(url: str) -> bytes | None:
    if not url.startswith("/static/"):
        return None
    rel = url[len("/static/") :]
    full = os.path.join(_STATIC_ROOT, rel.replace("/", os.sep))
    if not os.path.exists(full):
        return None
    try:
        with open(full, "rb") as f:
            return f.read()
    except Exception:
        return None


async def _prefetch_cover_bytes(products: list[CMIGProduct]) -> dict[int, bytes]:
    """Resolve a imagem de capa de cada produto.

    - URLs locais (`/static/...`) -> lê do disco.
    - URLs remotas (`http://`, `https://`) -> baixa em paralelo via httpx.
    Retorna dict {product_id: bytes_jpeg_ou_png}.
    """
    result: dict[int, bytes] = {}
    remote: list[tuple[int, str]] = []

    for p in products:
        url = _resolve_cover_url(p)
        if not url:
            continue
        if url.startswith("/static/"):
            data = _read_local_static(url)
            if data:
                result[p.id] = data
        elif url.startswith(("http://", "https://")):
            remote.append((p.id, url))

    if remote:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0), follow_redirects=True
        ) as client:

            async def _fetch(pid: int, url: str):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200 and resp.content:
                        result[pid] = resp.content
                except Exception:
                    pass

            await asyncio.gather(*(_fetch(pid, url) for pid, url in remote))

    return result


def _money_br(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _image_flowable(data: bytes | None, size_mm: float = 20):
    """Converte bytes de imagem em flowable do ReportLab.

    Usa PIL para normalizar (RGBA/P -> RGB, formato indefinido -> JPEG).
    Retorna string vazia se a imagem não puder ser carregada — célula fica vazia
    sem quebrar a renderização do PDF.
    """
    if not data:
        return ""
    try:
        pil = PILImage.open(io.BytesIO(data))
        if pil.mode in ("RGBA", "P", "LA"):
            pil = pil.convert("RGB")
        elif pil.mode != "RGB":
            pil = pil.convert("RGB")
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return Image(buf, width=size_mm * mm, height=size_mm * mm)
    except Exception:
        return ""


def _header_flowables(cmig: CMIG, title: str, total: int) -> list:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "rep_title", parent=styles["Title"], fontSize=16, leading=20, alignment=0
    )
    sub_style = ParagraphStyle(
        "rep_sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )
    cmig_name = cmig.trade_name or cmig.company_name or f"CMIG #{cmig.id}"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return [
        Paragraph(title, title_style),
        Paragraph(
            f"<b>Conta MIG:</b> {cmig_name} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Itens:</b> {total} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Gerado em:</b> {now}",
            sub_style,
        ),
        Spacer(1, 6),
    ]


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    page_w = doc.pagesize[0]
    canvas.drawRightString(page_w - 12 * mm, 8 * mm, f"Página {doc.page}")
    canvas.restoreState()


# ── PDF builders (síncronos — executados via asyncio.to_thread) ─────────────────


def _build_price_table_bytes(
    cmig: CMIG, products: list[CMIGProduct], cover_bytes: dict[int, bytes]
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title="Tabela de Precos",
    )

    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=11)

    story = _header_flowables(cmig, "Tabela de Preços", len(products))

    data = [[
        Paragraph("<b>Foto</b>", cell),
        Paragraph("<b>SKU</b>", cell),
        Paragraph("<b>EAN</b>", cell),
        Paragraph("<b>Título</b>", cell),
        Paragraph("<b>Preço de Venda</b>", cell),
    ]]
    for p in products:
        data.append([
            _image_flowable(cover_bytes.get(p.id)),
            Paragraph(p.sku_cmig or "—", cell),
            Paragraph(p.ean or "—", cell),
            Paragraph(p.title or "—", cell),
            Paragraph(_money_br(p.suggested_price), cell),
        ])

    # Largura útil em A4 paisagem: 297 - 24 (margens) = 273mm
    col_widths = [26 * mm, 35 * mm, 32 * mm, 140 * mm, 40 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3c8dbc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()


def _build_stock_report_bytes(
    cmig: CMIG, products: list[CMIGProduct], cover_bytes: dict[int, bytes]
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title="Relatorio de Estoque",
    )

    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9, leading=11)
    total_style = ParagraphStyle(
        "total", parent=styles["Normal"], fontSize=12, alignment=TA_RIGHT
    )

    story = _header_flowables(cmig, "Relatório de Estoque", len(products))

    data = [[
        Paragraph("<b>Foto</b>", cell),
        Paragraph("<b>SKU</b>", cell),
        Paragraph("<b>EAN</b>", cell),
        Paragraph("<b>Título</b>", cell),
        Paragraph("<b>Estoque</b>", cell),
        Paragraph("<b>Custo Unit.</b>", cell),
        Paragraph("<b>Custo Total</b>", cell),
    ]]

    grand_total = Decimal("0")
    for p in products:
        cost = Decimal(str(p.cost_price)) if p.cost_price is not None else Decimal("0")
        stock = int(p.stock_quantity or 0)
        line_total = cost * stock
        grand_total += line_total
        data.append([
            _image_flowable(cover_bytes.get(p.id)),
            Paragraph(p.sku_cmig or "—", cell),
            Paragraph(p.ean or "—", cell),
            Paragraph(p.title or "—", cell),
            Paragraph(str(stock), cell),
            Paragraph(_money_br(cost), cell),
            Paragraph(_money_br(line_total), cell),
        ])

    # Largura útil A4 paisagem 273mm
    col_widths = [26 * mm, 30 * mm, 28 * mm, 102 * mm, 22 * mm, 30 * mm, 35 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3c8dbc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            f"<b>CUSTO TOTAL GERAL: {_money_br(grand_total)}</b>", total_style
        )
    )

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()


# ── API pública ────────────────────────────────────────────────────────────────


async def build_price_table_pdf(
    db: AsyncSession, cmig_id: int, user: User, include_zero_stock: bool = True
) -> bytes:
    cmig = await _get_cmig_or_403(db, cmig_id, user)
    products = await _fetch_products(db, cmig_id, include_zero_stock)
    cover_bytes = await _prefetch_cover_bytes(products)
    return await asyncio.to_thread(_build_price_table_bytes, cmig, products, cover_bytes)


async def build_stock_report_pdf(
    db: AsyncSession, cmig_id: int, user: User, include_zero_stock: bool = True
) -> bytes:
    cmig = await _get_cmig_or_403(db, cmig_id, user)
    products = await _fetch_products(db, cmig_id, include_zero_stock)
    cover_bytes = await _prefetch_cover_bytes(products)
    return await asyncio.to_thread(_build_stock_report_bytes, cmig, products, cover_bytes)

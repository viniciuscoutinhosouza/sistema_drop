"""DACE — Documento Auxiliar da Declaração de Conteúdo Eletrônico (PDF).

Gera o PDF representativo da DC-e autorizada (análogo ao DANFE da NF-e), com QR-Code.
Usa apenas reportlab (já no projeto) — o QR é o widget nativo, sem dependência extra.
Layout conforme o Anexo II (DACE) e o DACE real de referência.
"""

from __future__ import annotations

import io

from lxml import etree
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_NS = {"d": "http://www.portalfiscal.inf.br/dce"}
_MODALIDADE = {"0": "0 - Transporte pelos Correios", "1": "1 - Transportadora", "2": "2 - Meios próprios"}


def _txt(el, path: str, default: str = "") -> str:
    node = el.find(path, _NS)
    return node.text if node is not None and node.text else default


def _doc_fmt(bloco) -> str:
    """CNPJ/CPF/idOutros formatado do bloco emit/dest."""
    if bloco is None:
        return ""
    cnpj = _txt(bloco, "d:CNPJ")
    if cnpj:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    cpf = _txt(bloco, "d:CPF")
    if cpf:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return _txt(bloco, "d:idOutros")


def _ender_str(bloco, tag: str) -> tuple[str, str]:
    """Retorna (endereço, cidade-UF) do grupo enderEmit/enderDest."""
    e = bloco.find(f"d:{tag}", _NS) if bloco is not None else None
    if e is None:
        return "", ""
    lgr = f"{_txt(e, 'd:xLgr')}, {_txt(e, 'd:nro')}"
    bairro = _txt(e, "d:xBairro")
    if bairro:
        lgr += f" - {bairro}"
    cep = _txt(e, "d:CEP")
    if cep:
        lgr += f" - CEP {cep}"
    cidade_uf = f"{_txt(e, 'd:xMun')} / {_txt(e, 'd:UF')}"
    return lgr, cidade_uf


def _chave_espacada(chave: str) -> str:
    return " ".join(chave[i:i + 4] for i in range(0, len(chave), 4))


def gerar_dace(xml_assinado: str, protocolo: str | None = None) -> bytes:
    """Gera o PDF do DACE a partir do XML da DC-e assinada/autorizada. Retorna bytes."""
    root = etree.fromstring(xml_assinado.encode("utf-8")) if isinstance(xml_assinado, str) else xml_assinado
    if not root.tag.endswith("}DCe") and not root.tag.endswith("DCe"):
        # pode vir só o infDCe ou um procDCe; tenta localizar
        dce = root.find(".//d:DCe", _NS)
        root = dce if dce is not None else root
    inf = root.find("d:infDCe", _NS)
    if inf is None:
        raise ValueError("XML sem infDCe — não é uma DC-e válida.")

    chave = (inf.get("Id") or "")[3:]  # remove 'DCe'
    ide = inf.find("d:ide", _NS)
    emit = inf.find("d:emit", _NS)
    dest = inf.find("d:dest", _NS)
    mkt = inf.find("d:Marketplace", _NS)
    supl = root.find("d:infDCeSupl", _NS)
    qr_url = _txt(supl, "d:qrCodDCe") if supl is not None else ""

    numero = _txt(ide, "d:nDC")
    serie = _txt(ide, "d:serie")
    dh = _txt(ide, "d:dhEmi")
    modal = _MODALIDADE.get(_txt(inf, "d:transp/d:modTrans", "0"), "0 - Correios")

    emit_end, emit_cid = _ender_str(emit, "enderEmit")
    dest_end, dest_cid = _ender_str(dest, "enderDest")

    itens = []
    for det in inf.findall("d:det", _NS):
        prod = det.find("d:prod", _NS)
        itens.append((
            _txt(prod, "d:xProd"),
            _txt(prod, "d:qCom"),
            _txt(prod, "d:vUnCom"),
            _txt(prod, "d:vProd"),
        ))
    v_dc = _txt(inf, "d:total/d:vDC")

    # ── Monta o PDF ──────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=10 * mm, bottomMargin=10 * mm,
        leftMargin=12 * mm, rightMargin=12 * mm, title=f"DACE {chave}",
    )
    styles = _styles()
    story: list = []

    # QR code
    qr = QrCodeWidget(qr_url or f"https://www.fazenda.pr.gov.br/dce/qrcode?chDCe={chave}")
    b = qr.getBounds()
    qr_draw = Drawing(28 * mm, 28 * mm, transform=[28 * mm / (b[2] - b[0]), 0, 0, 28 * mm / (b[3] - b[1]), 0, 0])
    qr_draw.add(qr)

    cab = Table(
        [[Paragraph("<b>DACE</b><br/>Declaração Auxiliar de Conteúdo Eletrônico", styles["title"]),
          Paragraph(
              f"<b>Nº</b> {numero} &nbsp; <b>Série</b> {serie}<br/>"
              f"<b>Emissão:</b> {dh}<br/>"
              f"<b>Protocolo:</b> {protocolo or '—'}<br/>"
              f"<b>Modalidade:</b> {modal}", styles["small"]),
          qr_draw]],
        colWidths=[70 * mm, 78 * mm, 30 * mm],
    )
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, colors.black)]))
    story.append(cab)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Chave de Acesso da DC-e:</b> {_chave_espacada(chave)}", styles["chave"]))
    story.append(Spacer(1, 3 * mm))

    def bloco(titulo, doc_lbl, doc_val, nome, cidade, endereco):
        return Table(
            [[Paragraph(f"<b>{titulo}</b>", styles["small"])],
             [Paragraph(f"<b>{doc_lbl}:</b> {doc_val} &nbsp;&nbsp; <b>Nome:</b> {nome}", styles["small"])],
             [Paragraph(f"<b>Cidade/UF:</b> {cidade} &nbsp;&nbsp; <b>Endereço:</b> {endereco}", styles["small"])]],
            colWidths=[178 * mm],
        )

    for tbl in (
        bloco("REMETENTE (Usuário Emitente)", "CNPJ/CPF", _doc_fmt(emit), _txt(emit, "d:xNome"), emit_cid, emit_end),
        bloco("DESTINATÁRIO", "CNPJ/CPF", _doc_fmt(dest), _txt(dest, "d:xNome"), dest_cid, dest_end),
        bloco("FISCO / MARKETPLACE / TRANSPORTADOR", "CNPJ", _doc_fmt(mkt), _txt(mkt, "d:xNome"), "", ""),
    ):
        tbl.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.black), ("TOPPADDING", (0, 0), (-1, -1), 1)]))
        story.append(tbl)
        story.append(Spacer(1, 2 * mm))

    # Itens
    linhas = [["Descrição do produto", "Qtd", "Vl. Unit.", "Vl. Total"]]
    linhas += [[Paragraph(i[0], styles["small"]), i[1], i[2], i[3]] for i in itens]
    linhas.append(["", "", Paragraph("<b>Total</b>", styles["small"]), Paragraph(f"<b>{v_dc}</b>", styles["small"])])
    t_itens = Table(linhas, colWidths=[118 * mm, 18 * mm, 21 * mm, 21 * mm])
    t_itens.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(t_itens)
    story.append(Spacer(1, 3 * mm))

    for obs in (_txt(inf, "d:infDec/d:xObs1"), _txt(inf, "d:infDec/d:xObs2")):
        if obs:
            story.append(Paragraph(obs, styles["legal"]))

    doc.build(story)
    return buf.getvalue()


def _styles() -> dict:
    return {
        "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=12, leading=14),
        "small": ParagraphStyle("s", fontName="Helvetica", fontSize=7.5, leading=9),
        "chave": ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=8, leading=10),
        "legal": ParagraphStyle("l", fontName="Helvetica", fontSize=6, leading=7, textColor=colors.HexColor("#444444")),
    }

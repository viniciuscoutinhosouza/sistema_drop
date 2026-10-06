"""Importação de produtos SIMPLES (não-kit) via planilha Excel — PG e CMIG.

Desenho VALIDATE-ALL-THEN-INSERT (padrão `routers/ncm.py`): o parser valida tudo em memória e os
endpoints carregam os SKUs existentes em UMA query, cruzam, e inserem só as linhas válidas num único
commit — evita `IntegrityError` no meio do lote (que abortaria a transação no AsyncSyncSession/Oracle).

Produto simples: sem componentes (is_composite=False), estoque 0 (entra por NF-e/pedido como o resto).
"""
from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_FILE_BYTES = 8 * 1024 * 1024  # 8 MB (comprimido)
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB descomprimido (anti zip-bomb)
MAX_ROWS = 2000

_NCM_RE = re.compile(r"\D")
_SHEET = "Produtos"

# (cabeçalho na planilha, campo interno, obrigatório, tipo)
COLUMNS = [
    ("sku", "sku", True, "str"),
    ("titulo", "title", True, "str"),
    ("descricao", "description", False, "str"),
    ("marca", "brand", False, "str"),
    ("fabricante", "manufacturer", False, "str"),
    ("modelo", "model", False, "str"),
    ("ean", "ean", False, "str"),
    ("preco_custo", "cost_price", True, "dec"),
    ("preco_sugerido", "suggested_price", False, "dec"),
    ("ncm", "ncm", False, "ncm"),
    ("cest", "cest", False, "cest"),
    ("origem", "origin", False, "origin"),
    ("peso_kg", "weight_kg", False, "dec"),
    ("altura_cm", "height_cm", False, "dec"),
    ("largura_cm", "width_cm", False, "dec"),
    ("comprimento_cm", "length_cm", False, "dec"),
    ("categoria", "category_name", False, "str"),
    # ── Codificação tributária por produto (migration 147) ──────────────────────
    # Cabeçalhos canônicos emitidos no template. Opcionais; absentes não sobrescrevem
    # (guard `_h in hmap` no parse loop). Nomes alternativos da planilha real do dono são
    # aceitos via _HEADER_ALIASES (ex.: "cst icms", "aliq. icms", "ncm do produto").
    ("cfop", "cfop", False, "str"),
    ("cst_icms", "icms_cst", False, "str"),
    ("aliq_icms", "icms_aliquota", False, "dec"),
    ("red_bc_icms", "icms_reducao_bc", False, "dec"),
    ("fcp", "fcp_aliquota", False, "dec"),
    ("cst_pis_cofins", "pis_cst", False, "str"),  # mesmo valor replicado p/ cofins_cst
    ("aliq_pis", "pis_aliquota", False, "dec"),
    ("aliq_cofins", "cofins_aliquota", False, "dec"),
    ("cst_ipi", "ipi_cst", False, "str"),
    ("aliq_ipi", "ipi_aliquota", False, "dec"),
    ("cod_enq_ipi", "ipi_cenq", False, "str"),
    ("cbenef", "cbenef", False, "str"),
    ("motivo_desoneracao", "mot_des_icms", False, "str"),
    ("cst_cbs_ibs", "ibscbs_cst", False, "str"),
    ("cclasstrib_cbs_ibs", "cclasstrib", False, "str"),
]

# Nomes alternativos de cabeçalho aceitos no import (além do canônico em COLUMNS[0]).
# A planilha real do dono usa estes rótulos; mapeamos p/ o cabeçalho canônico no parser.
# Chaves e valores são comparados já normalizados (minúsculas + trim).
_HEADER_ALIASES = {
    "ncm do produto": "ncm",
    "cest do produto": "cest",
    "cst icms": "cst_icms",
    "aliq. icms": "aliq_icms",
    "aliquota icms": "aliq_icms",
    "red. bc. icms": "red_bc_icms",
    "cst pis/cofins sai": "cst_pis_cofins",
    "aliq. pis": "aliq_pis",
    "aliq. cofins": "aliq_cofins",
    "cst ipi sai": "cst_ipi",
    "aliq. ipi": "aliq_ipi",
    "cod. enq": "cod_enq_ipi",
    "c. benef": "cbenef",
    "motivo desoneração": "mot_des_icms",
    "motivo desoneracao": "mot_des_icms",
    "cst cbs/ibs": "cst_cbs_ibs",
    "cclasstrib. cbs/ibs": "cclasstrib_cbs_ibs",
}

# Campos fiscais (migration 147) que viram colunas do produto no import. `pis_cst` propaga
# para `cofins_cst` (a planilha traz um único "CST PIS/COFINS SAI").
_FISCAL_IMPORT_FIELDS = (
    "cfop", "icms_cst", "icms_aliquota", "icms_reducao_bc", "fcp_aliquota",
    "pis_cst", "cofins_cst", "pis_aliquota", "cofins_aliquota",
    "ipi_cst", "ipi_aliquota", "ipi_cenq", "ibscbs_cst", "cclasstrib",
    "cbenef", "mot_des_icms",
)


def fiscal_import_fields(rec: dict) -> dict:
    """Extrai do registro parseado os campos fiscais por produto (migration 147) prontos para o
    construtor de CatalogProduct/CMIGProduct. Só inclui o que veio preenchido na planilha
    (ausente = NULL = usa o default da CMIG). `cofins_cst` espelha `pis_cst` quando não vier
    explícito (a planilha traz um único CST de PIS/COFINS)."""
    out = {f: rec[f] for f in _FISCAL_IMPORT_FIELDS if rec.get(f) is not None}
    if "pis_cst" in out and "cofins_cst" not in out:
        out["cofins_cst"] = out["pis_cst"]
    return out

_EXAMPLE_ROWS = [
    ["CAM-001", "Camiseta Básica Branca M", "Camiseta 100% algodão", "MinhaMarca",
     "Confecções XYZ Ltda", "Básica",
     "7891234567890", "19.90", "39.90", "61091000", "", "0", "0.2", "2", "30", "40", "Vestuário"],
    ["CANECA-PT", "Caneca Cerâmica Preta 300ml", "", "Genérica", "Cerâmica ABC", "", "", "8.50",
     "24.90", "69120000", "", "0", "0.35", "10", "9", "9", ""],
]

_INSTRUCTIONS = [
    "COMO USAR ESTA PLANILHA",
    "",
    "1. Preencha uma linha por produto na aba 'Produtos'. Não altere o cabeçalho.",
    "2. Colunas obrigatórias: sku, titulo, preco_custo.",
    "3. sku: código único do produto. No PG é único no SISTEMA inteiro; no CMIG é único dentro da CMIG.",
    "4. preco_custo / preco_sugerido / peso / dimensões: números (use ponto ou vírgula).",
    "5. origem: 0 a 8 (0 = Nacional). Em branco = 0.",
    "6. ncm: 8 dígitos (pontuação é ignorada). cest: 7 dígitos.",
    "7. categoria: nome EXATO de uma categoria já cadastrada no seu galpão. Se não existir, o produto"
    " é criado SEM categoria (você ajusta depois). Não criamos categoria automaticamente.",
    "8. Apaga as linhas de exemplo antes de importar.",
    "9. Esta planilha serve tanto para Produtos PG quanto para Produtos CMIG (a coluna 'sku' é usada",
    "   como SKU do PG ou SKU da CMIG conforme a tela em que você importar).",
    f"10. Limite: {MAX_ROWS} linhas por arquivo.",
    "11. Colunas fiscais (cfop, cst_icms, aliq_icms, cst_pis_cofins, cst_ipi, cst_cbs_ibs etc.):",
    "    opcionais. Em branco = o produto usa o PADRÃO da CMIG (Configuração Fiscal). Preencha só",
    "    para SOBRESCREVER o padrão naquele produto. CST PIS/COFINS é um valor único (vale p/ os dois).",
]


def _xlsx_safe(v):
    """Anti formula-injection: prefixa `'` em texto que começa com = + - @."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _to_dec(v):
    """Decimal tolerante (vírgula ou ponto). None/'' → None. Lança ValueError se inválido."""
    s = _s(v)
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if ("," in s and "." in s) else s.replace(",", ".")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise ValueError(f"número inválido: {v!r}") from None
    if d < 0:
        raise ValueError("não pode ser negativo")
    return d


def norm_ncm(v) -> str | None:
    d = _NCM_RE.sub("", _s(v))
    if d and len(d) != 8:
        raise ValueError("ncm deve ter 8 dígitos (ex.: 61091000)")
    return d or None


def norm_cest(v) -> str | None:
    d = _NCM_RE.sub("", _s(v))
    if d and len(d) != 7:
        raise ValueError("cest deve ter 7 dígitos")
    return d or None


# Limites das colunas do banco (CatalogProduct/CMIGProduct) — validados no parser para que um valor
# longo vire ERRO DA LINHA (relatório) em vez de estourar no commit e derrubar o lote inteiro.
_MAXLEN = {"sku": 100, "title": 500, "ean": 14, "brand": 100, "manufacturer": 100, "model": 200, "description": 4000}
_MAXNUM = {
    "cost_price": Decimal("9999999999999.99"),      # Numeric(15,2)
    "suggested_price": Decimal("9999999999999.99"),
    "weight_kg": Decimal("99999.999"),               # Numeric(8,3)
    "height_cm": Decimal("999999.99"),               # Numeric(8,2)
    "width_cm": Decimal("999999.99"),
    "length_cm": Decimal("999999.99"),
}


def _validate_limits(rec: dict) -> None:
    """Garante que os campos cabem nas colunas do banco (evita DatabaseError no commit)."""
    for field, mx in _MAXLEN.items():
        val = rec.get(field)
        if val and len(str(val)) > mx:
            raise ValueError(f"'{field}' excede {mx} caracteres")
    for field, mx in _MAXNUM.items():
        val = rec.get(field)
        if val is not None and val > mx:
            raise ValueError(f"'{field}' é grande demais (máx {mx})")


def _parse_origin(v) -> int:
    s = _s(v)
    if not s:
        return 0
    if s not in "012345678" or len(s) != 1:
        raise ValueError("origem deve ser 0 a 8")
    return int(s)


def build_template_xlsx() -> bytes:
    """Planilha modelo: aba 'Produtos' (cabeçalho + exemplos) + aba 'Instruções'."""
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = _SHEET
    head_fill = PatternFill("solid", fgColor="1F3B57")
    head_font = Font(bold=True, color="FFFFFF")
    req_fill = PatternFill("solid", fgColor="FBE9A8")  # realça obrigatórias

    headers = [c[0] for c in COLUMNS]
    ws.append(headers)
    for ci, (_h, _f, required, _t) in enumerate(COLUMNS, start=1):
        hc = ws.cell(row=1, column=ci)
        hc.fill = head_fill if not required else req_fill
        hc.font = head_font if not required else Font(bold=True, color="7A5C00")
        hc.alignment = Alignment(horizontal="center")
    for ex in _EXAMPLE_ROWS:
        ws.append([_xlsx_safe(v) for v in ex])
    widths = [14, 32, 30, 14, 20, 12, 16, 12, 14, 12, 10, 8, 9, 10, 10, 14, 18]
    for ci, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = w
    ws.freeze_panes = "A2"

    wsi = wb.create_sheet("Instruções")
    for line in _INSTRUCTIONS:
        wsi.append([_xlsx_safe(line)])
    wsi.column_dimensions["A"].width = 100

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


async def resolve_or_create_category_id(db, name, warehouse_id):
    """Resolve a categoria por nome NO GALPÃO (migration 145) e CRIA se não existir (raiz, no galpão
    do produto). Retorna (id, created). Decisão do dono: a importação cria a categoria ausente.

    Não cria categoria SEM galpão (warehouse_id None → só resolve; evita categoria órfã para admin
    sem galpão). Comparação case-insensitive para reusar categoria já existente."""
    from sqlalchemy import func, select

    from models.product import Category

    nm = (name or "").strip()
    if not nm:
        return None, False
    q = select(Category.id).where(func.lower(Category.name) == nm.lower())
    if warehouse_id is not None:
        q = q.where(Category.warehouse_id == warehouse_id)
    found = (await db.execute(q)).scalars().first()
    if found is not None:
        return found, False
    if warehouse_id is None:
        return None, False  # admin sem galpão → não cria categoria órfã
    cat = Category(name=nm[:200], warehouse_id=warehouse_id)
    db.add(cat)
    await db.flush()  # obtém o id; a próxima linha com o mesmo nome reusa (SELECT autoflush)
    return cat.id, True


def parse_products_xlsx(data: bytes) -> tuple[list[dict], list[dict]]:
    """Lê a planilha e valida cada linha. Retorna (linhas_válidas, erros).

    Cada linha válida: {campos normalizados, "_row": n, "_sku_key": sku.lower()}.
    Erros: [{"row": n, "sku": str, "motivo": str}]. Dedup intra-arquivo (SKU case-insensitive).
    Falha alto (ValueError) em arquivo não-xlsx/corrompido/grande demais — o caller vira 422.
    """
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Arquivo acima do limite de {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    # Guard anti zip-bomb: o teto de 8 MB é sobre os bytes COMPRIMIDOS; um .xlsx pode inflar muito
    # (ex.: sharedStrings.xml). Rejeita se o descomprimido ultrapassa o teto (ADR-0016, mesma ideia).
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as _zf:
            if sum(i.file_size for i in _zf.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Arquivo descomprimido grande demais (possível planilha corrompida).")
    except zipfile.BadZipFile:
        raise ValueError("Arquivo inválido — envie um .xlsx (Excel). Formato .xls antigo não é aceito.") from None
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, KeyError):
        raise ValueError("Arquivo inválido — envie um .xlsx (Excel). Formato .xls antigo não é aceito.") from None

    ws = wb[_SHEET] if _SHEET in wb.sheetnames else wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        raise ValueError("Planilha vazia.") from None

    # Mapa cabeçalho→índice (tolerante a maiúsc/espaços). Nomes alternativos da planilha real
    # (migration 147) são reescritos para o cabeçalho canônico de COLUMNS via _HEADER_ALIASES.
    hmap = {}
    for i, h in enumerate(header or []):
        key = _s(h).lower()
        if not key:
            continue
        key = _HEADER_ALIASES.get(key, key)
        hmap.setdefault(key, i)  # 1º cabeçalho vence (não sobrescreve canônico já visto)
    missing_req = [h for (h, _f, req, _t) in COLUMNS if req and h not in hmap]
    if missing_req:
        raise ValueError(f"Colunas obrigatórias ausentes no cabeçalho: {', '.join(missing_req)}")

    valid: list[dict] = []
    errors: list[dict] = []
    seen: set[str] = set()
    count = 0
    for idx, raw in enumerate(rows_iter, start=2):  # linha 1 é o cabeçalho
        if raw is None or all(_s(c) == "" for c in raw):
            continue
        count += 1
        if count > MAX_ROWS:
            raise ValueError(f"Arquivo acima do limite de {MAX_ROWS} linhas.")

        def cell(h, raw=raw):
            i = hmap.get(h)
            return raw[i] if i is not None and i < len(raw) else None

        sku = _s(cell("sku"))
        rec: dict = {"_row": idx, "sku": sku}
        try:
            if not sku:
                raise ValueError("sku é obrigatório")
            if not _s(cell("titulo")):
                raise ValueError("titulo é obrigatório")
            key = sku.lower()
            if key in seen:
                raise ValueError(f"SKU duplicado na planilha: {sku}")
            seen.add(key)

            for _h, field, _req, typ in COLUMNS:
                # Pula cabeçalhos ausentes na planilha. Sem isto, uma coluna com nome
                # alternativo (ex.: "ncm do produto" quando só há "ncm") escreveria None por
                # cima do valor já lido. Múltiplas entradas → campo = 1ª presente.
                if _h not in hmap:
                    continue
                v = cell(_h)
                if typ == "dec":
                    rec[field] = _to_dec(v)
                elif typ == "ncm":
                    rec[field] = norm_ncm(v)
                elif typ == "cest":
                    rec[field] = norm_cest(v)
                elif typ == "origin":
                    rec[field] = _parse_origin(v)
                else:
                    rec[field] = _s(v) or None
            if rec.get("cost_price") is None:
                raise ValueError("preco_custo é obrigatório")
            rec["title"] = _s(cell("titulo"))
            rec["sku"] = sku
            _validate_limits(rec)  # cabe nas colunas do banco → erro de linha, não 500 no commit
            rec["_sku_key"] = key
            valid.append(rec)
        except ValueError as e:
            errors.append({"row": idx, "sku": sku, "motivo": str(e)})

    return valid, errors

"""Lógica do Endereçamento Físico de Estoque (ADR-0039).

Funções puras/auxiliares consumidas por `routers/storage.py`: resolução de produto (+galpão),
cálculo do `full_code` da árvore, geração em massa de códigos, EAN-13 interno (prefixo 2 + DV,
único), e reconciliação endereçado × saldo escalar. NADA aqui grava saldo (camada aditiva).
"""
from __future__ import annotations

import secrets

from sqlalchemy import select

PRODUCT_TYPES = ("pg", "cmig", "variant_pg", "variant_cmig")
BOX_TOKEN_PREFIX = "BOX-"
LOC_TOKEN_PREFIX = "LOC-"
MAX_BULK = 500  # teto de filhos por geração em massa


# ── EAN-13 ────────────────────────────────────────────────────────────────────
def ean13_check_digit(body12: str) -> str:
    """Dígito verificador EAN-13 a partir dos 12 primeiros dígitos (pesos 1,3,1,3…)."""
    s = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body12))
    return str((10 - (s % 10)) % 10)


async def generate_internal_ean(db) -> str:
    """Gera um EAN-13 interno ÚNICO (prefixo '2' = uso interno, não colide com GTIN de fabricante).

    Checa colisão em product_eans (source='internal') e tenta de novo; falha alto se não achar
    um livre (improvável). O índice único funcional da migration 173 é a trava final anti-corrida.
    """
    from models.product_ean import ProductEan

    for _ in range(40):
        body = "2" + "".join(secrets.choice("0123456789") for _ in range(11))
        candidate = body + ean13_check_digit(body)
        exists = (
            await db.execute(
                select(ProductEan.id).where(
                    ProductEan.ean == candidate, ProductEan.source == "internal"
                )
            )
        ).first()
        if not exists:
            return candidate
    raise RuntimeError("Não foi possível gerar um código interno único — tente novamente.")


# ── Resolução de produto (+ galpão) ────────────────────────────────────────────
async def resolve_product_meta(db, product_type: str, product_id: int) -> dict | None:
    """Metadados de um produto p/ o endereçamento. None se não existe.

    Retorna: warehouse_id, is_composite, title, sku, main_ean, is_traceable e, p/ produto BASE
    (pg/cmig), o alvo do product_eans (`ean_target` = 'catalog_product_id' | 'cmig_product_id',
    `ean_target_id`) — variantes não têm FK em product_eans, então `ean_target` = None nelas.
    """
    from models.cmig import CMIG, CMIGProduct
    from models.product import CatalogProduct

    pt = (product_type or "").lower()
    if pt not in PRODUCT_TYPES:
        return None

    def _trk(obj) -> bool:
        return bool(
            getattr(obj, "track_lot", False)
            or getattr(obj, "track_expiry", False)
            or getattr(obj, "track_serial", False)
        )

    if pt == "pg":
        p = (await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))).scalar_one_or_none()
        if not p:
            return None
        return {
            "warehouse_id": p.warehouse_id, "is_composite": bool(p.is_composite),
            "title": p.title, "sku": p.sku, "main_ean": p.ean, "is_traceable": _trk(p),
            "ean_target": "catalog_product_id", "ean_target_id": p.id,
        }

    if pt == "cmig":
        p = (await db.execute(select(CMIGProduct).where(CMIGProduct.id == product_id))).scalar_one_or_none()
        if not p:
            return None
        cmig = (await db.execute(select(CMIG).where(CMIG.id == p.cmig_id))).scalar_one_or_none()
        return {
            "warehouse_id": getattr(cmig, "warehouse_id", None), "is_composite": bool(p.is_composite),
            "title": p.title, "sku": p.sku_cmig, "main_ean": p.ean, "is_traceable": _trk(p),
            "ean_target": "cmig_product_id", "ean_target_id": p.id,
        }

    if pt == "variant_pg":
        from models.product import CatalogProductVariant

        v = (await db.execute(select(CatalogProductVariant).where(CatalogProductVariant.id == product_id))).scalar_one_or_none()
        if not v:
            return None
        parent = (await db.execute(select(CatalogProduct).where(CatalogProduct.id == v.product_id))).scalar_one_or_none()
        title = f"{getattr(parent, 'title', '')} — {v.variant_name or v.size_label or v.sku}".strip(" —")
        return {
            "warehouse_id": getattr(parent, "warehouse_id", None), "is_composite": False,
            "title": title, "sku": v.sku, "main_ean": None, "is_traceable": _trk(parent),
            "ean_target": None, "ean_target_id": None,
        }

    # variant_cmig
    from models.cmig import CMIGProductVariant

    v = (await db.execute(select(CMIGProductVariant).where(CMIGProductVariant.id == product_id))).scalar_one_or_none()
    if not v:
        return None
    parent = (await db.execute(select(CMIGProduct).where(CMIGProduct.id == v.cmig_product_id))).scalar_one_or_none()
    cmig = (await db.execute(select(CMIG).where(CMIG.id == getattr(parent, "cmig_id", None)))).scalar_one_or_none()
    title = f"{getattr(parent, 'title', '')} — {v.variant_name or v.size_label or v.sku}".strip(" —")
    return {
        "warehouse_id": getattr(cmig, "warehouse_id", None), "is_composite": False,
        "title": title, "sku": v.sku, "main_ean": None, "is_traceable": _trk(parent),
        "ean_target": None, "ean_target_id": None,
    }


async def scalar_stock(db, product_type: str, product_id: int) -> int | None:
    """Saldo escalar LOCAL (stock_quantity) do produto — a verdade com que a reconciliação compara.

    É o saldo LOCAL (ADR-0019 replay-from-0); o FULL vive em `full_stock` e fica DE FORA (endereço
    é físico/local). Kit (is_composite) é derivado (ADR-0023) e sempre 0 → não reconcilia.
    """
    from models.cmig import CMIGProduct, CMIGProductVariant
    from models.product import CatalogProduct, CatalogProductVariant

    pt = (product_type or "").lower()
    model = {
        "pg": CatalogProduct, "cmig": CMIGProduct,
        "variant_pg": CatalogProductVariant, "variant_cmig": CMIGProductVariant,
    }.get(pt)
    if model is None:
        return None
    row = (await db.execute(select(model.stock_quantity).where(model.id == product_id))).first()
    return int(row[0]) if row and row[0] is not None else None


# ── full_code da árvore ─────────────────────────────────────────────────────────
async def build_full_code(db, parent_id: int | None, code: str) -> str:
    from models.storage import StorageLocation

    code = (code or "").strip()
    if not parent_id:
        return code
    parent = (await db.execute(select(StorageLocation).where(StorageLocation.id == parent_id))).scalar_one_or_none()
    if not parent:
        return code
    return f"{parent.full_code} / {code}"


async def recompute_subtree_full_codes(db, node) -> int:
    """Recomputa o full_code do nó (a partir do pai) e de TODA a subárvore. Retorna quantos tocou.

    Chamado quando o `code` de um pai muda (as etiquetas já impressas ficam defasadas → o router
    avisa). Itera sem recursão (seguro p/ árvores fundas)."""
    from models.storage import StorageLocation

    parent = None
    if node.parent_id:
        parent = (await db.execute(select(StorageLocation).where(StorageLocation.id == node.parent_id))).scalar_one_or_none()
    node.full_code = f"{parent.full_code} / {node.code.strip()}" if parent else node.code.strip()

    count = 1
    stack = [node]
    while stack:
        cur = stack.pop()
        children = (
            await db.execute(select(StorageLocation).where(StorageLocation.parent_id == cur.id))
        ).scalars().all()
        for ch in children:
            ch.full_code = f"{cur.full_code} / {ch.code.strip()}"
            count += 1
            stack.append(ch)
    return count


# ── Geração em massa de códigos (por pai) ───────────────────────────────────────
def generate_bulk_codes(scheme: dict) -> list[str]:
    """Códigos-filho a partir de um esquema. Levanta ValueError em entrada inválida (fail-loud).

    scheme.type:
      - 'named'   {names: [str, ...]}
      - 'numeric' {start:int, end:int, pad?:int, prefix?:str, suffix?:str}
      - 'letter'  {start:'A', end:'F', prefix?:str, suffix?:str}
    """
    t = (scheme or {}).get("type")
    prefix = str((scheme or {}).get("prefix") or "")
    suffix = str((scheme or {}).get("suffix") or "")

    if t == "named":
        names = [str(n).strip() for n in (scheme.get("names") or []) if str(n).strip()]
        if not names:
            raise ValueError("Informe ao menos um nome.")
        out = [f"{prefix}{n}{suffix}" for n in names]
    elif t == "numeric":
        start, end = int(scheme.get("start")), int(scheme.get("end"))
        if end < start:
            raise ValueError("Faixa numérica inválida (fim < início).")
        pad = int(scheme.get("pad") or 0)
        out = [f"{prefix}{str(i).zfill(pad)}{suffix}" for i in range(start, end + 1)]
    elif t == "letter":
        a, b = str(scheme.get("start") or "").strip().upper(), str(scheme.get("end") or "").strip().upper()
        if len(a) != 1 or len(b) != 1 or not a.isalpha() or not b.isalpha() or ord(b) < ord(a):
            raise ValueError("Faixa de letras inválida (use A..Z, início ≤ fim).")
        out = [f"{prefix}{chr(c)}{suffix}" for c in range(ord(a), ord(b) + 1)]
    else:
        raise ValueError("Esquema inválido (named|numeric|letter).")

    if len(out) > MAX_BULK:
        raise ValueError(f"Geração em massa limitada a {MAX_BULK} itens por vez.")
    # dedup preservando ordem
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


# ── Reconciliação ───────────────────────────────────────────────────────────────
async def warehouse_reconciliation(db, warehouse_id: int) -> list[dict]:
    """Por produto do galpão com alocação: endereçado (Σ qty_units) × saldo escalar × sem-endereço.

    Exclui kit (is_composite — saldo derivado, ADR-0023). `sem_endereco` pode ser negativo
    (over-endereçado) → sinalizado por `over=True`."""
    from sqlalchemy import func

    from models.storage import ProductAllocation

    rows = (
        await db.execute(
            select(
                ProductAllocation.product_type,
                ProductAllocation.product_id,
                func.sum(ProductAllocation.qty_units),
            )
            .where(ProductAllocation.warehouse_id == warehouse_id, ProductAllocation.is_active == True)  # noqa: E712
            .group_by(ProductAllocation.product_type, ProductAllocation.product_id)
        )
    ).all()

    out: list[dict] = []
    for ptype, pid, addressed in rows:
        meta = await resolve_product_meta(db, ptype, pid)
        if not meta or meta.get("is_composite"):
            continue
        stock = await scalar_stock(db, ptype, pid)
        addressed = int(addressed or 0)
        sem = (stock if stock is not None else 0) - addressed
        out.append({
            "product_type": ptype, "product_id": pid,
            "title": meta["title"], "sku": meta["sku"],
            "addressed": addressed, "stock": stock,
            "sem_endereco": sem, "over": sem < 0,
        })
    out.sort(key=lambda r: (r["sem_endereco"] >= 0, -abs(r["sem_endereco"])))
    return out

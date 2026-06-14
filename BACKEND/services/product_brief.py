"""Monta um resumo textual ("ficha técnica") de um produto PG ou CMIG para
injetar no contexto de prompts de IA (geração de imagem/clip). Reutilizável.

Sanitiza: trunca tamanhos e remove quebras de controle para reduzir risco de
prompt injection via campos editáveis pelo usuário (descrição/atributos).
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct
from models.product import CatalogProduct

logger = logging.getLogger(__name__)


def _clean(text: str, limit: int) -> str:
    s = " ".join(str(text).split())  # colapsa espaços/quebras
    return s[:limit]


def _attrs(raw) -> list[tuple[str, str]]:
    data = raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    out: list[tuple[str, str]] = []
    for a in data:
        if not isinstance(a, dict):
            continue
        name = a.get("name") or a.get("id")
        val = a.get("value_name") or a.get("value")
        if name and val not in (None, ""):
            out.append((_clean(name, 40), _clean(val, 80)))
    return out


async def build_product_brief(
    db: AsyncSession, product_type: str, product_id: int
) -> str:
    """Retorna um texto curto com título, marca, modelo, descrição e características
    do produto. Vazio se não encontrar."""
    if product_type == "pg":
        p = (
            await db.execute(select(CatalogProduct).where(CatalogProduct.id == product_id))
        ).scalar_one_or_none()
    elif product_type == "cmig":
        p = (
            await db.execute(select(CMIGProduct).where(CMIGProduct.id == product_id))
        ).scalar_one_or_none()
    else:
        return ""
    if not p:
        return ""

    lines: list[str] = []
    if p.title:
        lines.append(f"Produto: {_clean(p.title, 200)}")
    if getattr(p, "brand", None):
        lines.append(f"Marca: {_clean(p.brand, 80)}")
    if getattr(p, "model", None):
        lines.append(f"Modelo: {_clean(p.model, 80)}")
    if getattr(p, "description", None):
        lines.append(f"Descrição: {_clean(p.description, 800)}")
    attrs = _attrs(getattr(p, "attributes_json", None))
    if attrs:
        lines.append("Características: " + "; ".join(f"{k}: {v}" for k, v in attrs[:15]))
    return "\n".join(lines)[:2000]

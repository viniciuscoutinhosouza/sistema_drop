"""Ponto único de casamento por EAN considerando MULTI-EAN (migration 172, tabela product_eans).

Um produto pode ter 1+ EANs: o principal na coluna `.ean` do produto + adicionais em product_eans.
Estas funções são consumidas pelas TRÊS superfícies de casamento item-de-nota↔produto para manter
paridade: `stock_calculator.affected_products_from_invoice` (detecta quem recomputar) e
`stock_history._fetch_nfe_events_for_cmig_product` / `_fetch_direct_pg_events` (crédito no replay).

Normalização MÍNIMA (`.strip()`) — espelha exatamente o que o código já fazia na coluna nativa
(zero regressão: com product_eans vazio, o conjunto de EANs = [ean principal], idêntico ao de hoje).
NÃO valida dígito verificador GTIN (muitos produtos têm EAN interno/sem GTIN — bloquear quebraria
o recebimento).
"""

import logging

from sqlalchemy import select

from models.cmig import CMIGProduct
from models.product import CatalogProduct
from models.product_ean import ProductEan

logger = logging.getLogger(__name__)


def normalize_ean(s: str | None) -> str:
    """Normaliza um EAN para comparação/gravação. Mínimo: strip (igual ao casamento histórico)."""
    return (s or "").strip()


async def eans_of_cmig_product(db, cmig_product_id: int, main_ean: str | None) -> list[str]:
    """Todos os EANs do produto CMIG (principal + adicionais), normalizados e deduplicados."""
    out: list[str] = []
    m = normalize_ean(main_ean)
    if m:
        out.append(m)
    rows = (
        await db.execute(
            select(ProductEan.ean).where(ProductEan.cmig_product_id == cmig_product_id)
        )
    ).scalars().all()
    for e in rows:
        e = normalize_ean(e)
        if e and e not in out:
            out.append(e)
    return out


async def eans_of_catalog_product(db, catalog_product_id: int, main_ean: str | None) -> list[str]:
    """Todos os EANs do produto PG (principal + adicionais), normalizados e deduplicados."""
    out: list[str] = []
    m = normalize_ean(main_ean)
    if m:
        out.append(m)
    rows = (
        await db.execute(
            select(ProductEan.ean).where(ProductEan.catalog_product_id == catalog_product_id)
        )
    ).scalars().all()
    for e in rows:
        e = normalize_ean(e)
        if e and e not in out:
            out.append(e)
    return out


async def cmig_product_id_by_ean(db, cmig_id: int, ean: str | None) -> int | None:
    """Produto CMIG (desta CMIG) cujo EAN — principal OU adicional — casa com `ean`.

    Determinístico (menor id) + log.warning se >1 produto casa o mesmo EAN (fail-loud, não silencia)."""
    ean = normalize_ean(ean)
    if not ean or not cmig_id:
        return None
    ids: set[int] = set()
    ids.update(
        (await db.execute(
            select(CMIGProduct.id).where(CMIGProduct.cmig_id == cmig_id, CMIGProduct.ean == ean)
        )).scalars().all()
    )
    ids.update(
        (await db.execute(
            select(ProductEan.cmig_product_id)
            .join(CMIGProduct, CMIGProduct.id == ProductEan.cmig_product_id)
            .where(ProductEan.ean == ean, CMIGProduct.cmig_id == cmig_id)
        )).scalars().all()
    )
    ids.discard(None)
    if not ids:
        return None
    if len(ids) > 1:
        logger.warning(
            "EAN ambíguo %r na CMIG %s casa %s produtos CMIG %s — usando o menor id.",
            ean, cmig_id, len(ids), sorted(ids),
        )
    return sorted(ids)[0]


async def catalog_product_id_by_ean(db, ean: str | None) -> int | None:
    """Produto PG cujo EAN — principal OU adicional — casa com `ean` (escopo global, espelha o
    casamento PG histórico por EAN). Determinístico + log.warning em ambiguidade."""
    ean = normalize_ean(ean)
    if not ean:
        return None
    ids: set[int] = set()
    ids.update(
        (await db.execute(
            select(CatalogProduct.id).where(CatalogProduct.ean == ean)
        )).scalars().all()
    )
    ids.update(
        (await db.execute(
            select(ProductEan.catalog_product_id).where(ProductEan.ean == ean)
        )).scalars().all()
    )
    ids.discard(None)
    if not ids:
        return None
    if len(ids) > 1:
        logger.warning(
            "EAN ambíguo %r casa %s produtos PG %s — usando o menor id.", ean, len(ids), sorted(ids)
        )
    return sorted(ids)[0]

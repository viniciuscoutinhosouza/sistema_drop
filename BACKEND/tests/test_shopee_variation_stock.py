"""Resolução de variação Shopee por model_sku (baixa de estoque no produto certo).

Regressão do bug: pedido Shopee de produto com variação resolvia pelo `item_sku` (SKU do pai),
baixando o produto errado. Ex. vivo: "Bola Pilates 55cm Rosa" (model_sku=5178 → PG 84) baixava
PG 62 (75cm Preta, sku 5171). O fix resolve pelo SKU da variação, com precedência sobre o
ProductListing do item.
"""
import asyncio

from models.product import CatalogProduct
from services.order_item_resolver import _resolve_by_sku, resolve_order_item_link


def test_resolve_by_sku_casa_variacao_pg(mock_db):
    pg = CatalogProduct(id=84, sku="5178")
    mock_db.set_result(pg, rows=[pg])
    link = asyncio.run(_resolve_by_sku(mock_db, sku="5178", cmig_id=None))
    assert link is not None
    assert link.catalog_product.id == 84
    assert link.source == "variation_sku_pg"


def test_variacao_vence_o_listing(mock_db):
    # prefer_variation_sku=True (Shopee): o model_sku da variação resolve o produto ESPECÍFICO
    # ANTES do ProductListing do item_id (que apontaria para uma única variação).
    pg = CatalogProduct(id=84, sku="5178")
    mock_db.set_result(pg, rows=[pg])
    link = asyncio.run(
        resolve_order_item_link(
            mock_db,
            account_id=1,
            shopee_item_id=58263206378,
            cmig_id=None,
            sku="5178",
            prefer_variation_sku=True,
        )
    )
    assert link.catalog_product.id == 84  # PG 84 (55cm Rosa) — não o produto do listing do item
    assert link.source == "variation_sku_pg"

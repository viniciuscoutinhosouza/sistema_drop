"""Importação de anúncios por marketplace — dispatcher EXTENSÍVEL.

O Mercado Livre tem fluxo próprio rico (routers/anuncios.py: auto-match, descrições, categorias,
visitas) e NÃO passa por aqui. Este módulo cobre as OUTRAS plataformas — Shopee hoje; Amazon,
TikTok Shop, Magalu etc. no futuro: cada uma vira um ramo em `import_marketplace_listings`, sem
tocar o ML. Cria DropshipperProduct + ProductListing (dedup por conta + platform_item_id).
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select

from models.product import DropshipperProduct, ProductListing
from services import shopee_service
from services.shopee_auth import get_valid_shopee_token


def _trunc_bytes(s: str, max_bytes: int) -> str:
    """Trunca a string para caber em max_bytes UTF-8 (colunas Oracle contam bytes — 'Musculação'
    tem acento multibyte, então title[:100] estoura ORA-12899)."""
    enc = (s or "").encode("utf-8")
    return s if len(enc) <= max_bytes else enc[:max_bytes].decode("utf-8", errors="ignore")


async def import_marketplace_listings(account, user, db) -> dict:
    """Importa os anúncios da conta conforme a plataforma (dispatcher).

    Ponto de extensão para novos marketplaces: adicione um `elif account.platform == "<novo>"`.
    O ML NÃO entra aqui (tem o import rico em routers/anuncios.py).
    """
    if account.platform == "shopee":
        return await _import_shopee(account, user, db)
    # Futuro: elif account.platform == "amazon": ... / "tiktok": ... / "magalu": ...
    raise HTTPException(
        status_code=400,
        detail=f"Importação de anúncios ainda não implementada para {account.platform}.",
    )


async def _import_shopee(account, user, db) -> dict:
    """Importa os anúncios ATIVOS da loja Shopee (get_item_list → get_items_base_info)."""
    token = await get_valid_shopee_token(account, db)
    item_ids: list = []
    offset = 0
    for _ in range(50):  # teto de segurança: 50 páginas × 100 = 5000 itens
        res = await shopee_service.get_item_list(
            token, account.shop_id, offset=offset, page_size=100, item_status="NORMAL")
        item_ids += [it.get("item_id") for it in (res.get("item") or []) if it.get("item_id")]
        if not res.get("has_next_page"):
            break
        offset = res.get("next_offset") or (offset + 100)
    if not item_ids:
        return {"imported": 0, "updated": 0, "total": 0,
                "message": "Nenhum anúncio ativo encontrado na Shopee."}

    items = await shopee_service.get_items_base_info(token, account.shop_id, item_ids)
    imported, updated = 0, 0
    for it in items:
        item_id = it.get("item_id")
        sid = str(item_id)
        title = _trunc_bytes(it.get("item_name") or "", 500)
        title_sh = _trunc_bytes(it.get("item_name") or "", 100)   # coluna 100 bytes (byte-safe)
        pinfo = (it.get("price_info") or [{}])[0] if it.get("price_info") else {}
        price = float(pinfo.get("current_price") or pinfo.get("original_price") or 0)
        category = it.get("category_id")

        listing = (await db.execute(
            select(ProductListing).where(
                ProductListing.account_id == account.id,
                ProductListing.platform_item_id == sid,
            )
        )).scalar_one_or_none()
        if listing:
            listing.sale_price = price
            listing.status = "published"
            listing.last_sync_at = datetime.now(UTC)
            prod = (await db.execute(
                select(DropshipperProduct).where(DropshipperProduct.id == listing.product_id)
            )).scalar_one_or_none()
            if prod:
                prod.title_shopee = title_sh
                prod.sale_price_shopee = price
            updated += 1
        else:
            prod = DropshipperProduct(
                dropshipper_id=user.id,
                title=title,
                title_shopee=title_sh,
                sale_price_shopee=price,
                shopee_item_id=int(item_id) if item_id else None,
                shopee_category_id=int(category) if category else None,
                status="active",
            )
            db.add(prod)
            await db.flush()
            db.add(ProductListing(
                product_id=prod.id,
                account_id=account.id,
                platform_item_id=sid,
                sale_price=price,
                category_id=str(category) if category else None,
                status="published",
                published_at=datetime.now(UTC),
                last_sync_at=datetime.now(UTC),
            ))
            imported += 1

    await db.commit()
    return {"imported": imported, "updated": updated, "total": len(items),
            "message": f"{imported} anúncios importados, {updated} atualizados (Shopee)."}

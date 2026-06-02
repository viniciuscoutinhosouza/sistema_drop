"""
sync_variation_stock_job – Executa a cada 30 minutos.

Sincroniza estoque por variação para anúncios ML com `variations_json` não-vazio.

Regras:
- Para cada variação no JSON, lê stock do PG ou CMIG vinculado (via `_source`,
  `_catalog_product_id`, `_cmig_product_id`) e envia `available_quantity = max(stock, 0)`.
- Estoque = stock_quantity - reserved_quantity (igual ao sync_stock padrão).
- Variações com estoque ≤ 0 são enviadas com qty=0 (ficam "Sem estoque" na VIP,
  não vendem; voltam sozinhas quando o estoque cresce — preservam histórico).
- Se TODAS as variações ficam com qty=0, pausa o item inteiro no ML.
- Se o item estava pausado e alguma variação volta a ter estoque > 0, reativa.

Skips:
- `is_full=True`: estoque FULL gerenciado pelo ML, não tocar.
- `stock_mode='fixed'` sem keep_stock_fixed: gerenciado por vendas, não tocar.
- Todas as variações sem vínculo (_source/ids ausentes): listing não mapeado,
  pula para evitar pausar itens erroneamente (conta em listings_skipped_no_source).

Contadores no result_json:
  listings_processed         – total iterado
  listings_updated           – atualização enviada ao ML com sucesso
  listings_paused            – pausados por total_stock=0
  listings_reactivated       – reativados após estoque voltar
  listings_skipped_no_source – variações sem _source/_ids → não é possível calcular estoque
  errors                     – exceções inesperadas (token, rede, etc.)
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from database import AsyncSyncSession, task_db
from models.cmig import CMIGProduct
from models.integration import MarketplaceAccount
from models.product import CatalogProduct, ProductListing
from services import ml_service
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


async def sync_all_variation_stock() -> None:
    async with tracked_job("sync_variation_stock") as job_result:
        logger.info("sync_variation_stock_job: iniciando")
        stats = {
            "listings_processed": 0,
            "listings_updated": 0,
            "listings_paused": 0,
            "listings_reactivated": 0,
            "listings_skipped_no_source": 0,
            "errors": 0,
        }
        async with task_db() as db:
            await _sync(db, stats)
        logger.info(
            "sync_variation_stock_job: concluído (processed=%s updated=%s paused=%s "
            "reactivated=%s skipped_no_source=%s errors=%s)",
            stats["listings_processed"],
            stats["listings_updated"],
            stats["listings_paused"],
            stats["listings_reactivated"],
            stats["listings_skipped_no_source"],
            stats["errors"],
        )
        job_result.set(stats)


async def _sync(db: AsyncSyncSession, stats: dict) -> None:
    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .where(
            ProductListing.variations_json.isnot(None),
            ProductListing.platform_item_id.isnot(None),
            MarketplaceAccount.platform == "mercadolivre",
            MarketplaceAccount.is_active == True,
        )
    )
    rows = result.all()

    for listing, account in rows:
        stats["listings_processed"] += 1

        # Itens Full ML: estoque gerenciado pelo ML
        if listing.is_full:
            continue
        # Itens com stock_mode fixed sem keep_stock_fixed: não tocar
        if (listing.stock_mode or "product") == "fixed" and not listing.keep_stock_fixed:
            continue

        try:
            vars_data = json.loads(listing.variations_json or "[]")
        except Exception as exc:
            stats["errors"] += 1
            logger.warning(
                "sync_variation_stock: variations_json inválido listing_id=%s: %s",
                listing.id,
                exc,
            )
            continue

        if not isinstance(vars_data, list) or not vars_data:
            continue

        # Pula se nenhuma variação tem vínculo de produto.
        # Sem _source/_catalog_product_id/_cmig_product_id o estoque seria forçado para 0,
        # o que pausaria o item erroneamente no ML.
        has_any_linked = any(
            (v.get("_source") == "pg" and v.get("_catalog_product_id"))
            or (v.get("_source") == "cmig" and v.get("_cmig_product_id"))
            for v in vars_data
        )
        if not has_any_linked:
            stats["listings_skipped_no_source"] += 1
            logger.warning(
                "sync_variation_stock: listing_id=%s item=%s sem vínculo de produto "
                "nas variações — vincule via painel antes de sincronizar",
                listing.id,
                listing.platform_item_id,
            )
            continue

        try:
            ml_payload, total_stock = await _build_variation_stock_payload(db, vars_data)
        except Exception as exc:
            stats["errors"] += 1
            logger.warning(
                "sync_variation_stock: falha ao compor payload listing_id=%s: %s",
                listing.id,
                exc,
            )
            continue

        if not ml_payload:
            continue

        try:
            access_token = account.access_token
            if not access_token:
                continue

            was_paused = listing.status == "paused"
            should_pause = total_stock <= 0

            if should_pause:
                # Pausa item inteiro — variations não suportam status "paused" individual
                if not was_paused:
                    await ml_service.update_item_status(
                        access_token, listing.platform_item_id, "paused"
                    )
                    listing.status = "paused"
                    stats["listings_paused"] += 1
                # Ainda assim atualiza qty=0 nas variações pra refletir no JSON local
                await ml_service.update_item_variations(
                    access_token, listing.platform_item_id, ml_payload
                )
            else:
                if was_paused:
                    # Reativa antes de mexer no estoque
                    try:
                        await ml_service.update_item_status(
                            access_token, listing.platform_item_id, "active"
                        )
                        listing.status = "published"
                        stats["listings_reactivated"] += 1
                    except Exception as exc:
                        logger.warning(
                            "sync_variation_stock: falha ao reativar listing_id=%s: %s",
                            listing.id,
                            exc,
                        )
                await ml_service.update_item_variations(
                    access_token, listing.platform_item_id, ml_payload
                )

            # Atualiza variations_json local refletindo os novos available_quantity
            updated_vars = []
            for v in vars_data:
                payload_match = next(
                    (p for p in ml_payload if str(p.get("id")) == str(v.get("id"))), None
                )
                if payload_match:
                    v = dict(v)
                    v["available_quantity"] = payload_match["available_quantity"]
                updated_vars.append(v)
            listing.variations_json = json.dumps(updated_vars, ensure_ascii=False)
            listing.available_quantity = total_stock
            listing.last_sync_at = datetime.now(UTC)
            stats["listings_updated"] += 1
        except Exception as exc:
            stats["errors"] += 1
            logger.warning(
                "sync_variation_stock: falha listing_id=%s platform_item=%s: %s",
                listing.id,
                listing.platform_item_id,
                exc,
            )

    await db.commit()


async def _build_variation_stock_payload(
    db: AsyncSyncSession, vars_data: list[dict]
) -> tuple[list[dict], int]:
    """Compõe a lista completa de variações para o PUT do ML (regra de ouro: enviar tudo).

    Usa stock_quantity - reserved_quantity (estoque disponível real), igual ao sync_stock.
    Variações sem _source/_ids contribuem com 0 mas ainda são incluídas no payload
    com available_quantity=0 (ML exige o array completo).
    """
    payload: list[dict] = []
    total = 0
    for v in vars_data:
        ml_id = v.get("id")
        if not ml_id:
            # Sem id ML → não dá pra atualizar. Mantém no JSON mas pula PUT
            continue
        source = v.get("_source")
        stock = 0
        if source == "pg" and v.get("_catalog_product_id"):
            r = await db.execute(
                select(
                    CatalogProduct.stock_quantity,
                    CatalogProduct.reserved_quantity,
                ).where(CatalogProduct.id == v["_catalog_product_id"])
            )
            row = r.one_or_none()
            if row is not None:
                physical, reserved = row
                stock = max(0, int(physical or 0) - int(reserved or 0))
        elif source == "cmig" and v.get("_cmig_product_id"):
            r = await db.execute(
                select(
                    CMIGProduct.stock_quantity,
                    CMIGProduct.reserved_quantity,
                ).where(CMIGProduct.id == v["_cmig_product_id"])
            )
            row = r.one_or_none()
            if row is not None:
                physical, reserved = row
                stock = max(0, int(physical or 0) - int(reserved or 0))

        total += stock
        payload.append({"id": ml_id, "available_quantity": stock})

    return payload, total

"""
sync_stock_job – Executa a cada 30 minutos.

Modos de estoque por listing (stock_mode):
  'product'  – usa o estoque real do produto PG/CMIG vinculado (comportamento original)
  'fixed'    – usa fixed_quantity;
               se keep_stock_fixed=True o job restaura o valor a cada ciclo (estoque fixo);
               se keep_stock_fixed=False o job pula este listing (estoque gerenciado apenas por vendas)

Contadores no result_json:
  listings_processed      – total iterado
  listings_updated        – ML/Shopee confirmou atualização
  listings_skipped_full   – is_full=True (estoque gerenciado pelo fulfillment do ML)
  listings_skipped_fixed  – stock_mode='fixed' sem keep_stock_fixed (gerenciado por vendas)
  listings_unresolved     – tentativa feita mas ML não aceitou (ver unresolved_by_reason)
  unresolved_by_reason    – breakdown: "fulfillment", "multi_variation", "catalog_fail", "unknown"
  errors                  – exceções inesperadas (token expirado, rede, etc.)
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from database import AsyncSyncSession, task_db
from models.cmig import CMIGProduct
from models.integration import MarketplaceAccount
from models.product import CatalogProduct, DropshipperProduct, ProductListing
from services.ml_service import update_item_stock as ml_update_stock
from services.shopee_service import update_item_stock as shopee_update_stock
from tasks._job_wrapper import tracked_job

logger = logging.getLogger(__name__)


async def sync_all_stock() -> None:
    async with tracked_job("sync_stock") as job_result:
        logger.info("sync_stock_job: iniciando")
        stats: dict = {
            "listings_processed": 0,
            "listings_updated": 0,
            "listings_skipped_full": 0,
            "listings_skipped_fixed": 0,
            "listings_unresolved": 0,
            "unresolved_by_reason": {},
            "errors": 0,
            "error_details": [],  # até 20 entradas; cada uma explica o que falhou e o que fazer
        }
        async with task_db() as db:
            await _sync(db, stats)
        logger.info(
            "sync_stock_job: concluído (processed=%s updated=%s skipped_full=%s "
            "skipped_fixed=%s unresolved=%s errors=%s unresolved_detail=%s)",
            stats["listings_processed"],
            stats["listings_updated"],
            stats["listings_skipped_full"],
            stats["listings_skipped_fixed"],
            stats["listings_unresolved"],
            stats["errors"],
            stats["unresolved_by_reason"],
        )
        job_result.set(stats)


async def _sync(db: AsyncSyncSession, stats: dict) -> None:
    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .where(
            ProductListing.status == "published",
            ProductListing.platform_item_id.isnot(None),
            MarketplaceAccount.is_active == True,
        )
    )
    rows = result.all()

    for listing, account in rows:
        stats["listings_processed"] += 1

        # Full ML: estoque gerenciado pelo sistema de fulfillment do ML, não alteramos
        if account.platform == "mercadolivre" and listing.is_full:
            stats["listings_skipped_full"] += 1
            continue

        # NOTA: ml_catalog_id NÃO é motivo para pular.
        # Itens de catálogo ML ainda têm available_quantity editável pelo vendedor via
        # PUT /user-products/{user_product_id}/stock — ml_update_stock já trata esse fallback.

        stock_mode = listing.stock_mode or "product"

        if stock_mode == "fixed":
            if not listing.keep_stock_fixed:
                stats["listings_skipped_fixed"] += 1
                continue
            stock = int(listing.fixed_quantity or 1)
        else:
            try:
                stock = await _compute_product_stock(db, listing)
            except Exception as exc:
                stats["errors"] += 1
                logger.warning(
                    "sync_stock: erro ao calcular estoque listing_id=%s: %s", listing.id, exc
                )
                _append_error(stats, listing, str(exc), "Verifique o vínculo do produto com este anúncio no painel")
                continue

        try:
            if account.platform == "mercadolivre":
                outcome = await ml_update_stock(
                    account.access_token, listing.platform_item_id, stock
                )
                if outcome == "updated":
                    listing.available_quantity = stock
                    listing.last_sync_at = datetime.now(UTC)
                    stats["listings_updated"] += 1
                else:
                    stats["listings_unresolved"] += 1
                    reasons: dict = stats["unresolved_by_reason"]
                    reasons[outcome] = reasons.get(outcome, 0) + 1
                    logger.warning(
                        "sync_stock: não atualizou listing_id=%s item=%s motivo=%s qty=%s",
                        listing.id,
                        listing.platform_item_id,
                        outcome,
                        stock,
                    )
            elif account.platform == "shopee":
                await shopee_update_stock(
                    account.access_token,
                    account.shop_id,
                    int(listing.platform_item_id),
                    stock,
                )
                listing.available_quantity = stock
                listing.last_sync_at = datetime.now(UTC)
                stats["listings_updated"] += 1
        except Exception as exc:
            stats["errors"] += 1
            logger.warning(
                "sync_stock: falha listing_id=%s platform_item=%s: %s",
                listing.id,
                listing.platform_item_id,
                exc,
            )
            _append_error(stats, listing, str(exc), "Acesse o Mercado Livre e verifique o status do anúncio")

    await db.commit()


_MAX_ERROR_DETAILS = 20


def _append_error(stats: dict, listing: ProductListing, error: str, action: str) -> None:
    """Registra até _MAX_ERROR_DETAILS erros detalhados no result_json."""
    details: list = stats["error_details"]
    if len(details) >= _MAX_ERROR_DETAILS:
        return
    # Extrai mensagem limpa: retira traceback e prefixos técnicos longos
    short_error = error.split("\n")[0][:300]
    details.append({
        "listing_id": listing.id,
        "platform_item_id": listing.platform_item_id,
        "error": short_error,
        "acao": action,
    })


async def _compute_product_stock(db: AsyncSyncSession, listing: ProductListing) -> int:
    """Disponível a enviar ao ML: LOCAL (estoque-reservado); se 0, cai p/ o FULL
    (só pausa quando LOCAL e FULL = 0). Lógica única em full_stock_service."""
    from services.full_stock_service import available_to_push

    return await available_to_push(db, listing)

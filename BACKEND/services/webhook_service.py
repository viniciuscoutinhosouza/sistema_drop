"""
Webhook service – idempotent processing of ML and Shopee webhook events.

Critical: All order creation from webhooks goes through here.
The unique constraint on webhook_events(platform, event_id) is the safety net
against duplicate processing when marketplaces retry webhooks.
"""

import json
import logging
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.integration import MarketplaceAccount
from models.order import Order, OrderItem
from models.product import CatalogProduct, DropshipperProduct
from models.webhook import WebhookEvent
from services.ml_service import get_shipment, get_shipment_costs
from services.notification_service import create_notification
from services.order_item_resolver import resolve_order_item_link
from services.shipping_mode import MODE_DESCONHECIDO, classify_shipping

settings = get_settings()


def _parse_ship_date(val):
    """Parse an ML shipping date (string or {date}) to a date_type or None."""
    if not val:
        return None
    if isinstance(val, dict):
        val = val.get("date") or val.get("from") or val.get("to")
    try:
        return date_type.fromisoformat(str(val)[:10]) if val else None
    except (ValueError, TypeError):
        return None


def _apply_shipment_costs_to_order(order: Order, costs_data: dict) -> bool:
    """Apply accurate shipping costs from /shipments/{id}/costs.

    receiver.cost   = frete pago pelo COMPRADOR (já com descontos)
    senders[0].cost = frete pago pelo VENDEDOR (já descontado do repasse)

    This is the canonical source — preferred over shipping_option fallback.
    Returns True if any value was set.
    """
    if not costs_data:
        return False
    applied = False
    receiver = costs_data.get("receiver") or {}
    if receiver.get("cost") is not None:
        try:
            order.buyer_shipping_paid = Decimal(str(receiver["cost"]))
            applied = True
        except Exception:
            pass
    senders = costs_data.get("senders") or []
    if senders and isinstance(senders, list):
        sender_cost = senders[0].get("cost") if isinstance(senders[0], dict) else None
        if sender_cost is not None:
            try:
                order.seller_shipping_cost = Decimal(str(sender_cost))
                applied = True
            except Exception:
                pass
    return applied


def _apply_shipment_to_order(
    order: Order, shipment_data: dict, costs_data: dict | None = None
) -> bool:
    """Apply shipment fields from a fresh ML /shipments/{id} response to an Order.

    When costs_data (from /shipments/{id}/costs) is provided, prefers it for
    accurate buyer/seller shipping costs. Falls back to shipping_option list/cost diff.

    Retorna True se o `shipment_status` mudou — sinaliza pro caller chamar
    o recompute de estoque dos produtos do pedido.
    """
    if not shipment_data:
        return False

    prev_status = order.shipment_status
    status_changed = False
    new_status = shipment_data.get("status")
    if new_status:
        order.shipment_status = new_status
        status_changed = new_status != prev_status

    # ML tem 2 formatos de resposta para shipment:
    # - Antigo (default): logistic_type + mode no root
    # - Novo (x-format-new): logistic.type + logistic.mode aninhado
    nested = shipment_data.get("logistic") or {}
    new_logistic = shipment_data.get("logistic_type") or nested.get("type")
    new_mode = shipment_data.get("mode") or nested.get("mode")
    if new_logistic and new_logistic != order.shipping_method:
        order.shipping_method = new_logistic
    order.shipping_mode = classify_shipping(
        order.shipping_method, new_mode, order.shipment_id
    )

    new_tracking = shipment_data.get("tracking_number")
    if new_tracking:
        order.tracking_code = new_tracking

    receiver_address = shipment_data.get("receiver_address") or {}
    if receiver_address:
        order.shipping_address = json.dumps(receiver_address, ensure_ascii=False)

    # shipped_at: prefer explicit fields, fallback to last_updated when status is shipped
    if not order.shipped_at:
        shipped_raw = (
            shipment_data.get("date_first_printed")
            or shipment_data.get("date_shipped")
            or (new_status == "shipped" and shipment_data.get("last_updated"))
            or None
        )
        if isinstance(shipped_raw, str) and "T" in shipped_raw:
            try:
                order.shipped_at = datetime.fromisoformat(shipped_raw.replace("Z", "+00:00"))
            except Exception:
                pass

    # SLA dates from shipping_option
    ship_opt = shipment_data.get("shipping_option") or {}
    h_limit = _parse_ship_date(ship_opt.get("estimated_handling_limit"))
    if h_limit:
        order.estimated_handling_limit = h_limit
    d_final = _parse_ship_date(ship_opt.get("estimated_delivery_final")) or _parse_ship_date(
        ship_opt.get("estimated_delivery_extended")
    )
    if d_final:
        order.estimated_delivery_final = d_final
    delivery_time = shipment_data.get("estimated_delivery_time") or {}
    d_date = (
        _parse_ship_date(ship_opt.get("estimated_delivery_time"))
        or _parse_ship_date(
            delivery_time.get("date") if isinstance(delivery_time, dict) else delivery_time
        )
        or _parse_ship_date(delivery_time)
    )
    if d_date:
        order.estimated_delivery_date = d_date

    # Shipping costs — prefer /costs endpoint (accurate); fallback to list_cost - cost
    if costs_data and _apply_shipment_costs_to_order(order, costs_data):
        return status_changed  # accurate values applied; skip fallback

    buyer_paid = ship_opt.get("cost")
    list_cost = ship_opt.get("list_cost")
    if buyer_paid is not None:
        try:
            order.buyer_shipping_paid = Decimal(str(buyer_paid))
        except Exception:
            pass
    if list_cost is not None:
        try:
            seller_cost = max(Decimal("0"), Decimal(str(list_cost)) - Decimal(str(buyer_paid or 0)))
            order.seller_shipping_cost = seller_cost
        except Exception:
            pass

    return status_changed


def _apply_fees_to_order(order: Order, ml_order_data: dict) -> None:
    """Compute and store ML fee (sale_fee total) and percentage from order_items.

    IMPORTANT: order_items[].sale_fee is the fee PER UNIT, not per line.
    For multi-unit or multi-item orders, multiply by quantity and sum across items.
    """
    if not ml_order_data:
        return
    items = ml_order_data.get("order_items") or []
    total_fee = Decimal("0")
    has_fee = False
    for item in items:
        fee = item.get("sale_fee")
        if fee is None:
            continue
        qty = item.get("quantity") or 1
        try:
            total_fee += Decimal(str(fee)) * Decimal(str(qty))
            has_fee = True
        except Exception:
            pass
    if has_fee:
        order.platform_fee = total_fee
        try:
            sale = order.sale_amount
            if sale and Decimal(str(sale)) > 0:
                order.ml_fee_pct = (total_fee / Decimal(str(sale)) * Decimal("100")).quantize(
                    Decimal("0.0001")
                )
        except Exception:
            pass


async def is_already_processed(db: AsyncSession, platform: str, event_id: str) -> bool:
    result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.platform == platform,
            WebhookEvent.event_id == event_id,
            WebhookEvent.processed == True,
        )
    )
    return result.scalar_one_or_none() is not None


async def record_webhook(
    db: AsyncSession,
    platform: str,
    event_id: str,
    event_type: str,
    payload: dict,
) -> WebhookEvent | None:
    """
    Insert webhook event record.
    Returns the event on first insert.
    Returns the existing event if it exists but was never processed (allows retry
    after a previous processing failure).
    Returns None only if the event was already successfully processed.
    """
    event = WebhookEvent(
        platform=platform,
        event_id=event_id,
        event_type=event_type,
        payload=json.dumps(payload, ensure_ascii=False),
    )
    db.add(event)
    try:
        await db.flush()
        return event
    except IntegrityError:
        await db.rollback()
        # Return existing unprocessed event so the caller can retry processing it
        result = await db.execute(
            select(WebhookEvent).where(
                WebhookEvent.platform == platform,
                WebhookEvent.event_id == event_id,
                WebhookEvent.processed == False,
            )
        )
        return result.scalar_one_or_none()


async def _backfill_order_links(db: AsyncSession, order: Order, integration: MarketplaceAccount) -> bool:
    """Tenta resolver vínculos de OrderItems sem produto e atualiza Order.product_cost.

    Idempotente: itens que já têm dropshipper_product_id OU catalog_product_id são
    pulados. Retorna True se algo mudou.
    """
    items = (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    ).scalars().all()
    if not items:
        return False

    changed = False
    for it in items:
        if it.dropshipper_product_id or it.catalog_product_id:
            continue
        resolved = await resolve_order_item_link(
            db,
            account_id=order.account_id,
            ml_item_id=it.ml_item_id,
            cmig_id=order.cmig_id,
            sku=it.sku,
            dropshipper_id=integration.owner_id if integration else None,
        )
        if not resolved.has_link:
            continue
        if resolved.dropshipper_product:
            it.dropshipper_product_id = resolved.dropshipper_product.id
        if resolved.catalog_product:
            it.catalog_product_id = resolved.catalog_product.id
        if it.unit_cost is None and resolved.unit_cost is not None:
            it.unit_cost = resolved.unit_cost
        changed = True

    if changed:
        total = sum((i.unit_cost or Decimal("0")) * i.quantity for i in items)
        if total > 0:
            order.product_cost = total

    return changed


async def process_ml_order(
    db: AsyncSession,
    ml_order_data: dict,
    integration: MarketplaceAccount,
):
    """
    Process a Mercado Livre order webhook.
    Creates Order and OrderItem records. Notifies the AC owner.
    """
    ml_order_id = str(ml_order_data.get("id", ""))

    # Check if order already exists
    existing = await db.execute(
        select(Order).where(
            Order.platform == "mercadolivre",
            Order.platform_order_id == ml_order_id,
            Order.dropshipper_id == integration.owner_id,
        )
    )
    existing_order = existing.scalar_one_or_none()
    if existing_order:
        # Update cancellation status if ML cancelled the order after import
        if ml_order_data.get("status") == "cancelled" and existing_order.status != "cancelled":
            existing_order.status = "cancelled"
            existing_order.platform_status = "cancelled"
            # Libera ou marca aguardando retorno dependendo se já foi despachado
            try:
                from services.stock_reservation_service import (
                    _order_was_dispatched,
                    mark_awaiting_return,
                    release_reservation,
                )
                if _order_was_dispatched(existing_order):
                    await mark_awaiting_return(db, existing_order)
                else:
                    await release_reservation(db, existing_order)
            except Exception as exc:
                logger.warning("stock cancel hook order=%s: %s", existing_order.id, exc)
        # Backfill created_at with ML date_created if currently wrong (same day = sync artifact)
        raw_created = ml_order_data.get("date_created")
        if raw_created:
            try:
                ml_date = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
                local_created = existing_order.created_at
                if local_created is not None and local_created.tzinfo is None:
                    local_created = local_created.replace(tzinfo=UTC)
                if not local_created or abs((local_created - ml_date).total_seconds()) > 300:
                    existing_order.created_at = ml_date
            except Exception:
                pass

        # Refresh shipment status, tracking code and SLA dates from current ML state
        shipping = ml_order_data.get("shipping", {}) or {}
        shipment_id = shipping.get("id")
        if shipment_id and integration.access_token:
            try:
                shipment_data = await get_shipment(
                    integration.access_token,
                    str(shipment_id),
                    caller_id=integration.platform_user_id,
                )
                costs_data = {}
                try:
                    costs_data = await get_shipment_costs(
                        integration.access_token, str(shipment_id)
                    )
                except Exception:
                    pass
                if shipment_data:
                    status_changed = _apply_shipment_to_order(
                        existing_order, shipment_data, costs_data
                    )
                    if not existing_order.shipment_id:
                        existing_order.shipment_id = str(shipment_id)
                    # Mudança de shipment_status → recalcular estoque dos produtos
                    if status_changed:
                        try:
                            from services.fiscal.stock_calculator import (
                                recompute_after_order_change,
                            )
                            await recompute_after_order_change(existing_order, db)
                        except Exception:
                            pass
                        # Se o pedido foi despachado, debita estoque físico
                        if (existing_order.shipment_status or "") in {"shipped", "delivered"}:
                            try:
                                from services.stock_reservation_service import confirm_dispatch
                                await confirm_dispatch(db, existing_order)
                            except Exception as exc:
                                logger.warning("confirm_dispatch order=%s: %s", existing_order.id, exc)
            except Exception:
                pass

        # Refresh ML fees (sale_fee aggregate)
        if not existing_order.sale_amount:
            existing_order.sale_amount = Decimal(str(ml_order_data.get("total_amount") or 0))
        _apply_fees_to_order(existing_order, ml_order_data)

        # Resolve vínculos de produtos faltantes (idempotente — só toca em items sem vínculo)
        try:
            await _backfill_order_links(db, existing_order, integration)
        except Exception:
            pass
        return

    buyer = ml_order_data.get("buyer", {})
    shipping = ml_order_data.get("shipping", {})
    fiscal_data = ml_order_data.get("fiscal_data", {}) or {}
    invoice = fiscal_data.get("invoice", {}) or {}

    def _parse_date(val):
        if not val:
            return None
        if isinstance(val, dict):
            val = val.get("date") or val.get("from") or val.get("to")
        try:
            return date_type.fromisoformat(str(val)[:10]) if val else None
        except (ValueError, TypeError):
            return None

    # Fetch full shipment details to get logistic_type, receiver_address, status, tracking
    shipping_method = ""
    shipment_status = ""
    tracking_code = ""
    shipping_address_json = json.dumps(shipping, ensure_ascii=False)
    estimated_delivery_date = None
    estimated_handling_limit = None
    estimated_delivery_final = None
    shipped_at = None
    buyer_shipping_paid = None
    seller_shipping_cost = None
    shipment_id = shipping.get("id")
    shipping_mode_value = None
    if shipment_id and integration.access_token:
        try:
            shipment_data = await get_shipment(
                integration.access_token,
                str(shipment_id),
                caller_id=integration.platform_user_id,
            )
            # ML: logistic_type+mode no root OU logistic.{type,mode} aninhado
            nested = shipment_data.get("logistic") or {}
            shipping_method = shipment_data.get("logistic_type") or nested.get("type") or ""
            ml_mode = shipment_data.get("mode") or nested.get("mode")
            shipping_mode_value = classify_shipping(
                shipping_method, ml_mode, str(shipment_id) if shipment_id else None
            )
            shipment_status = shipment_data.get("status", "")
            tracking_code = shipment_data.get("tracking_number", "") or ""
            receiver_address = shipment_data.get("receiver_address") or {}
            if receiver_address:
                shipping_address_json = json.dumps(receiver_address, ensure_ascii=False)
            # shipped_at from shipment date_first_printed or date_shipped
            shipped_at_raw = (
                shipment_data.get("date_first_printed")
                or shipment_data.get("date_shipped")
                or (shipment_data.get("status") == "shipped" and shipment_data.get("last_updated"))
                or None
            )
            if isinstance(shipped_at_raw, str) and "T" in shipped_at_raw:
                try:
                    shipped_at = datetime.fromisoformat(shipped_at_raw.replace("Z", "+00:00"))
                except Exception:
                    pass
            # SLA dates from shipping_option
            ship_opt = shipment_data.get("shipping_option") or {}
            estimated_handling_limit = _parse_date(ship_opt.get("estimated_handling_limit"))
            estimated_delivery_final = _parse_date(
                ship_opt.get("estimated_delivery_final")
            ) or _parse_date(ship_opt.get("estimated_delivery_extended"))
            # Estimated delivery from shipment
            delivery_time = shipment_data.get("estimated_delivery_time") or {}
            estimated_delivery_date = (
                _parse_date(ship_opt.get("estimated_delivery_time"))
                or _parse_date(delivery_time.get("date"))
                or _parse_date(delivery_time)
            )
            # Shipping costs: prefer /shipments/{id}/costs (accurate)
            try:
                costs_data = await get_shipment_costs(integration.access_token, str(shipment_id))
            except Exception:
                costs_data = {}
            if costs_data:
                receiver = costs_data.get("receiver") or {}
                senders = costs_data.get("senders") or []
                if receiver.get("cost") is not None:
                    try:
                        buyer_shipping_paid = Decimal(str(receiver["cost"]))
                    except Exception:
                        pass
                if senders and isinstance(senders[0], dict) and senders[0].get("cost") is not None:
                    try:
                        seller_shipping_cost = Decimal(str(senders[0]["cost"]))
                    except Exception:
                        pass
            # Fallback to list_cost - cost when /costs is unavailable
            if buyer_shipping_paid is None:
                cost = ship_opt.get("cost")
                if cost is not None:
                    try:
                        buyer_shipping_paid = Decimal(str(cost))
                    except Exception:
                        pass
            if seller_shipping_cost is None:
                cost = ship_opt.get("cost")
                list_cost = ship_opt.get("list_cost")
                if list_cost is not None:
                    try:
                        seller_shipping_cost = max(
                            Decimal("0"), Decimal(str(list_cost)) - Decimal(str(cost or 0))
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # Fallback: extract estimated delivery from order-level shipping data
    if not estimated_delivery_date:
        delivery_time = shipping.get("estimated_delivery_time", {}) or {}
        estimated_delivery_date = _parse_date(
            delivery_time.get("date")
            or (shipping.get("estimated_delivery_final") or {}).get("date")
        )

    # created_at from ML order date_created (fallback chain: date_created → date_closed → last_updated → now)
    ml_created_at = None
    for _date_field in ("date_created", "date_closed", "last_updated"):
        _raw = ml_order_data.get(_date_field)
        if _raw:
            try:
                ml_created_at = datetime.fromisoformat(str(_raw).replace("Z", "+00:00"))
                break
            except Exception:
                pass
    if ml_created_at is None:
        ml_created_at = datetime.now(UTC)

    # paid_at from payments array; fallback to date_closed
    paid_at = None
    for payment in ml_order_data.get("payments") or []:
        date_approved = payment.get("date_approved")
        if date_approved:
            try:
                paid_at = datetime.fromisoformat(str(date_approved).replace("Z", "+00:00"))
                break
            except Exception:
                pass
    if not paid_at and ml_order_data.get("status") in ("paid", "cancelled"):
        raw_closed = ml_order_data.get("date_closed")
        if raw_closed:
            try:
                paid_at = datetime.fromisoformat(str(raw_closed).replace("Z", "+00:00"))
            except Exception:
                pass

    # ML order tags (paid, fraud_risk_detected, cart, test_order, not_delivered, etc.)
    order_tags = ",".join(ml_order_data.get("tags") or [])

    # Extract NF-e data from fiscal_data if present
    # Prefer access_key (44-digit chave de acesso) over invoice number for URL construction
    nfe_key = invoice.get("access_key") or invoice.get("number")
    nfe_url = invoice.get("cdg_post") or invoice.get("url")
    nfe_status = "authorized" if invoice else None

    order = Order(
        dropshipper_id=integration.owner_id,
        account_id=integration.id,
        cmig_id=integration.cmig_id,
        platform="mercadolivre",
        platform_order_id=ml_order_id,
        platform_order_ref=str(ml_order_data.get("order_id", ml_order_id)),
        platform_status=ml_order_data.get("status", ""),
        status="cancelled" if ml_order_data.get("status") == "cancelled" else "downloaded",
        payment_status="pending",
        buyer_name=f"{buyer.get('first_name', '')} {buyer.get('last_name', '')}".strip(),
        buyer_email=buyer.get("email"),
        buyer_document=buyer.get("identification", {}).get("number"),
        shipping_address=shipping_address_json,
        shipping_method=shipping_method,
        shipping_mode=shipping_mode_value or classify_shipping(
            shipping_method, None, str(shipment_id) if shipment_id else None
        ),
        shipment_status=shipment_status or None,
        shipment_id=str(shipment_id) if shipment_id else None,
        tracking_code=tracking_code or None,
        sale_amount=Decimal(str(ml_order_data.get("total_amount", 0))),
        buyer_shipping_paid=buyer_shipping_paid,
        seller_shipping_cost=seller_shipping_cost,
        estimated_delivery_date=estimated_delivery_date,
        estimated_handling_limit=estimated_handling_limit,
        estimated_delivery_final=estimated_delivery_final,
        order_tags=order_tags or None,
        nfe_url=nfe_url,
        nfe_key=nfe_key,
        nfe_status=nfe_status,
        paid_at=paid_at,
        shipped_at=shipped_at,
        created_at=ml_created_at,
    )
    db.add(order)
    try:
        await db.flush()
    except IntegrityError:
        # Corrida: outro processo (webhook/sync) inseriu este pedido ao mesmo tempo. O
        # índice único ux_orders_plat_poid_drop (migration 123) barra a duplicata — re-busca
        # o pedido já criado e ignora graciosamente (o "vencedor" cuidou de itens/reserva).
        await db.rollback()
        dup = (
            await db.execute(
                select(Order).where(
                    Order.platform == "mercadolivre",
                    Order.platform_order_id == ml_order_id,
                    Order.dropshipper_id == integration.owner_id,
                )
            )
        ).scalar_one_or_none()
        if dup:
            logger.info("[ml] pedido %s criado concorrentemente — duplicata evitada", ml_order_id)
            return
        raise

    # Compute and store ML platform_fee + ml_fee_pct from order_items[].sale_fee
    _apply_fees_to_order(order, ml_order_data)

    # Create order items
    for item_data in ml_order_data.get("order_items", []):
        item_info = item_data.get("item", {})
        ml_item_id = str(item_info.get("id", ""))

        # Normalize thumbnail to HTTPS
        raw_thumb = item_info.get("thumbnail", "") or ""
        thumbnail_url = raw_thumb.replace("http://", "https://") if raw_thumb else None

        # Resolve vínculo via ProductListing (fonte canônica)
        resolved = await resolve_order_item_link(
            db,
            account_id=integration.id,
            ml_item_id=ml_item_id,
            cmig_id=order.cmig_id,
            sku=item_info.get("seller_sku") or None,
            dropshipper_id=integration.owner_id,
        )

        db.add(
            OrderItem(
                order_id=order.id,
                dropshipper_product_id=(
                    resolved.dropshipper_product.id if resolved.dropshipper_product else None
                ),
                catalog_product_id=(
                    resolved.catalog_product.id if resolved.catalog_product else None
                ),
                ml_item_id=ml_item_id,
                sku=item_info.get("seller_sku", ""),
                title=item_info.get("title", ""),
                quantity=item_data.get("quantity", 1),
                unit_price=Decimal(str(item_data.get("unit_price", 0))),
                unit_cost=resolved.unit_cost,
                thumbnail_url=thumbnail_url,
            )
        )

    await db.flush()

    # Agrega product_cost no pedido (sum(unit_cost * qty) dos OrderItems criados)
    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = items_result.scalars().all()
    total_cost = sum(
        (i.unit_cost or Decimal("0")) * i.quantity for i in items
    )
    if total_cost > 0:
        order.product_cost = total_cost

    await db.commit()

    # Reserva o estoque dos produtos vinculados ao pedido
    if order.status != "cancelled":
        try:
            from services.stock_reservation_service import reserve_stock
            await reserve_stock(db, order)
        except Exception as exc:
            logger.warning("reserve_stock order=%s: %s", order.id, exc)

    # Trigger recálculo de estoque (cobre kits via explosão de componentes)
    try:
        from services.fiscal.stock_calculator import (
            trigger_stock_recompute_on_order_created,
        )
        await trigger_stock_recompute_on_order_created(order, db)
    except Exception:
        pass

    # Notify AC owner
    await create_notification(
        db=db,
        dropshipper_id=integration.owner_id,
        type="new_order",
        title=f"Novo pedido #{order.id} – Mercado Livre",
        body=f"Pedido de {order.buyer_name} no valor de R$ {float(order.sale_amount):.2f}",
        reference_type="order",
        reference_id=order.id,
    )


async def process_shopee_order(
    db: AsyncSession,
    shopee_order_data: dict,
    integration: MarketplaceAccount,
):
    """Process a Shopee order webhook event."""
    shopee_order_id = str(shopee_order_data.get("ordersn", ""))

    existing = await db.execute(
        select(Order).where(
            Order.platform == "shopee",
            Order.platform_order_id == shopee_order_id,
            Order.dropshipper_id == integration.owner_id,
        )
    )
    if existing.scalar_one_or_none():
        return

    recipient_address = shopee_order_data.get("recipient_address", {})

    order = Order(
        dropshipper_id=integration.owner_id,
        account_id=integration.id,
        cmig_id=integration.cmig_id,
        platform="shopee",
        platform_order_id=shopee_order_id,
        platform_status=shopee_order_data.get("order_status", ""),
        status="downloaded",
        payment_status="pending",
        buyer_name=recipient_address.get("name", ""),
        shipping_address=json.dumps(recipient_address, ensure_ascii=False),
        sale_amount=Decimal(str(shopee_order_data.get("total_amount", 0))),
        shipping_mode=MODE_DESCONHECIDO,  # Shopee usa rede propria — fora do escopo do bucket ML
    )
    db.add(order)
    try:
        await db.flush()
    except IntegrityError:
        # Corrida: duplicata barrada pelo índice único (migration 123). Re-busca e ignora.
        await db.rollback()
        dup = (
            await db.execute(
                select(Order).where(
                    Order.platform == "shopee",
                    Order.platform_order_id == shopee_order_id,
                    Order.dropshipper_id == integration.owner_id,
                )
            )
        ).scalar_one_or_none()
        if dup:
            logger.info("[shopee] pedido %s criado concorrentemente — duplicata evitada", shopee_order_id)
            return
        raise

    for item_data in shopee_order_data.get("item_list", []):
        shopee_item_id = item_data.get("item_id")

        # Caminho legado (DropshipperProduct.shopee_item_id) — preservar pro fallback de DP
        dp_result = await db.execute(
            select(DropshipperProduct).where(
                DropshipperProduct.shopee_item_id == shopee_item_id,
                DropshipperProduct.dropshipper_id == integration.owner_id,
            )
        )
        dp_legacy = dp_result.scalar_one_or_none()

        resolved = await resolve_order_item_link(
            db,
            account_id=integration.id,
            shopee_item_id=shopee_item_id,
            cmig_id=order.cmig_id,
            sku=item_data.get("item_sku") or None,
            dropshipper_id=integration.owner_id,
        )

        # Se o helper não achou via ProductListing mas o lookup legado achou, usa esse
        dp_resolved = resolved.dropshipper_product or dp_legacy
        catalog_resolved = resolved.catalog_product
        if not catalog_resolved and dp_legacy and dp_legacy.catalog_product_id:
            catalog_resolved = await (db.execute(
                select(CatalogProduct).where(CatalogProduct.id == dp_legacy.catalog_product_id)
            ))
            catalog_resolved = catalog_resolved.scalar_one_or_none()
        unit_cost = resolved.unit_cost
        if unit_cost is None and catalog_resolved and catalog_resolved.cost_price is not None:
            unit_cost = Decimal(str(catalog_resolved.cost_price))

        db.add(
            OrderItem(
                order_id=order.id,
                dropshipper_product_id=dp_resolved.id if dp_resolved else None,
                catalog_product_id=catalog_resolved.id if catalog_resolved else None,
                sku=item_data.get("item_sku", ""),
                title=item_data.get("item_name", ""),
                quantity=item_data.get("model_quantity_purchased", 1),
                unit_price=Decimal(str(item_data.get("model_discounted_price", 0))),
                unit_cost=unit_cost,
            )
        )

    await db.flush()

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = items_result.scalars().all()
    total_cost = sum(
        (i.unit_cost or Decimal("0")) * i.quantity for i in items
    )
    if total_cost > 0:
        order.product_cost = total_cost

    await db.commit()

    # Trigger recálculo de estoque (cobre kits via explosão de componentes)
    try:
        from services.fiscal.stock_calculator import (
            trigger_stock_recompute_on_order_created,
        )
        await trigger_stock_recompute_on_order_created(order, db)
    except Exception:
        pass

    await create_notification(
        db=db,
        dropshipper_id=integration.owner_id,
        type="new_order",
        title=f"Novo pedido #{order.id} – Shopee",
        body=f"Pedido de {order.buyer_name}",
        reference_type="order",
        reference_id=order.id,
    )

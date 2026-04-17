from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from database import get_db
from dependencies import get_current_user
from models.user import User
from models.notification import Notification
from schemas.dashboard import KPIResponse, TopProductSchema
from datetime import datetime, timezone, timedelta
from decimal import Decimal

router = APIRouter()


@router.get("/kpis", response_model=KPIResponse)
async def get_kpis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_of_prev_month = (start_of_month - timedelta(days=1)).replace(day=1)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_30d = now - timedelta(days=30)

    uid = current_user.id

    # Lazy import to avoid circular imports
    from models.order import Order, OrderItem
    from models.product import DropshipperProduct

    # Monthly sales (current month) – count and value
    res = await db.execute(
        text("""
            SELECT COUNT(*), NVL(SUM(sale_amount), 0)
            FROM orders
            WHERE dropshipper_id = :uid
              AND status NOT IN ('cancelled','returned')
              AND created_at >= :start
        """),
        {"uid": uid, "start": start_of_month},
    )
    row = res.fetchone()
    monthly_count = row[0] or 0
    monthly_value = Decimal(str(row[1] or 0))

    # Previous month sales
    res = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM orders
            WHERE dropshipper_id = :uid
              AND status NOT IN ('cancelled','returned')
              AND created_at >= :start AND created_at < :end
        """),
        {"uid": uid, "start": start_of_prev_month, "end": start_of_month},
    )
    prev_count = res.scalar() or 0
    change_pct = 0.0
    if prev_count > 0:
        change_pct = ((monthly_count - prev_count) / prev_count) * 100

    # Unpaid orders
    res = await db.execute(
        text("SELECT COUNT(*) FROM orders WHERE dropshipper_id = :uid AND payment_status = 'pending' AND status NOT IN ('cancelled','returned')"),
        {"uid": uid},
    )
    unpaid_count = res.scalar() or 0

    # Unlinked orders (order items with no dropshipper_product link)
    res = await db.execute(
        text("""
            SELECT COUNT(DISTINCT o.id)
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            WHERE o.dropshipper_id = :uid
              AND oi.dropshipper_product_id IS NULL
              AND o.status NOT IN ('cancelled','returned')
        """),
        {"uid": uid},
    )
    unlinked_count = res.scalar() or 0

    # Cancelled
    res = await db.execute(
        text("SELECT COUNT(*) FROM orders WHERE dropshipper_id = :uid AND status = 'cancelled'"),
        {"uid": uid},
    )
    cancelled_count = res.scalar() or 0

    # Total active products
    res = await db.execute(
        text("SELECT COUNT(*) FROM dropshipper_products WHERE dropshipper_id = :uid AND status != 'closed'"),
        {"uid": uid},
    )
    total_products = res.scalar() or 0

    # Sales last 30 days
    res = await db.execute(
        text("""
            SELECT NVL(SUM(sale_amount), 0)
            FROM orders
            WHERE dropshipper_id = :uid
              AND status NOT IN ('cancelled','returned')
              AND created_at >= :start
        """),
        {"uid": uid, "start": start_of_30d},
    )
    sales_30d = Decimal(str(res.scalar() or 0))

    # Sales today
    res = await db.execute(
        text("""
            SELECT NVL(SUM(sale_amount), 0)
            FROM orders
            WHERE dropshipper_id = :uid
              AND status NOT IN ('cancelled','returned')
              AND created_at >= :start
        """),
        {"uid": uid, "start": start_of_today},
    )
    sales_today = Decimal(str(res.scalar() or 0))

    return KPIResponse(
        monthly_sales_count=monthly_count,
        monthly_sales_value=monthly_value,
        monthly_sales_change_pct=round(change_pct, 1),
        unpaid_orders_count=unpaid_count,
        unlinked_orders_count=unlinked_count,
        cancelled_orders_count=cancelled_count,
        total_products=total_products,
        sales_last_30_days=sales_30d,
        sales_today=sales_today,
    )


@router.get("/top-products")
async def get_top_products(db: AsyncSession = Depends(get_db)):
    """Top 8 most recently added catalog products."""
    from models.product import CatalogProduct, CatalogProductImage

    result = await db.execute(
        select(CatalogProduct)
        .where(CatalogProduct.is_active == True)
        .order_by(CatalogProduct.created_at.desc())
        .limit(8)
    )
    products = result.scalars().all()

    out = []
    for p in products:
        img_result = await db.execute(
            select(CatalogProductImage)
            .where(CatalogProductImage.product_id == p.id)
            .order_by(CatalogProductImage.is_primary.desc(), CatalogProductImage.sort_order)
            .limit(1)
        )
        img = img_result.scalar_one_or_none()
        out.append(TopProductSchema(
            id=p.id,
            sku=p.sku,
            title=p.title,
            cost_price=p.cost_price,
            stock_quantity=p.stock_quantity,
            image_url=img.url if img else "",
        ))
    return out

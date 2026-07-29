from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.dashboard import KPIResponse, TopProductSchema
from services.datetime_br import BR_TZ as BRT  # fonte única do fuso do Brasil

router = APIRouter()


@router.get("/kpis", response_model=KPIResponse)
async def get_kpis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ADR-0013: "hoje"/"mês" são limites do DIA/MÊS no fuso do Brasil (BRT), convertidos
    # para UTC só na hora de comparar com created_at (TIMESTAMP WITH TIME ZONE). Usar
    # datetime.now(UTC) direto colocava a virada do dia/mês às 00:00 UTC (21:00 BRT do dia
    # anterior), contando pedidos do dia/mês errado perto da meia-noite local.
    now_brt = datetime.now(BRT)
    start_today_brt = now_brt.replace(hour=0, minute=0, second=0, microsecond=0)
    start_month_brt = start_today_brt.replace(day=1)
    start_prev_month_brt = (start_month_brt - timedelta(days=1)).replace(day=1)

    start_of_month = start_month_brt.astimezone(UTC)
    start_of_prev_month = start_prev_month_brt.astimezone(UTC)
    start_of_today = start_today_brt.astimezone(UTC)
    start_of_30d = datetime.now(UTC) - timedelta(days=30)  # janela móvel de 30 dias (instante)

    uid = current_user.id

    # Lazy import to avoid circular imports

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
        text(
            "SELECT COUNT(*) FROM orders WHERE dropshipper_id = :uid AND payment_status = 'pending' AND status NOT IN ('cancelled','returned')"
        ),
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
        text(
            "SELECT COUNT(*) FROM dropshipper_products WHERE dropshipper_id = :uid AND status != 'closed'"
        ),
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
    """Last 12 most recently added catalog products."""
    from models.product import CatalogProduct, CatalogProductImage

    result = await db.execute(
        select(CatalogProduct)
        .where(CatalogProduct.is_active == True)
        .order_by(CatalogProduct.created_at.desc())
        .limit(12)
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
        out.append(
            TopProductSchema(
                id=p.id,
                sku=p.sku,
                title=p.title,
                cost_price=p.cost_price,
                stock_quantity=p.stock_quantity,
                image_url=img.url if img else "",
            )
        )
    return out


# ---------------------------------------------------------------------------
# Dashboard de Marketplaces — matriz Hoje/Ontem/7d/7d antes/Mês/Mês anterior
# ---------------------------------------------------------------------------

# Ordem e rótulos das janelas (colunas da matriz).
_WINDOWS = ["hoje", "ontem", "7d", "7d_antes", "mes", "mes_anterior"]
_WINDOW_LABELS = {
    "hoje": "Hoje",
    "ontem": "Ontem",
    "7d": "7 dias",
    "7d_antes": "7 dias antes",
    "mes": "Este Mês",
    "mes_anterior": "Mês Anterior",
}


def _date_windows(now_brt: datetime):
    """Devolve, para cada janela, os limites em datetime (BRT) para orders
    e em date (BRT) para o snapshot diário."""
    start_today = now_brt.replace(hour=0, minute=0, second=0, microsecond=0)
    today = start_today.date()
    start_month = start_today.replace(day=1)
    start_prev_month = (start_month - timedelta(days=1)).replace(day=1)

    dt = {
        "hoje": (start_today, now_brt),
        "ontem": (start_today - timedelta(days=1), start_today),
        "7d": (start_today - timedelta(days=6), now_brt),
        "7d_antes": (start_today - timedelta(days=13), start_today - timedelta(days=6)),
        "mes": (start_month, now_brt),
        "mes_anterior": (start_prev_month, start_month),
    }
    # Limites do snapshot por DATE (BRT), inclusivos.
    dd = {
        "hoje": (today, today),
        "ontem": (today - timedelta(days=1), today - timedelta(days=1)),
        "7d": (today - timedelta(days=6), today),
        "7d_antes": (today - timedelta(days=13), today - timedelta(days=7)),
        "mes": (start_month.date(), today),
        "mes_anterior": (start_prev_month.date(), start_month.date() - timedelta(days=1)),
    }
    return dt, dd


@router.get("/marketplace")
async def get_marketplace_dashboard(
    account_id: int | None = Query(None),
    platform: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Matriz de métricas de marketplace por janela de tempo (fuso BRT).

    Pedidos/Faturamento/Full/Flex saem ao vivo da tabela orders.
    Visitas/Perguntas/ADS saem do snapshot marketplace_metrics_daily (ML-only).
    Conversão = pedidos/visitas. Admin/GO veem tudo; AC/UGO só os próprios pedidos.
    """
    is_global = current_user.role in ("admin", "go")
    now_brt = datetime.now(BRT)
    dt_windows, dd_windows = _date_windows(now_brt)

    # ----- filtros comuns (orders) -----
    base_filters = []
    params: dict = {}
    if not is_global:
        base_filters.append("dropshipper_id = :uid")
        params["uid"] = current_user.id
    if account_id is not None:
        base_filters.append("account_id = :account_id")
        params["account_id"] = account_id
    if platform:
        base_filters.append("platform = :platform")
        params["platform"] = platform
    extra_where = (" AND " + " AND ".join(base_filters)) if base_filters else ""

    orders_sql = text(f"""
        SELECT
          COUNT(CASE WHEN status NOT IN ('cancelled','returned') THEN 1 END) AS qtd,
          COUNT(CASE WHEN status = 'cancelled' THEN 1 END) AS cancelados,
          COUNT(CASE WHEN status NOT IN ('cancelled','returned')
                     AND shipping_mode = 'full' THEN 1 END) AS full_cnt,
          COUNT(CASE WHEN status NOT IN ('cancelled','returned')
                     AND shipping_mode = 'flex' THEN 1 END) AS flex_cnt,
          COUNT(CASE WHEN status NOT IN ('cancelled','returned')
                     AND (shipping_mode NOT IN ('full','flex') OR shipping_mode IS NULL)
                     THEN 1 END) AS outros_cnt,
          NVL(SUM(CASE WHEN status NOT IN ('cancelled','returned')
                       THEN sale_amount END), 0) AS fat,
          NVL(SUM(CASE WHEN status NOT IN ('cancelled','returned')
                       AND shipping_mode = 'full' THEN sale_amount END), 0) AS fat_full,
          NVL(SUM(CASE WHEN status NOT IN ('cancelled','returned')
                       AND shipping_mode = 'flex' THEN sale_amount END), 0) AS fat_flex,
          NVL(SUM(CASE WHEN status NOT IN ('cancelled','returned')
                       THEN NVL(product_cost,0) + NVL(platform_fee,0)
                            + NVL(seller_shipping_cost,0) END), 0) AS custos
        FROM orders
        WHERE created_at >= :start AND created_at < :end {extra_where}
    """)

    # Snapshot: contas dentro do escopo do usuário. Se filtro de conta, usa ela;
    # senão, todas as contas que aparecem nos pedidos do escopo (alinha visitas/ads
    # às mesmas contas que geraram os pedidos). Admin/GO = todas as contas ML.
    snap_filters = ["metric_date >= :d_start", "metric_date <= :d_end"]
    snap_params: dict = {}
    if account_id is not None:
        snap_filters.append("account_id = :s_account_id")
        snap_params["s_account_id"] = account_id
    elif not is_global:
        snap_filters.append(
            "account_id IN (SELECT DISTINCT account_id FROM orders "
            "WHERE dropshipper_id = :s_uid AND account_id IS NOT NULL)"
        )
        snap_params["s_uid"] = current_user.id
    snap_sql = text(f"""
        SELECT NVL(SUM(visits),0) AS visits,
               NVL(SUM(questions_total),0) AS questions,
               NVL(SUM(ads_cost),0) AS ads
        FROM marketplace_metrics_daily
        WHERE {" AND ".join(snap_filters)}
    """)

    def _f(v) -> float:
        return float(v or 0)

    rows: dict[str, dict] = {
        key: {}
        for key in (
            "qtd_pedidos", "cancelados", "full", "flex", "outros",
            "faturamento", "fat_full", "fat_flex",
            "visitas", "conversao", "perguntas", "ads_cost",
        )
    }
    extras: dict[str, dict] = {}

    for w in _WINDOWS:
        start_dt, end_dt = dt_windows[w]
        d_start, d_end = dd_windows[w]
        o = await db.execute(
            orders_sql,
            {**params, "start": start_dt.astimezone(UTC), "end": end_dt.astimezone(UTC)},
        )
        orow = o.fetchone()
        s = await db.execute(
            snap_sql, {**snap_params, "d_start": d_start, "d_end": d_end}
        )
        srow = s.fetchone()

        qtd = int(orow[0] or 0)
        fat = _f(orow[5])
        custos = _f(orow[8])
        visits = int(srow[0] or 0)

        rows["qtd_pedidos"][w] = qtd
        rows["cancelados"][w] = int(orow[1] or 0)
        rows["full"][w] = int(orow[2] or 0)
        rows["flex"][w] = int(orow[3] or 0)
        rows["outros"][w] = int(orow[4] or 0)
        rows["faturamento"][w] = round(fat, 2)
        rows["fat_full"][w] = round(_f(orow[6]), 2)
        rows["fat_flex"][w] = round(_f(orow[7]), 2)
        rows["visitas"][w] = visits
        rows["conversao"][w] = round((qtd / visits * 100), 2) if visits > 0 else 0.0
        rows["perguntas"][w] = int(srow[1] or 0)
        rows["ads_cost"][w] = round(_f(srow[2]), 2)

        # Extras (cards de apoio): ticket médio, ACOS, margem, taxa de cancelamento.
        ads = round(_f(srow[2]), 2)
        cancel = int(orow[1] or 0)
        extras[w] = {
            "ticket_medio": round(fat / qtd, 2) if qtd > 0 else 0.0,
            "acos": round(ads / fat * 100, 2) if fat > 0 else 0.0,
            "margem": round(fat - custos, 2),
            "margem_pct": round((fat - custos) / fat * 100, 2) if fat > 0 else 0.0,
            "taxa_cancelamento": round(cancel / (qtd + cancel) * 100, 2)
            if (qtd + cancel) > 0 else 0.0,
        }

    # Rótulos amigáveis e flag ML-only por linha (para o frontend).
    row_meta = {
        "qtd_pedidos": {"label": "Qtd Pedidos", "type": "int"},
        "cancelados": {"label": "Pedidos Cancelados", "type": "int"},
        "full": {"label": "Pedidos do Full", "type": "int"},
        "flex": {"label": "Pedidos do Flex", "type": "int"},
        "outros": {"label": "Outros Pedidos", "type": "int"},
        "faturamento": {"label": "Faturamento", "type": "money"},
        "fat_full": {"label": "Faturamento FULL", "type": "money"},
        "fat_flex": {"label": "Faturamento FLEX", "type": "money"},
        "visitas": {"label": "Visitas", "type": "int", "ml_only": True},
        "conversao": {"label": "Conversão", "type": "pct", "ml_only": True},
        "perguntas": {"label": "Perguntas", "type": "int", "ml_only": True},
        "ads_cost": {"label": "Gasto no ADS", "type": "money", "ml_only": True},
    }

    # Intervalo real [de, até) de cada janela — em ISO UTC (contrato ADR-0013; o front
    # converte p/ horário de Brasília). Alimenta o tooltip do título da coluna, deixando
    # transparente o período exato filtrado no BD (fuso BRT).
    window_ranges = {
        w: {
            "from": dt_windows[w][0].astimezone(UTC).isoformat(),
            "to": dt_windows[w][1].astimezone(UTC).isoformat(),
        }
        for w in _WINDOWS
    }

    return {
        "windows": _WINDOWS,
        "window_labels": _WINDOW_LABELS,
        "window_ranges": window_ranges,
        "row_meta": row_meta,
        "rows": rows,
        "extras": extras,
        "scope": {
            "is_global": is_global,
            "account_id": account_id,
            "platform": platform,
            "generated_at": now_brt.astimezone(UTC).isoformat(),  # contrato único: UTC
        },
    }

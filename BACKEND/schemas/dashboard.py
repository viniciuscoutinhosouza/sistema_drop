from pydantic import BaseModel
from typing import List
from decimal import Decimal


class KPIResponse(BaseModel):
    monthly_sales_count: int
    monthly_sales_value: Decimal
    monthly_sales_change_pct: float   # vs previous month
    unpaid_orders_count: int
    unlinked_orders_count: int
    cancelled_orders_count: int
    total_products: int
    sales_last_30_days: Decimal
    sales_today: Decimal


class TopProductSchema(BaseModel):
    id: int
    sku: str
    title: str
    cost_price: Decimal
    stock_quantity: int
    image_url: str = ""

    model_config = {"from_attributes": True}

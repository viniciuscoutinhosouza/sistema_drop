import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.kit import Kit, KitComponent
from models.product import CatalogProduct, CatalogProductVariant


async def calculate_kit_stock(db: AsyncSession, kit_id: int) -> int:
    """
    Kit stock = min(floor(component_stock / component_quantity))
    across all components.
    Returns 0 if kit has no components.
    """
    result = await db.execute(
        select(KitComponent).where(KitComponent.kit_id == kit_id)
    )
    components = result.scalars().all()

    if not components:
        return 0

    min_stock = None
    for comp in components:
        if comp.variant_id:
            stock_result = await db.execute(
                select(CatalogProductVariant.stock_quantity)
                .where(CatalogProductVariant.id == comp.variant_id)
            )
            stock = stock_result.scalar() or 0
        elif comp.product_id:
            stock_result = await db.execute(
                select(CatalogProduct.stock_quantity)
                .where(CatalogProduct.id == comp.product_id)
            )
            stock = stock_result.scalar() or 0
        else:
            stock = 0

        contribution = math.floor(stock / comp.quantity) if comp.quantity > 0 else 0
        if min_stock is None or contribution < min_stock:
            min_stock = contribution

    return min_stock or 0

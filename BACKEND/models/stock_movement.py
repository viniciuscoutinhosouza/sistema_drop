from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, text

from database import Base


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True)
    product_type = Column(String(20), nullable=False)   # 'pg' | 'cmig' | 'variant_pg' | 'variant_cmig'
    product_id = Column(Integer, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    return_id = Column(Integer, ForeignKey("returns.id"), nullable=True)
    movement_type = Column(String(40), nullable=False)  # reserve|unreserve|dispatch|await_return|...
    qty = Column(Integer, nullable=False)
    field_affected = Column(String(50), nullable=False)  # reserved_quantity|stock_quantity|...
    delta = Column(Integer, nullable=False)              # positivo=entrada, negativo=saída
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

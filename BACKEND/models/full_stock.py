from sqlalchemy import TIMESTAMP, Boolean, Column, ForeignKey, Integer, String, text

from database import Base


class FullCnpj(Base):
    __tablename__ = "full_cnpjs"

    id = Column(Integer, primary_key=True)
    marketplace_account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    cnpj = Column(String(18), nullable=False)
    label = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))


class FullStock(Base):
    __tablename__ = "full_stock"

    id = Column(Integer, primary_key=True)
    product_type = Column(String(10), nullable=False)   # 'cmig' | 'pg'
    product_id = Column(Integer, nullable=False)
    marketplace_account_id = Column(Integer, ForeignKey("marketplace_accounts.id"), nullable=False)
    qty = Column(Integer, default=0, nullable=False)             # estoque físico FULL
    reserved_qty = Column(Integer, default=0, nullable=False)    # vendas FULL baixadas, não shipped
    updated_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

    @property
    def available_qty(self) -> int:
        """Disponível para venda = físico - reservado (nunca < 0)."""
        return max(0, int(self.qty or 0) - int(self.reserved_qty or 0))

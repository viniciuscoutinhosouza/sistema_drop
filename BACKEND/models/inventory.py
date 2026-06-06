from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class Inventory(Base):
    """Documento de inventário físico de um catálogo (PG ou uma CMIG).

    A contagem física informada por item vira um evento durável que o
    `stock_calculator` respeita (sobrevive a recomputes). Dois modos:

    - `baseline`: a contagem vira a verdade na data (reset do saldo). Eventos
      anteriores à contagem são descartados; só os posteriores ajustam.
    - `adjustment`: gera um delta (contado - sistema) somado ao saldo de eventos.
    """

    __tablename__ = "inventories"

    id = Column(Integer, primary_key=True)
    # `number` e `mode` são palavras reservadas no Oracle → colunas inv_number/inv_mode,
    # mas o atributo Python/JSON continua number/mode.
    number = Column("inv_number", Integer, nullable=False)  # sequencial, gerado na criação
    mode = Column("inv_mode", String(12), nullable=False)  # 'baseline' | 'adjustment'
    catalog_type = Column(String(10), nullable=False)  # 'pg' | 'cmig'
    cmig_id = Column(Integer, ForeignKey("cmigs.id"), nullable=True)  # obrigatório se catalog_type='cmig'
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    status = Column(String(12), nullable=False, default="draft")  # draft|finalized|cancelled
    notes = Column(String(1000))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    finalized_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    finalized_at = Column(TIMESTAMP(timezone=True), nullable=True)

    items = relationship(
        "InventoryItem", back_populates="inventory", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("inv_mode IN ('baseline','adjustment')", name="ck_inv_mode"),
        CheckConstraint("catalog_type IN ('pg','cmig')", name="ck_inv_catalog"),
        CheckConstraint(
            "status IN ('draft','finalized','cancelled')", name="ck_inv_status"
        ),
    )


class InventoryItem(Base):
    """Linha de contagem de um produto dentro de um inventário."""

    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True)
    inventory_id = Column(Integer, ForeignKey("inventories.id"), nullable=False)
    product_type = Column(String(10), nullable=False)  # 'pg' | 'cmig'
    product_id = Column(Integer, nullable=False)
    system_qty = Column(Integer, nullable=False, default=0)  # snapshot do saldo calculado
    counted_qty = Column(Integer, nullable=True)  # NULL = ainda não contado
    delta = Column(Integer, nullable=True)  # counted - system, congelado na finalização
    counted_at = Column(TIMESTAMP(timezone=True), nullable=True)

    inventory = relationship("Inventory", back_populates="items")

    __table_args__ = (
        CheckConstraint("product_type IN ('pg','cmig')", name="ck_invitem_type"),
    )

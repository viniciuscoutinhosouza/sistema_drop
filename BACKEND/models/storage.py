"""Endereçamento Físico de Estoque (ADR-0039) — camada ADITIVA de LOCALIZAÇÃO.

Diz ONDE o estoque está, reconcilia com o saldo escalar (ADR-0004) e o sub-ledger de lotes
(ADR-0027) e NUNCA grava saldo. `product_type` segue o enum de stock_movements/traceability:
'pg' | 'cmig' | 'variant_pg' | 'variant_cmig'.
"""
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import relationship

from database import Base


class StorageLocation(Base):
    """Nó da árvore de endereços de um galpão (do maior ao menor; folha = armazenável).

    `full_code` é derivado (caminho dos `code` dos ancestrais) e gravado p/ busca/etiqueta; é
    recomputado na subárvore quando um pai é renomeado (serviço `storage_service`).
    """

    __tablename__ = "storage_locations"

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("storage_locations.id"), nullable=True)
    level_type = Column(String(40), nullable=False)   # Sala, Armário, Estante, Coluna, Altura, Pallet…
    code = Column(String(60), nullable=False)          # identificação: nome/número/letra
    full_code = Column(String(500), nullable=False)    # derivado (caminho) — UNIQUE por galpão
    is_storable = Column(Boolean, nullable=False, server_default=text("0"))  # folha que recebe produto
    pick_sequence = Column(Integer, nullable=False, server_default=text("0"))  # rota de picking (Fase 2)
    area_kind = Column(String(10))                     # 'pallet' | 'cabinet' | 'other' (só na raiz da área)
    child_scheme = Column(String(200))                 # hint do padrão de filhos (continuar a sequência)
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    notes = Column(String(500))
    last_counted_at = Column(TIMESTAMP(timezone=True))   # inventário por endereço (Fase 3a) — migration 176
    last_counted_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    children = relationship(
        "StorageLocation",
        backref="parent",
        remote_side=[id],
        uselist=True,
        viewonly=True,
    )


class ProductAllocation(Base):
    """Produto (± lote) alocado num local armazenável, com quantidade total em unidades.

    `lot_id` só p/ produto rastreável (ADR-0027). UNIQUE (location, product, lot) via índice
    funcional NVL. Deletada direto (hard-delete) cascateando packs e etiquetas (no serviço).
    """

    __tablename__ = "product_allocations"

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("storage_locations.id"), nullable=False)
    product_type = Column(String(20), nullable=False)  # pg|cmig|variant_pg|variant_cmig
    product_id = Column(Integer, nullable=False)
    lot_id = Column(Integer, ForeignKey("product_lots.id"), nullable=True)
    qty_units = Column(Integer, nullable=False, server_default=text("0"))
    pick_order = Column(Integer, nullable=False, server_default=text("0"))  # ordem entre locais do produto
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )

    packs = relationship(
        "ProductAllocationPack", backref="allocation", cascade="all, delete-orphan"
    )


class ProductAllocationPack(Base):
    """Composição de caixas de uma alocação: box_count caixas de units_per_box unidades.

    Heterogêneo = N linhas (3×10 + 4×8 + 1×20). Unidades soltas = qty_units − Σ(box·upb)."""

    __tablename__ = "product_allocation_packs"

    id = Column(Integer, primary_key=True)
    allocation_id = Column(Integer, ForeignKey("product_allocations.id"), nullable=False)
    box_count = Column(Integer, nullable=False, server_default=text("0"))
    units_per_box = Column(Integer, nullable=False, server_default=text("0"))
    label = Column(String(100))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))


class ProductPackDefault(Base):
    """Embalagem-padrão reutilizável por produto (sugere no modal de alocação)."""

    __tablename__ = "product_pack_defaults"

    id = Column(Integer, primary_key=True)
    product_type = Column(String(20), nullable=False)
    product_id = Column(Integer, nullable=False)
    units_per_box = Column(Integer, nullable=False)
    label = Column(String(100))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"), onupdate=text("SYSTIMESTAMP")
    )


class StorageBoxLabel(Base):
    """Etiqueta/QR de caixa física: `token` (no QR) → alocação. Base da bipagem/contagem (Fase 2) e,
    a partir da Fase 3c (box tracking, migration 178), unidade com CICLO DE VIDA e movível de endereço.

    `status`: 'closed' (caixa fechada, rastreável/movível) | 'open' (aberta → unidades soltas no mesmo
    endereço) | 'consumed' (etiqueta retirada: reemissão/DELETE, ou futura baixa por caixa no despacho).
    INVARIANTE: `is_active == (status == 'closed')` — `is_active` segue como compat; o ponto único
    `storage_service.box_labels_to_close` carimba status='open' junto do is_active=False, e os 2 sites
    diretos (reemissão/DELETE) carimbam status='consumed'. O endereço da caixa é o da sua alocação
    (sem coluna location_id — fonte única); mover a caixa repontar `allocation_id` p/ a alocação do
    endereço de destino (mesmo token)."""

    __tablename__ = "storage_box_labels"

    id = Column(Integer, primary_key=True)
    token = Column(String(40), nullable=False, unique=True)
    allocation_id = Column(Integer, ForeignKey("product_allocations.id"), nullable=False)
    units_per_box = Column(Integer, nullable=False, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    status = Column(String(12), nullable=False, server_default=text("'closed'"))  # closed|open|consumed
    printed_by = Column(Integer, ForeignKey("users.id"))
    printed_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    moved_at = Column(TIMESTAMP(timezone=True))   # última movimentação de caixa (Fase 3c)
    moved_by = Column(Integer, ForeignKey("users.id"))


class ProductAllocationMovement(Base):
    """Razão append-only do movimento de ENDEREÇO (ADR-0039) — migration 175 (+ 'adjust' na 176).

    Espelha stock_movements × qty_units: o débito ao despachar (reason='dispatch', delta<0), o crédito
    no retorno ao vendável (reason='return', delta>0) e o ajuste de inventário por contagem física
    (reason='adjust', Fase 3a, delta ±) só movem `product_allocations.qty_units`; o saldo escalar
    (ADR-0004) é debitado pelo código existente do `confirm_dispatch`, independente.

    `product_type`/`product_id` = a ALOCAÇÃO de fato tocada (pode ser variant_pg/variant_cmig).
    `base_product_type`/`base_product_id` = o produto-LÓGICO (pg|cmig base) — bridge p/ o crédito do
    retorno (base-level) reencontrar os débitos feitos no nível de variante. Idempotência: débito por
    (order_id, reason='dispatch'); crédito por (return_id, reason='return')."""

    __tablename__ = "product_allocation_movements"

    id = Column(Integer, primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"))
    return_id = Column(Integer, ForeignKey("returns.id"))
    allocation_id = Column(Integer, ForeignKey("product_allocations.id"))
    location_id = Column(Integer, ForeignKey("storage_locations.id"))
    product_type = Column(String(20), nullable=False)
    product_id = Column(Integer, nullable=False)
    base_product_type = Column(String(20), nullable=False)
    base_product_id = Column(Integer, nullable=False)
    lot_id = Column(Integer, ForeignKey("product_lots.id"))
    delta_units = Column(Integer, nullable=False)
    reason = Column(String(20), nullable=False)  # dispatch | return
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Integer, String, text

from database import Base


class ProductEan(Base):
    """EAN ADICIONAL de um produto (CMIG ou PG) — migration 172.

    Um produto pode ter 1+ EANs: o principal fica na coluna `.ean` do próprio produto; os
    adicionais ficam aqui. Usado para reconciliar NF-e de entrada cujo EAN não bate com o cadastro,
    sem perder o EAN principal. Exatamente uma das FKs é preenchida (CHECK no banco).
    O casamento de estoque (stock_history/stock_calculator) consulta a coluna nativa E esta tabela.
    """

    __tablename__ = "product_eans"

    id = Column(Integer, primary_key=True)
    cmig_product_id = Column(Integer, ForeignKey("cmig_products.id"), nullable=True)
    catalog_product_id = Column(Integer, ForeignKey("catalog_products.id"), nullable=True)
    ean = Column(String(14), nullable=False)
    # 'ean' = EAN de fabricante (pode repetir entre galpões) | 'internal' = código interno gerado
    # (EAN-13 faixa prefixo 2 + DV, único globalmente via índice funcional — migration 173, ADR-0039).
    source = Column(String(10), nullable=False, server_default=text("'ean'"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))

from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from database import Base


class Warehouse(Base):
    """Galpão pertencente a um GO. Um GO pode ter múltiplos galpões."""
    __tablename__ = "warehouses"

    id           = Column(Integer, primary_key=True)
    go_id        = Column(Integer, ForeignKey("goes.id"), nullable=True)
    name         = Column(String(200), nullable=False)
    cnpj         = Column(String(18))
    company_name = Column(String(255))
    trade_name   = Column(String(255))
    phone        = Column(String(20))
    whatsapp     = Column(String(20))
    email        = Column(String(255))
    zip_code     = Column(String(9))
    street       = Column(String(255))
    number       = Column('address_number', String(20))
    complement   = Column(String(100))
    neighborhood = Column(String(100))
    city         = Column(String(100))
    state        = Column(String(2))
    pix_key_type = Column(String(20))   # cpf | cnpj | email | phone | random
    pix_key      = Column(String(255))
    notes        = Column(String(2000))
    created_at   = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at   = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                          onupdate=text("SYSTIMESTAMP"))

    go    = relationship("GO", back_populates="warehouses", foreign_keys=[go_id])
    cmigs = relationship("CMIG", back_populates="warehouse")

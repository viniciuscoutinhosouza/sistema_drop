from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey, text, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base


class Person(Base):
    """Cadastro unificado Cliente / Fornecedor / Transportador, escopo por CMIG."""
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("cmig_id", "document", name="uq_people_cmig_doc"),)

    id              = Column(Integer, primary_key=True)
    cmig_id         = Column(Integer, ForeignKey("cmigs.id"), nullable=False)
    person_type     = Column(String(2), nullable=False)
    document        = Column(String(20), nullable=False)
    ie              = Column(String(20))
    ie_isento       = Column(Boolean, nullable=False, default=False)
    im              = Column(String(20))
    name            = Column(String(255), nullable=False)
    trade_name      = Column(String(255))
    email           = Column(String(255))
    phone           = Column(String(20))
    zip_code        = Column(String(9))
    street          = Column(String(255))
    address_number  = Column(String(20))
    complement      = Column(String(100))
    neighborhood    = Column(String(100))
    city            = Column(String(100))
    state           = Column(String(2))
    ibge_code       = Column(String(7))
    country_code    = Column(String(4), default="1058")
    is_customer     = Column(Boolean, nullable=False, default=True)
    is_supplier     = Column(Boolean, nullable=False, default=False)
    is_carrier      = Column(Boolean, nullable=False, default=False)
    notes           = Column(String(2000))
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"))
    updated_at      = Column(TIMESTAMP(timezone=True), server_default=text("SYSTIMESTAMP"),
                             onupdate=text("SYSTIMESTAMP"))

    cmig = relationship("CMIG", back_populates="people")

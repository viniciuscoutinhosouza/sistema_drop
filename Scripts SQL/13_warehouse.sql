-- ============================================================
-- MIG ECOMMERCE – Script 13: Galpão do Gestor Operacional
-- ============================================================

CREATE TABLE warehouses (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            VARCHAR2(200)   NOT NULL,
    cnpj            VARCHAR2(18),
    company_name    VARCHAR2(255),
    trade_name      VARCHAR2(255),
    phone           VARCHAR2(20),
    whatsapp        VARCHAR2(20),
    email           VARCHAR2(255),
    zip_code        VARCHAR2(9),
    street          VARCHAR2(255),
    address_number  VARCHAR2(20),
    complement      VARCHAR2(100),
    neighborhood    VARCHAR2(100),
    city            VARCHAR2(100),
    state           VARCHAR2(2),
    pix_key_type    VARCHAR2(20),   -- cpf | cnpj | email | phone | random
    pix_key         VARCHAR2(255),
    notes           VARCHAR2(2000),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE OR REPLACE TRIGGER trg_warehouses_updated_at
    BEFORE UPDATE ON warehouses
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

COMMIT;

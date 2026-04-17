-- ============================================================
-- MIG ECOMMERCE – Script 08: Devoluções
-- ============================================================

CREATE TABLE returns (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id  NUMBER          NOT NULL,
    order_id        NUMBER,
    reason          VARCHAR2(50)
                        CONSTRAINT chk_ret_reason CHECK (reason IN (
                            'defeito', 'produto_errado', 'desistencia', 'outro'
                        )),
    description     CLOB,
    tracking_code   VARCHAR2(100),
    tracking_url    VARCHAR2(500),
    carrier         VARCHAR2(100),
    expected_date   DATE,
    security_code   VARCHAR2(100),      -- Código de segurança do marketplace
    status          VARCHAR2(20)    DEFAULT 'analyzing' NOT NULL
                        CONSTRAINT chk_ret_status CHECK (status IN ('analyzing','returned','rejected')),
    supplier_notes  CLOB,               -- Notas do fornecedor ao analisar
    credit_amount   NUMBER(15,2),       -- Valor creditado de volta (se devolvido)
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_ret_dropshipper   FOREIGN KEY (dropshipper_id) REFERENCES users(id),
    CONSTRAINT fk_ret_order         FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE OR REPLACE TRIGGER trg_returns_updated_at
    BEFORE UPDATE ON returns
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE INDEX idx_ret_dropshipper    ON returns(dropshipper_id);
CREATE INDEX idx_ret_status         ON returns(dropshipper_id, status);
CREATE INDEX idx_ret_order          ON returns(order_id);

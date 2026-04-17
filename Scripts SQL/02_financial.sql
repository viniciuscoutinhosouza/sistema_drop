-- ============================================================
-- MIG ECOMMERCE – Script 02: Módulo Financeiro
-- ============================================================

CREATE TABLE financial_transactions (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dropshipper_id  NUMBER          NOT NULL,
    type            VARCHAR2(20)    NOT NULL
                        CONSTRAINT chk_ft_type CHECK (type IN ('credit','debit')),
    amount          NUMBER(15,2)    NOT NULL,
    description     VARCHAR2(500),
    reference_type  VARCHAR2(50),   -- 'order' | 'pix_deposit' | 'subscription' | 'return'
    reference_id    NUMBER,
    balance_before  NUMBER(15,2)    NOT NULL,
    balance_after   NUMBER(15,2)    NOT NULL,
    pix_key         VARCHAR2(255),
    pix_txid        VARCHAR2(255),
    status          VARCHAR2(20)    NOT NULL DEFAULT 'completed'
                        CONSTRAINT chk_ft_status CHECK (status IN ('pending','completed','failed','reversed')),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_ft_dropshipper FOREIGN KEY (dropshipper_id) REFERENCES users(id)
);

CREATE INDEX idx_ft_dropshipper ON financial_transactions(dropshipper_id, created_at DESC);
CREATE INDEX idx_ft_type        ON financial_transactions(dropshipper_id, type);
CREATE INDEX idx_ft_status      ON financial_transactions(dropshipper_id, status);

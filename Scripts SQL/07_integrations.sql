-- ============================================================
-- MIG ECOMMERCE – Script 07: CONTAs de Marketplace
-- v2.0 – marketplace_integrations renomeado para marketplace_accounts
--         dropshipper_id renomeado para owner_id
--         Adicionados: email, phone, otp_verified
--         Nova tabela: account_administrators (many-to-many AC <-> CONTA)
--         Nova tabela: account_balances (saldo operacional por CONTA)
--         Nova tabela: account_transactions (extrato financeiro por CONTA)
--         Nova tabela: otp_verifications
-- ============================================================

CREATE TABLE marketplace_accounts (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id            NUMBER          NOT NULL,       -- AC que criou a CONTA
    platform            VARCHAR2(20)    NOT NULL
                            CONSTRAINT chk_ma_platform CHECK (platform IN ('mercadolivre','shopee','bling')),
    description         VARCHAR2(200),
    email               VARCHAR2(255),                  -- E-mail da conta no marketplace
    phone               VARCHAR2(20),                   -- Celular da conta no marketplace
    access_token        VARCHAR2(2000),
    refresh_token       VARCHAR2(2000),
    token_expires_at    TIMESTAMP WITH TIME ZONE,
    platform_user_id    VARCHAR2(200),
    platform_username   VARCHAR2(200),
    shop_id             NUMBER,
    api_key             VARCHAR2(500),
    is_active           NUMBER(1)       DEFAULT 1 NOT NULL
                            CONSTRAINT chk_ma_active CHECK (is_active IN (0,1)),
    otp_verified        NUMBER(1)       DEFAULT 0 NOT NULL
                            CONSTRAINT chk_ma_otp CHECK (otp_verified IN (0,1)),
    last_sync_at        TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_ma_owner      FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT uq_ma_identity   UNIQUE (platform, email, phone)
);

-- Many-to-many: AC <-> CONTA (co-administração)
CREATE TABLE account_administrators (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     NUMBER      NOT NULL,
    account_id  NUMBER      NOT NULL,
    is_owner    NUMBER(1)   DEFAULT 0 NOT NULL
                    CONSTRAINT chk_aa_owner CHECK (is_owner IN (0,1)),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_aa_user    FOREIGN KEY (user_id)    REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_aa_account FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_aa_user_account UNIQUE (user_id, account_id)
);

-- Saldo operacional por CONTA (etiquetas, NFs, taxas)
CREATE TABLE account_balances (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id      NUMBER          NOT NULL,
    balance         NUMBER(15,2)    DEFAULT 0 NOT NULL,
    balance_reserved NUMBER(15,2)   DEFAULT 0 NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_ab_account FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_ab_account UNIQUE (account_id)
);

-- Extrato financeiro operacional por CONTA
CREATE TABLE account_transactions (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_balance_id  NUMBER          NOT NULL,
    type                VARCHAR2(10)    NOT NULL
                            CONSTRAINT chk_at_type CHECK (type IN ('credit','debit')),
    amount              NUMBER(15,2)    NOT NULL,
    description         VARCHAR2(500),
    reference_type      VARCHAR2(50),   -- order | pix_deposit | label | nfe | fee
    reference_id        NUMBER,
    pix_key             VARCHAR2(100),
    pix_txid            VARCHAR2(200),
    status              VARCHAR2(20)    DEFAULT 'pending' NOT NULL
                            CONSTRAINT chk_at_status CHECK (status IN ('pending','completed','failed')),
    balance_before      NUMBER(15,2),
    balance_after       NUMBER(15,2),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_at_balance FOREIGN KEY (account_balance_id) REFERENCES account_balances(id)
);

-- OTP para verificação de vínculo de CONTA
CREATE TABLE otp_verifications (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id  NUMBER          NOT NULL,
    code        VARCHAR2(6)     NOT NULL,
    channel     VARCHAR2(10)    NOT NULL
                    CONSTRAINT chk_otp_channel CHECK (channel IN ('email','whatsapp')),
    destination VARCHAR2(255)   NOT NULL,
    is_used     NUMBER(1)       DEFAULT 0 NOT NULL
                    CONSTRAINT chk_otp_used CHECK (is_used IN (0,1)),
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_otp_account FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id) ON DELETE CASCADE
);

-- Índices
CREATE INDEX idx_ma_owner       ON marketplace_accounts(owner_id);
CREATE INDEX idx_ma_platform    ON marketplace_accounts(platform);
CREATE INDEX idx_aa_user        ON account_administrators(user_id);
CREATE INDEX idx_aa_account     ON account_administrators(account_id);
CREATE INDEX idx_ab_account     ON account_balances(account_id);
CREATE INDEX idx_at_balance     ON account_transactions(account_balance_id);

-- Trigger atualiza updated_at em account_balances
CREATE OR REPLACE TRIGGER trg_ab_updated_at
    BEFORE UPDATE ON account_balances
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- FK de orders.integration_id (criada em 06_orders.sql) agora aponta para marketplace_accounts
-- Nota: renomear a constraint se já existir no banco
ALTER TABLE orders ADD CONSTRAINT fk_ord_account
    FOREIGN KEY (integration_id) REFERENCES marketplace_accounts(id);

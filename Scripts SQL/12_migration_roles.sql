-- ============================================================
-- MIG ECOMMERCE – Script 12: Migração de dados (v1 → v2)
-- Executa em banco existente que usava os roles antigos
-- ============================================================

-- 1. Remover constraint de role antiga
ALTER TABLE users DROP CONSTRAINT chk_users_role;

-- 2. Migrar valores de role
UPDATE users SET role = 'ugo'   WHERE role = 'supplier';
UPDATE users SET role = 'ac'    WHERE role = 'dropshipper';

-- 3. Adicionar nova constraint
ALTER TABLE users ADD CONSTRAINT chk_users_role
    CHECK (role IN ('ugo','ac','admin'));

-- 4. Renomear tabela dropshipper_profiles → ac_profiles
RENAME dropshipper_profiles TO ac_profiles;

-- 5. Adicionar coluna plan_id em ac_profiles (se não existir)
ALTER TABLE ac_profiles ADD (plan_id NUMBER);

-- 6. Remover colunas de saldo de ac_profiles (agora ficam em account_balances)
--    Fazer backup antes!
-- ALTER TABLE ac_profiles DROP COLUMN balance;
-- ALTER TABLE ac_profiles DROP COLUMN balance_reserved;

-- 7. Renomear marketplace_integrations → marketplace_accounts
RENAME marketplace_integrations TO marketplace_accounts;

-- 8. Renomear coluna dropshipper_id → owner_id em marketplace_accounts
ALTER TABLE marketplace_accounts RENAME COLUMN dropshipper_id TO owner_id;

-- 9. Adicionar novas colunas em marketplace_accounts
ALTER TABLE marketplace_accounts ADD (
    email           VARCHAR2(255),
    phone           VARCHAR2(20),
    otp_verified    NUMBER(1) DEFAULT 0 NOT NULL
                        CONSTRAINT chk_ma_otp CHECK (otp_verified IN (0,1))
);

-- 10. Criar tabela account_administrators
--     Popular com registros existentes (cada owner_id vira o administrador)
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

INSERT INTO account_administrators (user_id, account_id, is_owner)
SELECT owner_id, id, 1 FROM marketplace_accounts;

-- 11. Criar tabela account_balances (migrar saldo de ac_profiles)
CREATE TABLE account_balances (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id      NUMBER          NOT NULL,
    balance         NUMBER(15,2)    DEFAULT 0 NOT NULL,
    balance_reserved NUMBER(15,2)   DEFAULT 0 NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_ab_account FOREIGN KEY (account_id) REFERENCES marketplace_accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_ab_account UNIQUE (account_id)
);

INSERT INTO account_balances (account_id, balance)
SELECT id, 0 FROM marketplace_accounts;

-- 12. Renomear FK de orders (se existir fk_ord_integration)
-- ALTER TABLE orders DROP CONSTRAINT fk_ord_integration;
-- ALTER TABLE orders ADD CONSTRAINT fk_ord_account
--     FOREIGN KEY (integration_id) REFERENCES marketplace_accounts(id);

-- 13. Criar access_plans e ac_subscriptions se não existirem
CREATE TABLE access_plans (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            VARCHAR2(100)   NOT NULL,
    max_accounts    NUMBER          NOT NULL,
    monthly_price   NUMBER(10,2)    NOT NULL,
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_ap_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO access_plans (name, max_accounts, monthly_price) VALUES ('Starter', 3, 99.90);
INSERT INTO access_plans (name, max_accounts, monthly_price) VALUES ('Pro', 10, 199.90);
INSERT INTO access_plans (name, max_accounts, monthly_price) VALUES ('Enterprise', -1, 399.90);

-- 14. Adicionar FK de ac_profiles → access_plans
ALTER TABLE ac_profiles ADD CONSTRAINT fk_acp_plan
    FOREIGN KEY (plan_id) REFERENCES access_plans(id);

COMMIT;

-- ============================================================
-- VALIDAÇÃO
-- ============================================================
SELECT role, COUNT(*) as total FROM users GROUP BY role;
SELECT COUNT(*) as contas FROM marketplace_accounts;
SELECT COUNT(*) as admins FROM account_administrators;
SELECT COUNT(*) as saldos FROM account_balances;

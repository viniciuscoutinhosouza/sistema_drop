-- ============================================================
-- MIG ECOMMERCE – Script 01: Usuários e Autenticação
-- v2.0 – Roles atualizados: ugo | ac | admin
-- Tabela de perfil renomeada: dropshipper_profiles → ac_profiles
-- Banco: Oracle ATP
-- ============================================================

-- Tabela principal de usuários
CREATE TABLE users (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email               VARCHAR2(255)   NOT NULL,
    password_hash       VARCHAR2(255)   NOT NULL,
    role                VARCHAR2(20)    DEFAULT 'ac' NOT NULL
                            CONSTRAINT chk_users_role CHECK (role IN ('ugo','ac','admin')),
    full_name           VARCHAR2(255)   NOT NULL,
    whatsapp            VARCHAR2(20),
    cpf_cnpj            VARCHAR2(18),
    is_active           NUMBER(1)       DEFAULT 1 NOT NULL
                            CONSTRAINT chk_users_active CHECK (is_active IN (0,1)),
    dark_mode           NUMBER(1)       DEFAULT 0 NOT NULL
                            CONSTRAINT chk_users_dark CHECK (dark_mode IN (0,1)),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_users_email    UNIQUE (email),
    CONSTRAINT uq_users_cpfcnpj  UNIQUE (cpf_cnpj)
);

-- Planos de acesso para AC (cobrado por número de CONTAs ativas)
CREATE TABLE access_plans (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            VARCHAR2(100)   NOT NULL,
    max_accounts    NUMBER          NOT NULL,       -- -1 = ilimitado
    monthly_price   NUMBER(10,2)    NOT NULL,
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_ap_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

-- Perfil do Administrador de Conta (AC)
CREATE TABLE ac_profiles (
    id                      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                 NUMBER          NOT NULL,
    zip_code                VARCHAR2(9),
    street                  VARCHAR2(255),
    address_number          VARCHAR2(20),
    complement              VARCHAR2(100),
    neighborhood            VARCHAR2(100),
    city                    VARCHAR2(100),
    state                   VARCHAR2(2),
    plan_id                 NUMBER,
    subscription_status     VARCHAR2(20)    DEFAULT 'active' NOT NULL
                                CONSTRAINT chk_sub_status CHECK (
                                    subscription_status IN ('active','overdue','suspended')
                                ),
    subscription_due_date   DATE,
    CONSTRAINT fk_acp_user   FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_acp_plan   FOREIGN KEY (plan_id) REFERENCES access_plans(id),
    CONSTRAINT uq_acp_user   UNIQUE (user_id)
);

-- Histórico de assinaturas do AC
CREATE TABLE ac_subscriptions (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id      NUMBER          NOT NULL,
    plan_id         NUMBER          NOT NULL,
    status          VARCHAR2(20)    DEFAULT 'active' NOT NULL
                        CONSTRAINT chk_acs_status CHECK (status IN ('active','overdue','cancelled')),
    period_start    DATE            NOT NULL,
    period_end      DATE            NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_acs_profile FOREIGN KEY (profile_id) REFERENCES ac_profiles(id),
    CONSTRAINT fk_acs_plan    FOREIGN KEY (plan_id) REFERENCES access_plans(id),
    CONSTRAINT uq_acs_profile UNIQUE (profile_id)
);

-- Refresh tokens JWT
CREATE TABLE refresh_tokens (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     NUMBER          NOT NULL,
    token       VARCHAR2(500)   NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked     NUMBER(1)       DEFAULT 0 NOT NULL
                    CONSTRAINT chk_rt_revoked CHECK (revoked IN (0,1)),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_rt_user   FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_rt_token  UNIQUE (token)
);

-- Índices de performance
CREATE INDEX idx_users_email        ON users(email);
CREATE INDEX idx_rt_user_id         ON refresh_tokens(user_id);
CREATE INDEX idx_acp_user_id        ON ac_profiles(user_id);
CREATE INDEX idx_acp_plan_id        ON ac_profiles(plan_id);

-- Trigger para atualizar updated_at no users
CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Planos padrão iniciais
INSERT INTO access_plans (name, max_accounts, monthly_price) VALUES ('Starter', 3, 99.90);
INSERT INTO access_plans (name, max_accounts, monthly_price) VALUES ('Pro', 10, 199.90);
INSERT INTO access_plans (name, max_accounts, monthly_price) VALUES ('Enterprise', -1, 399.90);

-- Usuário admin inicial (senha: admin@123 – trocar antes de produção)
INSERT INTO users (email, password_hash, role, full_name, is_active)
VALUES (
    'admin@migcommerce.com.br',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'admin',
    'Administrador',
    1
);

COMMIT;

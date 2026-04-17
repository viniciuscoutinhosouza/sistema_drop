-- ============================================================
-- MIG ECOMMERCE – Script 01: Usuários e Autenticação
-- Banco: Oracle ATP
-- Execução: Rodar como o usuário do schema do sistema
-- ============================================================

-- Tabela principal de usuários
CREATE TABLE users (
    id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email               VARCHAR2(255)   NOT NULL,
    password_hash       VARCHAR2(255)   NOT NULL,
    role                VARCHAR2(20)    NOT NULL DEFAULT 'dropshipper'
                            CONSTRAINT chk_users_role CHECK (role IN ('supplier','dropshipper','admin')),
    full_name           VARCHAR2(255)   NOT NULL,
    whatsapp            VARCHAR2(20),
    cpf_cnpj            VARCHAR2(18),
    is_active           NUMBER(1)       NOT NULL DEFAULT 1
                            CONSTRAINT chk_users_active CHECK (is_active IN (0,1)),
    dark_mode           NUMBER(1)       NOT NULL DEFAULT 0
                            CONSTRAINT chk_users_dark CHECK (dark_mode IN (0,1)),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_users_email    UNIQUE (email),
    CONSTRAINT uq_users_cpfcnpj  UNIQUE (cpf_cnpj)
);

-- Perfil do dropshipper (extensão de users)
CREATE TABLE dropshipper_profiles (
    id                      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id                 NUMBER          NOT NULL,
    zip_code                VARCHAR2(9),
    street                  VARCHAR2(255),
    number                  VARCHAR2(20),
    complement              VARCHAR2(100),
    neighborhood            VARCHAR2(100),
    city                    VARCHAR2(100),
    state                   VARCHAR2(2),
    subscription_status     VARCHAR2(20)    NOT NULL DEFAULT 'active'
                                CONSTRAINT chk_sub_status CHECK (
                                    subscription_status IN ('active','overdue','suspended')
                                ),
    subscription_due_date   DATE,
    balance                 NUMBER(15,2)    NOT NULL DEFAULT 0,
    balance_reserved        NUMBER(15,2)    NOT NULL DEFAULT 0,
    CONSTRAINT fk_dp_user   FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT uq_dp_user   UNIQUE (user_id)
);

-- Refresh tokens JWT
CREATE TABLE refresh_tokens (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     NUMBER          NOT NULL,
    token       VARCHAR2(500)   NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked     NUMBER(1)       NOT NULL DEFAULT 0
                    CONSTRAINT chk_rt_revoked CHECK (revoked IN (0,1)),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_rt_user   FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_rt_token  UNIQUE (token)
);

-- Índices de performance
CREATE INDEX idx_users_email        ON users(email);
CREATE INDEX idx_rt_user_id         ON refresh_tokens(user_id);
CREATE INDEX idx_dp_user_id         ON dropshipper_profiles(user_id);

-- Trigger para atualizar updated_at no users
CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Usuário admin inicial (senha: admin@123 – trocar antes de produção)
-- password_hash abaixo é bcrypt de 'admin@123'
INSERT INTO users (email, password_hash, role, full_name, is_active)
VALUES (
    'admin@migcommerce.com.br',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'admin',
    'Administrador',
    1
);

COMMIT;

-- ============================================================
-- MIG ECOMMERCE – Script 16: Migração v3
-- Multi-GO, Multi-Galpão, CMIG, Produtos CMIG, NF-e Config
-- Banco: Oracle ATP
-- ============================================================

-- ============================================================
-- 1. NOVAS TABELAS
-- ============================================================

-- Empresas GO (Gestores Operacionais)
CREATE TABLE goes (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         NUMBER          NOT NULL,
    cnpj            VARCHAR2(18)    NOT NULL,
    company_name    VARCHAR2(255)   NOT NULL,
    trade_name      VARCHAR2(255),
    phone           VARCHAR2(20),
    email           VARCHAR2(255),
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_goes_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_goes_user   FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT uq_goes_user   UNIQUE (user_id),
    CONSTRAINT uq_goes_cnpj   UNIQUE (cnpj)
);

CREATE INDEX idx_goes_user_id ON goes(user_id);

CREATE OR REPLACE TRIGGER trg_goes_updated_at
    BEFORE UPDATE ON goes
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Contas MIG (CMIG) – CNPJ fiscal do AC
CREATE TABLE cmigs (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_ac_id     NUMBER          NOT NULL,
    warehouse_id    NUMBER          NOT NULL,
    cnpj            VARCHAR2(18)    NOT NULL,
    company_name    VARCHAR2(255)   NOT NULL,
    trade_name      VARCHAR2(255),
    email           VARCHAR2(255),
    phone           VARCHAR2(20),
    zip_code        VARCHAR2(9),
    street          VARCHAR2(255),
    address_number  VARCHAR2(20),
    complement      VARCHAR2(100),
    neighborhood    VARCHAR2(100),
    city            VARCHAR2(100),
    state           VARCHAR2(2),
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_cmigs_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_cmigs_owner     FOREIGN KEY (owner_ac_id) REFERENCES users(id),
    CONSTRAINT fk_cmigs_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
    CONSTRAINT uq_cmigs_cnpj      UNIQUE (cnpj)
);

CREATE INDEX idx_cmigs_owner_ac  ON cmigs(owner_ac_id);
CREATE INDEX idx_cmigs_warehouse ON cmigs(warehouse_id);

CREATE OR REPLACE TRIGGER trg_cmigs_updated_at
    BEFORE UPDATE ON cmigs
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Co-administração de CMIG (M:M AC ↔ CMIG)
CREATE TABLE cmig_administrators (
    id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     NUMBER      NOT NULL,
    cmig_id     NUMBER      NOT NULL,
    is_owner    NUMBER(1)   DEFAULT 0 NOT NULL
                    CONSTRAINT chk_cmigadm_owner CHECK (is_owner IN (0,1)),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_cmigadm_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_cmigadm_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
    CONSTRAINT uq_cmigadm      UNIQUE (user_id, cmig_id)
);

CREATE INDEX idx_cmigadm_user ON cmig_administrators(user_id);
CREATE INDEX idx_cmigadm_cmig ON cmig_administrators(cmig_id);

-- Produtos CMIG (catálogo específico de cada CMIG)
CREATE TABLE cmig_products (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cmig_id         NUMBER          NOT NULL,
    sku_cmig        VARCHAR2(100)   NOT NULL,
    title           VARCHAR2(255)   NOT NULL,
    description     CLOB,
    brand           VARCHAR2(100),
    cost_price      NUMBER(10,2),
    stock_quantity  NUMBER          DEFAULT 0 NOT NULL,
    weight_kg       NUMBER(8,3),
    height_cm       NUMBER(8,2),
    width_cm        NUMBER(8,2),
    length_cm       NUMBER(8,2),
    ncm             VARCHAR2(8),
    cest            VARCHAR2(7),
    origin          NUMBER(1)       DEFAULT 0,
    pg_product_id   NUMBER,         -- FK catalog_products (vínculo de similaridade, nullable)
    is_active       NUMBER(1)       DEFAULT 1 NOT NULL
                        CONSTRAINT chk_cmigprod_active CHECK (is_active IN (0,1)),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_cmigprod_cmig   FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
    CONSTRAINT fk_cmigprod_pg     FOREIGN KEY (pg_product_id) REFERENCES catalog_products(id),
    CONSTRAINT uq_cmigprod_sku    UNIQUE (cmig_id, sku_cmig)
);

CREATE INDEX idx_cmigprod_cmig   ON cmig_products(cmig_id);
CREATE INDEX idx_cmigprod_pg     ON cmig_products(pg_product_id);

CREATE OR REPLACE TRIGGER trg_cmig_products_updated_at
    BEFORE UPDATE ON cmig_products
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- Imagens dos Produtos CMIG
CREATE TABLE cmig_product_images (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cmig_product_id NUMBER      NOT NULL,
    url             VARCHAR2(1000) NOT NULL,
    sort_order      NUMBER      DEFAULT 0 NOT NULL,
    is_primary      NUMBER(1)   DEFAULT 0 NOT NULL
                        CONSTRAINT chk_cmigimg_primary CHECK (is_primary IN (0,1)),
    CONSTRAINT fk_cmigimg_product FOREIGN KEY (cmig_product_id) REFERENCES cmig_products(id) ON DELETE CASCADE
);

CREATE INDEX idx_cmigimg_product ON cmig_product_images(cmig_product_id);

-- Configurações de NF-e por CM (regra por método de envio)
CREATE TABLE nfe_configs (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cm_id           NUMBER          NOT NULL,
    shipping_method VARCHAR2(100)   NOT NULL,
    issuer          VARCHAR2(20)    NOT NULL
                        CONSTRAINT chk_nfecfg_issuer CHECK (issuer IN ('marketplace','system')),
    notes           VARCHAR2(500),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_nfecfg_cm  FOREIGN KEY (cm_id) REFERENCES marketplace_accounts(id) ON DELETE CASCADE,
    CONSTRAINT uq_nfecfg     UNIQUE (cm_id, shipping_method)
);

CREATE INDEX idx_nfecfg_cm ON nfe_configs(cm_id);

CREATE OR REPLACE TRIGGER trg_nfe_configs_updated_at
    BEFORE UPDATE ON nfe_configs
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- ============================================================
-- 2. ALTERAÇÕES EM TABELAS EXISTENTES
-- ============================================================

-- users: adicionar warehouse_id (UGO) e go_id
ALTER TABLE users ADD warehouse_id NUMBER;
ALTER TABLE users ADD go_id        NUMBER;

ALTER TABLE users ADD CONSTRAINT fk_users_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id);
ALTER TABLE users ADD CONSTRAINT fk_users_go
    FOREIGN KEY (go_id) REFERENCES goes(id);

-- users.role: ampliar enum para incluir 'go'
ALTER TABLE users DROP CONSTRAINT chk_users_role;
ALTER TABLE users ADD CONSTRAINT chk_users_role
    CHECK (role IN ('ugo','ac','admin','go'));

CREATE INDEX idx_users_warehouse ON users(warehouse_id);
CREATE INDEX idx_users_go        ON users(go_id);

-- warehouses: adicionar go_id
ALTER TABLE warehouses ADD go_id NUMBER;
ALTER TABLE warehouses ADD CONSTRAINT fk_warehouses_go
    FOREIGN KEY (go_id) REFERENCES goes(id);

CREATE INDEX idx_warehouses_go ON warehouses(go_id);

-- marketplace_accounts (CM): adicionar cmig_id
ALTER TABLE marketplace_accounts ADD cmig_id NUMBER;
ALTER TABLE marketplace_accounts ADD CONSTRAINT fk_ma_cmig
    FOREIGN KEY (cmig_id) REFERENCES cmigs(id);

CREATE INDEX idx_ma_cmig ON marketplace_accounts(cmig_id);

-- product_listings (Anúncios): adicionar cmig_product_id
ALTER TABLE product_listings ADD cmig_product_id NUMBER;
ALTER TABLE product_listings ADD CONSTRAINT fk_pl_cmig_product
    FOREIGN KEY (cmig_product_id) REFERENCES cmig_products(id);

CREATE INDEX idx_pl_cmig_product ON product_listings(cmig_product_id);

-- orders: adicionar cmig_id
ALTER TABLE orders ADD cmig_id NUMBER;
ALTER TABLE orders ADD CONSTRAINT fk_orders_cmig
    FOREIGN KEY (cmig_id) REFERENCES cmigs(id);

CREATE INDEX idx_orders_cmig ON orders(cmig_id);

-- catalog_products (PG): adicionar warehouse_id
ALTER TABLE catalog_products ADD warehouse_id NUMBER;
ALTER TABLE catalog_products ADD CONSTRAINT fk_pg_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id);

CREATE INDEX idx_pg_warehouse ON catalog_products(warehouse_id);

-- ============================================================
-- 3. SEED: Super Administrador
-- ============================================================

-- Super Admin: vinicius@madeingroup.com.br
-- Senha hash = 'admin@123' (bcrypt $2b$12) – TROCAR EM PRODUÇÃO
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM users WHERE email = 'vinicius@madeingroup.com.br';
    IF v_count = 0 THEN
        INSERT INTO users (email, password_hash, role, full_name, is_active)
        VALUES (
            'vinicius@madeingroup.com.br',
            '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
            'admin',
            'Vinicius – Super Administrador',
            1
        );
    END IF;
END;
/

COMMIT;

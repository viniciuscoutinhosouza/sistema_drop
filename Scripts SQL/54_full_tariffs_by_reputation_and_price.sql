-- Migration 54: refatora ml_full_tariffs para refletir o modelo real do ML 2026.
-- A tarifa Full agora depende de 3 fatores: reputação do vendedor, faixa de preço
-- e faixa de peso faturável. Drop+recreate da tabela criada na migration 53.
--
-- Reputação consolidada em 3 tiers:
--   green  = MercadoLíder (platinum/gold/silver) ou level_id 5_green/4_light_green
--   yellow = level_id 3_yellow
--   red    = level_id 2_orange/1_red ou sem reputação
--
-- Faixas de preço (Brasil): < R$ 79, R$ 79–99, R$ 100–199, ≥ R$ 200.
--
-- Valores aproximados publicados por canais especializados (2026). Ajuste manual
-- conforme as tarifas vigentes do seu painel ML — UPDATE direto no banco.

-- 1) Drop da tabela antiga (criada em migration 53)
DECLARE
    e_table_not_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_table_not_exists, -942);
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE ml_full_tariffs CASCADE CONSTRAINTS';
EXCEPTION
    WHEN e_table_not_exists THEN NULL;
END;
/

-- 2) Recria com novo schema
CREATE TABLE ml_full_tariffs (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id         VARCHAR2(5)  DEFAULT 'MLB' NOT NULL,
    reputation_tier VARCHAR2(10) NOT NULL,                  -- green | yellow | red
    weight_min_kg   NUMBER(8,3)  NOT NULL,
    weight_max_kg   NUMBER(8,3)  NOT NULL,
    price_min_brl   NUMBER(10,2) NOT NULL,
    price_max_brl   NUMBER(10,2) NOT NULL,
    tariff_brl      NUMBER(8,2)  NOT NULL,
    notes           VARCHAR2(200),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT chk_full_tier CHECK (reputation_tier IN ('green','yellow','red')),
    CONSTRAINT uq_full_tariff UNIQUE (site_id, reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl)
);
/

CREATE INDEX idx_full_lookup ON ml_full_tariffs(site_id, reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl);
/

-- 3) Seed — 3 tiers × 4 faixas de preço × 8 faixas de peso = 96 linhas
-- Estrutura: green é referência; yellow ≈ +15%; red ≈ +30% (médias observadas no painel)
DECLARE
    TYPE t_tariff_row IS RECORD (
        weight_min   NUMBER, weight_max NUMBER,
        p79_min      NUMBER, p79_max    NUMBER,    -- < 79
        p99_min      NUMBER, p99_max    NUMBER,    -- 79..99
        p199_min     NUMBER, p199_max   NUMBER,    -- 100..199
        p999_min     NUMBER, p999_max   NUMBER,    -- >= 200
        tariff_p79   NUMBER, tariff_p99 NUMBER,
        tariff_p199  NUMBER, tariff_p999 NUMBER
    );
    TYPE t_tariff_table IS TABLE OF t_tariff_row;
    rows t_tariff_table := t_tariff_table();
    v_yellow NUMBER;
    v_red    NUMBER;
BEGIN
    -- Tabela base GREEN (referência) — Brasil 2026, valores aproximados
    -- (peso_min, peso_max, _, _, _, _, _, _, _, _, tarifa<79, tarifa79-99, tarifa100-199, tarifa>=200)
    rows.EXTEND(8);
    rows(1) := t_tariff_row(0,      0.300, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25,  5.95, 11.95, 13.95);
    rows(2) := t_tariff_row(0.301,  0.500, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25,  6.95, 13.95, 15.95);
    rows(3) := t_tariff_row(0.501,  1.000, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25,  7.95, 15.95, 17.95);
    rows(4) := t_tariff_row(1.001,  2.000, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25,  9.95, 18.95, 21.95);
    rows(5) := t_tariff_row(2.001,  5.000, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25, 12.95, 24.95, 27.95);
    rows(6) := t_tariff_row(5.001, 10.000, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25, 17.95, 32.95, 37.95);
    rows(7) := t_tariff_row(10.001,25.000, 0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25, 24.95, 42.95, 49.95);
    rows(8) := t_tariff_row(25.001,999.000,0, 78.99, 79, 99.99, 100, 199.99, 200, 99999, 1.25, 32.95, 54.95, 64.95);

    FOR i IN 1..rows.COUNT LOOP
        -- GREEN
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('green', rows(i).weight_min, rows(i).weight_max, rows(i).p79_min,  rows(i).p79_max,  rows(i).tariff_p79,  'Aproximado MLB 2026');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('green', rows(i).weight_min, rows(i).weight_max, rows(i).p99_min,  rows(i).p99_max,  rows(i).tariff_p99,  'Aproximado MLB 2026');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('green', rows(i).weight_min, rows(i).weight_max, rows(i).p199_min, rows(i).p199_max, rows(i).tariff_p199, 'Aproximado MLB 2026');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('green', rows(i).weight_min, rows(i).weight_max, rows(i).p999_min, rows(i).p999_max, rows(i).tariff_p999, 'Aproximado MLB 2026');

        -- YELLOW (~+15% sobre green; reputação amarela paga mais)
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('yellow', rows(i).weight_min, rows(i).weight_max, rows(i).p79_min,  rows(i).p79_max,  rows(i).tariff_p79,             'Aproximado MLB 2026 (sem desconto reputação)');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('yellow', rows(i).weight_min, rows(i).weight_max, rows(i).p99_min,  rows(i).p99_max,  ROUND(rows(i).tariff_p99 * 1.15, 2),  'Aproximado MLB 2026 (~+15%)');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('yellow', rows(i).weight_min, rows(i).weight_max, rows(i).p199_min, rows(i).p199_max, ROUND(rows(i).tariff_p199 * 1.15, 2), 'Aproximado MLB 2026 (~+15%)');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('yellow', rows(i).weight_min, rows(i).weight_max, rows(i).p999_min, rows(i).p999_max, ROUND(rows(i).tariff_p999 * 1.15, 2), 'Aproximado MLB 2026 (~+15%)');

        -- RED (~+30% sobre green; reputação vermelha penaliza)
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('red', rows(i).weight_min, rows(i).weight_max, rows(i).p79_min,  rows(i).p79_max,  rows(i).tariff_p79,             'Aproximado MLB 2026 (sem desconto reputação)');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('red', rows(i).weight_min, rows(i).weight_max, rows(i).p99_min,  rows(i).p99_max,  ROUND(rows(i).tariff_p99 * 1.30, 2),  'Aproximado MLB 2026 (~+30%)');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('red', rows(i).weight_min, rows(i).weight_max, rows(i).p199_min, rows(i).p199_max, ROUND(rows(i).tariff_p199 * 1.30, 2), 'Aproximado MLB 2026 (~+30%)');
        INSERT INTO ml_full_tariffs(reputation_tier, weight_min_kg, weight_max_kg, price_min_brl, price_max_brl, tariff_brl, notes)
        VALUES ('red', rows(i).weight_min, rows(i).weight_max, rows(i).p999_min, rows(i).p999_max, ROUND(rows(i).tariff_p999 * 1.30, 2), 'Aproximado MLB 2026 (~+30%)');
    END LOOP;
    COMMIT;
END;
/

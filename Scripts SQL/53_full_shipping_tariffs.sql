-- Migration 53: tabela ml_full_tariffs (tarifa Full por faixa de peso faturável)
-- A API ML não expõe a tarifa Full publicamente. Mantemos uma tabela local que
-- pode ser ajustada conforme as tarifas oficiais publicadas pelo ML.
-- Valores iniciais aproximados — Brasil (MLB), 2026. Verifique e ajuste conforme
-- a sua categoria e tabela vigente no painel do vendedor.

DECLARE
    e_table_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_table_exists, -955);
BEGIN
    EXECUTE IMMEDIATE q'[
        CREATE TABLE ml_full_tariffs (
            id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            site_id         VARCHAR2(5)  DEFAULT 'MLB' NOT NULL,
            weight_min_kg   NUMBER(8,3)  NOT NULL,
            weight_max_kg   NUMBER(8,3)  NOT NULL,
            tariff_brl      NUMBER(8,2)  NOT NULL,
            notes           VARCHAR2(200),
            updated_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT uq_ml_full_tariff_range UNIQUE (site_id, weight_min_kg, weight_max_kg)
        )
    ]';
EXCEPTION
    WHEN e_table_exists THEN NULL;
END;
/

-- Seed (apenas se a tabela estiver vazia, para não sobrescrever ajustes do usuário)
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM ml_full_tariffs WHERE site_id = 'MLB';
    IF v_count = 0 THEN
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB', 0,      0.300,   8.90, 'Aproximado — ajustar conforme tabela Full oficial');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB', 0.301,  0.500,   9.50, 'Aproximado');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB', 0.501,  1.000,  11.90, 'Aproximado');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB', 1.001,  2.000,  14.90, 'Aproximado');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB', 2.001,  5.000,  19.90, 'Aproximado');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB', 5.001, 10.000,  26.90, 'Aproximado');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB',10.001, 25.000,  35.90, 'Aproximado');
        INSERT INTO ml_full_tariffs (site_id, weight_min_kg, weight_max_kg, tariff_brl, notes) VALUES ('MLB',25.001, 999.000, 49.90, 'Aproximado — peso > 25kg');
        COMMIT;
    END IF;
END;
/

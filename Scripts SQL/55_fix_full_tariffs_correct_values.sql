-- Migration 55: substitui todos os dados de ml_full_tariffs pelos valores oficiais do ML 2026.
-- Fonte: tabela de custos de envio publicada no painel do Mercado Livre (maio/2026).
-- Válido para Envios Full, Coleta e Agências ML — MercadoLíder/reputação verde.
--
-- Estrutura:
--   green  = MercadoLíder/reputação verde — valores da tabela oficial (já incluem 50% desconto)
--   yellow = aproximação: green × 1.5  (desconto ~25% — sem fonte oficial para esta faixa)
--   red    = green × 2.0               (sem desconto de reputação — tabela cheia)
--
-- Faixas de preço (8 colunas, Brasil):
--   P1: R$ 0–18,99   P2: R$ 19–48,99  P3: R$ 49–78,99  P4: R$ 79–99,99
--   P5: R$ 100–119,99  P6: R$ 120–149,99  P7: R$ 150–199,99  P8: R$ 200+
--
-- Faixas de peso faturável (30 linhas, conforme tabela ML).
-- A tabela local é usada apenas como FALLBACK quando a API /shipping_options/free
-- não retornar valor (timeout, indisponibilidade, dimensões ausentes).
-- Fonte primária de cálculo de frete: GET /users/{id}/shipping_options/free.

DELETE FROM ml_full_tariffs WHERE site_id = 'MLB';
/
COMMIT;
/

DECLARE
    -- Estrutura: weight_min, weight_max, p1..p8 (preços R$ para green)
    TYPE t_row IS RECORD (
        wmin NUMBER, wmax NUMBER,
        p1 NUMBER, p2 NUMBER, p3 NUMBER, p4 NUMBER,
        p5 NUMBER, p6 NUMBER, p7 NUMBER, p8 NUMBER
    );
    TYPE t_rows IS TABLE OF t_row;
    v   t_rows := t_rows();
    yf  NUMBER;   -- yellow factor (×1.5)
    rf  NUMBER;   -- red factor    (×2.0)
BEGIN
    yf := 1.5; rf := 2.0;

    -- 30 faixas de peso (min_kg, max_kg, p1..p8)
    v.EXTEND(30);
    -- Até 0,3 kg
    v(1)  := t_row(0,       0.300,  5.65,  6.55,  7.75, 12.35, 14.35, 16.45, 18.45, 20.95);
    -- De 0,3 a 0,5 kg
    v(2)  := t_row(0.301,   0.500,  5.95,  6.65,  7.85, 13.25, 15.45, 17.65, 19.85, 22.55);
    -- De 0,5 a 1 kg
    v(3)  := t_row(0.501,   1.000,  6.05,  6.75,  7.95, 13.85, 16.15, 18.45, 20.75, 23.65);
    -- De 1 a 1,5 kg
    v(4)  := t_row(1.001,   1.500,  6.15,  6.85,  8.05, 14.15, 16.45, 18.85, 21.15, 24.65);
    -- De 1,5 a 2 kg
    v(5)  := t_row(1.501,   2.000,  6.25,  6.95,  8.15, 14.45, 16.85, 19.25, 21.65, 24.65);
    -- De 2 a 3 kg
    v(6)  := t_row(2.001,   3.000,  6.35,  7.95,  8.55, 15.75, 18.35, 21.05, 23.65, 26.25);
    -- De 3 a 4 kg
    v(7)  := t_row(3.001,   4.000,  6.45,  8.15,  8.95, 17.05, 19.85, 22.65, 25.55, 28.35);
    -- De 4 a 5 kg
    v(8)  := t_row(4.001,   5.000,  6.55,  8.35,  9.75, 18.45, 21.55, 24.65, 27.75, 30.75);
    -- De 5 a 6 kg
    v(9)  := t_row(5.001,   6.000,  6.65,  8.55,  9.95, 25.45, 28.55, 32.65, 35.75, 39.75);
    -- De 6 a 7 kg
    v(10) := t_row(6.001,   7.000,  6.75,  8.75, 10.15, 27.05, 31.05, 36.05, 40.05, 44.05);
    -- De 7 a 8 kg
    v(11) := t_row(7.001,   8.000,  6.85,  8.95, 10.35, 28.85, 33.65, 38.45, 43.25, 48.05);
    -- De 8 a 9 kg
    v(12) := t_row(8.001,   9.000,  6.95,  9.15, 10.55, 29.65, 34.55, 39.55, 44.45, 49.35);
    -- De 9 a 11 kg
    v(13) := t_row(9.001,  11.000,  7.05,  9.55, 10.95, 41.25, 48.05, 54.95, 61.75, 68.65);
    -- De 11 a 13 kg
    v(14) := t_row(11.001, 13.000,  7.15,  9.95, 11.35, 42.15, 49.25, 56.25, 63.25, 70.25);
    -- De 13 a 15 kg
    v(15) := t_row(13.001, 15.000,  7.25, 10.15, 11.55, 45.05, 52.45, 59.95, 67.45, 74.95);
    -- De 15 a 17 kg
    v(16) := t_row(15.001, 17.000,  7.35, 10.35, 11.75, 48.55, 56.05, 63.55, 70.75, 78.65);
    -- De 17 a 20 kg
    v(17) := t_row(17.001, 20.000,  7.45, 10.55, 11.95, 54.75, 63.85, 72.95, 82.05, 91.15);
    -- De 20 a 25 kg
    v(18) := t_row(20.001, 25.000,  7.65, 10.95, 12.15, 64.05, 75.05, 84.75, 95.35,105.95);
    -- De 25 a 30 kg
    v(19) := t_row(25.001, 30.000,  7.75, 11.15, 12.35, 65.95, 75.45, 85.55, 96.25,106.95);
    -- De 30 a 40 kg
    v(20) := t_row(30.001, 40.000,  7.85, 11.35, 12.55, 67.75, 78.95, 88.95, 99.15,107.05);
    -- De 40 a 50 kg
    v(21) := t_row(40.001, 50.000,  7.95, 11.55, 12.75, 70.25, 81.05, 92.05,102.55,110.75);
    -- De 50 a 60 kg
    v(22) := t_row(50.001, 60.000,  8.05, 11.75, 12.95, 74.95, 86.45, 98.15,109.35,118.15);
    -- De 60 a 70 kg
    v(23) := t_row(60.001, 70.000,  8.15, 11.95, 13.15, 80.25, 92.95,105.05,117.15,126.55);
    -- De 70 a 80 kg
    v(24) := t_row(70.001, 80.000,  8.25, 12.15, 13.35, 83.95, 97.05,109.85,122.45,132.25);
    -- De 80 a 90 kg
    v(25) := t_row(80.001, 90.000,  8.35, 12.35, 13.55, 93.25,107.45,122.05,136.05,146.95);
    -- De 90 a 100 kg
    v(26) := t_row(90.001,100.000,  8.45, 12.55, 13.75,106.55,123.95,139.55,155.55,167.95);
    -- De 100 a 125 kg
    v(27) := t_row(100.001,125.000, 8.55, 12.75, 13.95,119.25,138.05,156.05,173.95,187.95);
    -- De 125 a 150 kg
    v(28) := t_row(125.001,150.000, 8.65, 12.75, 14.15,126.55,146.15,165.65,184.65,199.45);
    -- Mais de 150 kg
    v(29) := t_row(150.001,300.000, 8.75, 12.95, 14.35,166.15,192.45,217.55,242.55,261.95);
    -- Acima de 300 kg (faixa extra de segurança — mantém o mesmo valor de >150kg)
    v(30) := t_row(300.001,9999.00, 8.75, 12.95, 14.35,166.15,192.45,217.55,242.55,261.95);

    FOR i IN 1..v.COUNT LOOP
        -- 8 faixas de preço: P1..P8
        -- GREEN (valores da tabela oficial — já incluem 50% desconto)
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax,   0,   18.99,v(i).p1,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax,  19,   48.99,v(i).p2,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax,  49,   78.99,v(i).p3,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax,  79,   99.99,v(i).p4,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax, 100,  119.99,v(i).p5,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax, 120,  149.99,v(i).p6,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax, 150,  199.99,v(i).p7,'ML oficial mai/2026');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','green',v(i).wmin,v(i).wmax, 200, 99999.0,v(i).p8,'ML oficial mai/2026');

        -- YELLOW (~25% desconto = green × 1.5)
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax,   0,   18.99,ROUND(v(i).p1*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax,  19,   48.99,ROUND(v(i).p2*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax,  49,   78.99,ROUND(v(i).p3*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax,  79,   99.99,ROUND(v(i).p4*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax, 100,  119.99,ROUND(v(i).p5*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax, 120,  149.99,ROUND(v(i).p6*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax, 150,  199.99,ROUND(v(i).p7*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','yellow',v(i).wmin,v(i).wmax, 200, 99999.0,ROUND(v(i).p8*yf,2),'ML aprox. yellow mai/2026 (~25% desc.)');

        -- RED (sem desconto = green × 2.0 — tabela cheia)
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax,   0,   18.99,ROUND(v(i).p1*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax,  19,   48.99,ROUND(v(i).p2*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax,  49,   78.99,ROUND(v(i).p3*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax,  79,   99.99,ROUND(v(i).p4*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax, 100,  119.99,ROUND(v(i).p5*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax, 120,  149.99,ROUND(v(i).p6*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax, 150,  199.99,ROUND(v(i).p7*rf,2),'ML aprox. red mai/2026 (sem desconto)');
        INSERT INTO ml_full_tariffs(site_id,reputation_tier,weight_min_kg,weight_max_kg,price_min_brl,price_max_brl,tariff_brl,notes)
        VALUES('MLB','red',v(i).wmin,v(i).wmax, 200, 99999.0,ROUND(v(i).p8*rf,2),'ML aprox. red mai/2026 (sem desconto)');
    END LOOP;
    COMMIT;
END;
/


COMMIT;


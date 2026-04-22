-- ============================================================
-- MIG ECOMMERCE – Script 17: goes recebe warehouse_id
-- goes = pessoa física dona do galpão
-- Campos de empresa/endereço/PIX ficam SOMENTE em warehouses
-- ============================================================

-- Referência ao warehouse principal do GO (auto-criado no cadastro)
ALTER TABLE goes ADD warehouse_id NUMBER;
ALTER TABLE goes ADD CONSTRAINT fk_goes_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id);

-- ============================================================
-- MIG ECOMMERCE – Script 18: Remove campos de empresa de GOES
-- goes = pessoa física dona do galpão (sem CNPJ/endereço/PIX)
-- warehouses = empresa jurídica com todos os dados fiscais
-- Execute SOMENTE se o script 17 já foi executado no banco.
-- ============================================================

ALTER TABLE goes DROP COLUMN cnpj;
ALTER TABLE goes DROP COLUMN company_name;
ALTER TABLE goes DROP COLUMN trade_name;
ALTER TABLE goes DROP COLUMN phone;
ALTER TABLE goes DROP COLUMN email;
ALTER TABLE goes DROP COLUMN whatsapp;
ALTER TABLE goes DROP COLUMN zip_code;
ALTER TABLE goes DROP COLUMN street;
ALTER TABLE goes DROP COLUMN number;
ALTER TABLE goes DROP COLUMN complement;
ALTER TABLE goes DROP COLUMN neighborhood;
ALTER TABLE goes DROP COLUMN city;
ALTER TABLE goes DROP COLUMN state;
ALTER TABLE goes DROP COLUMN pix_key_type;
ALTER TABLE goes DROP COLUMN pix_key;
ALTER TABLE goes DROP COLUMN notes;

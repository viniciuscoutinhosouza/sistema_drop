-- Migration 42: Tabela `invoice_items` — itens da NFe
-- Idempotente.
-- NOTA: usamos `item_number` (não `sequence`) — SEQUENCE é palavra reservada Oracle.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE invoice_items (
      id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      invoice_id          NUMBER NOT NULL,
      item_number         NUMBER NOT NULL,
      cmig_product_id     NUMBER,
      cfop                VARCHAR2(4),
      ncm                 VARCHAR2(8),
      cest                VARCHAR2(7),
      description         VARCHAR2(500) NOT NULL,
      ean                 VARCHAR2(14),
      unit                VARCHAR2(6) DEFAULT 'UN',
      quantity            NUMBER(15,4) DEFAULT 1,
      unit_value          NUMBER(15,4) DEFAULT 0,
      total_value         NUMBER(15,2) DEFAULT 0,
      discount            NUMBER(15,2) DEFAULT 0,
      freight_value       NUMBER(15,2) DEFAULT 0,
      insurance_value     NUMBER(15,2) DEFAULT 0,
      other_value         NUMBER(15,2) DEFAULT 0,
      origin              NUMBER(1) DEFAULT 0,
      icms_cst            VARCHAR2(3),
      icms_csosn          VARCHAR2(3),
      icms_base           NUMBER(15,2) DEFAULT 0,
      icms_aliquota       NUMBER(8,4) DEFAULT 0,
      icms_value          NUMBER(15,2) DEFAULT 0,
      icms_st_base        NUMBER(15,2) DEFAULT 0,
      icms_st_aliquota    NUMBER(8,4) DEFAULT 0,
      icms_st_value       NUMBER(15,2) DEFAULT 0,
      ipi_cst             VARCHAR2(2),
      ipi_aliquota        NUMBER(8,4) DEFAULT 0,
      ipi_value           NUMBER(15,2) DEFAULT 0,
      pis_cst             VARCHAR2(2),
      pis_aliquota        NUMBER(8,4) DEFAULT 0,
      pis_value           NUMBER(15,2) DEFAULT 0,
      cofins_cst          VARCHAR2(2),
      cofins_aliquota     NUMBER(8,4) DEFAULT 0,
      cofins_value        NUMBER(15,2) DEFAULT 0,
      inbound_item_id     NUMBER,
      additional_info     VARCHAR2(2000),
      CONSTRAINT fk_invitem_inv FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
      CONSTRAINT fk_invitem_cmig_prod FOREIGN KEY (cmig_product_id) REFERENCES cmig_products(id) ON DELETE SET NULL,
      CONSTRAINT fk_invitem_inbound FOREIGN KEY (inbound_item_id) REFERENCES invoice_items(id) ON DELETE SET NULL
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_invitem_invoice ON invoice_items(invoice_id, item_number)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_invitem_cmig_prod ON invoice_items(cmig_product_id)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

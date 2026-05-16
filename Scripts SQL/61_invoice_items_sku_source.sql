-- Migration 61: Adiciona `sku` e `source_type` em `invoice_items`
-- Permite que o card de itens da NFe mostre o SKU do produto e a origem
-- (estoque CMIG vs estoque PG vs item manual sem vínculo).
-- Idempotente.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);  -- ORA-01430: column being added already exists
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE invoice_items ADD sku VARCHAR2(50)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -01430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE invoice_items ADD source_type VARCHAR2(10)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Constraint para garantir valores válidos em source_type (NULL permitido para itens legados).
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'CHK_INVITEM_SOURCE_TYPE'
     AND table_name = 'INVOICE_ITEMS';
  IF v_count = 0 THEN
    EXECUTE IMMEDIATE q'[
      ALTER TABLE invoice_items
      ADD CONSTRAINT chk_invitem_source_type
      CHECK (source_type IS NULL OR source_type IN ('cmig','pg','manual'))
    ]';
  END IF;
END;
/

-- Backfill: itens com cmig_product_id setado mas source_type NULL = origem CMIG.
UPDATE invoice_items
   SET source_type = 'cmig'
 WHERE cmig_product_id IS NOT NULL
   AND source_type IS NULL;

COMMIT;

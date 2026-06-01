-- 76_full_stock.sql
-- Saldo de estoque no centro de fulfillment do ML, por (produto × conta de marketplace).
-- Executar após 75_full_cnpjs.sql.

DECLARE
  e_tab_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_tab_exists, -955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE full_stock (
      id                     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      product_type           VARCHAR2(10)  NOT NULL,
      product_id             NUMBER        NOT NULL,
      marketplace_account_id NUMBER        NOT NULL REFERENCES marketplace_accounts(id),
      qty                    NUMBER        DEFAULT 0 NOT NULL,
      updated_at             TIMESTAMP     DEFAULT SYSTIMESTAMP
    )
  ';
EXCEPTION WHEN e_tab_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uix_full_stock_product ON full_stock(product_type, product_id, marketplace_account_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_full_stock_account ON full_stock(marketplace_account_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

-- Verificação
SELECT COUNT(*) AS total_full_stock_rows FROM full_stock;

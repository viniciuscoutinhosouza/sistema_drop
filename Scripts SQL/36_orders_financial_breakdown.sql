-- 36_orders_financial_breakdown.sql
-- Adiciona colunas para detalhamento financeiro do pedido:
--   buyer_shipping_paid  — frete que o comprador pagou (shipping_option.cost)
--   seller_shipping_cost — frete deduzido do vendedor (list_cost - cost)
--   ml_fee_pct           — percentual da tarifa ML sobre a venda
-- Idempotente: ignora ORA-01430 quando a coluna já existe.

DECLARE
    e_col_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
    BEGIN
        EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (buyer_shipping_paid NUMBER(15,2))';
    EXCEPTION
        WHEN e_col_exists THEN NULL;
    END;
    BEGIN
        EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (seller_shipping_cost NUMBER(15,2))';
    EXCEPTION
        WHEN e_col_exists THEN NULL;
    END;
    BEGIN
        EXECUTE IMMEDIATE 'ALTER TABLE orders ADD (ml_fee_pct NUMBER(8,4))';
    EXCEPTION
        WHEN e_col_exists THEN NULL;
    END;
END;
/
COMMIT;

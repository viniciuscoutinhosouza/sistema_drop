-- 71_stock_movements.sql
-- Cria tabela de trilha de movimentação de estoque em tempo real.
-- Cada linha representa uma entrada ou saída em um campo de estoque específico,
-- gerada automaticamente pelo sistema (webhook, cancelamento, devolução) ou manualmente.
--
-- movement_type values:
--   reserve        : pedido baixado → reserved_quantity += qty
--   unreserve      : pedido cancelado antes do despacho → reserved_quantity -= qty
--   dispatch       : pedido despachado → stock_quantity -= qty; reserved_quantity -= qty
--   await_return   : pedido cancelado após despacho → awaiting_return_quantity += qty
--   confirm_return : retorno físico confirmado → awaiting_return_quantity -= qty; stock_quantity += qty
--   receive_return : devolução de cliente recebida → pending_validation_quantity += qty
--   validate_ok    : devolução validada OK → pending_validation_quantity -= qty; stock_quantity += qty
--   validate_unfit : devolução reprovada → pending_validation_quantity -= qty; unfit_quantity += qty
--   manual         : ajuste manual de operador

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE stock_movements (
      id               NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      product_type     VARCHAR2(20)  NOT NULL,
      product_id       NUMBER        NOT NULL,
      order_id         NUMBER,
      return_id        NUMBER,
      movement_type    VARCHAR2(40)  NOT NULL,
      qty              NUMBER        NOT NULL,
      field_affected   VARCHAR2(50)  NOT NULL,
      delta            NUMBER        NOT NULL,
      created_by       NUMBER,
      created_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT fk_smov_order  FOREIGN KEY (order_id)  REFERENCES orders(id),
      CONSTRAINT fk_smov_return FOREIGN KEY (return_id) REFERENCES returns(id),
      CONSTRAINT fk_smov_user   FOREIGN KEY (created_by) REFERENCES users(id)
    )
  ';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

-- Índices para consultas por produto e por pedido/devolução
DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -01408);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_smov_product ON stock_movements(product_type, product_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -01408);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_smov_order ON stock_movements(order_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -01408);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX ix_smov_return ON stock_movements(return_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

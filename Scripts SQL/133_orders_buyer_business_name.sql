-- 133_orders_buyer_business_name.sql
-- Razão social do comprador PJ (CNPJ): guardar o nome fiscal para o eShip.
--
-- Contexto: ao enviar a ordem ao WMS (eShip webServicePostOrdem) com destinatário CNPJ ainda
-- não cadastrado, o eShip recusa com MCA9102 ("Como não existe cadastro para o CNPJ ... o campo
-- razaoSocialDestinatario não pode ser vazio"). A razão social vem de
-- GET /orders/{id}/billing_info (x-version: 2) em `buyer.billing_info.name` (o nome fiscal do PJ).
-- Guardamos aqui, junto com o documento (ver 127), para preencher `razaoSocialDestinatario`.
--
-- Idempotente: EXCEPTION WHEN e_col_exists (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);   -- ORA-01430: column already exists

  PROCEDURE add_col(p_sql VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE orders ADD (buyer_business_name VARCHAR2(255))');   -- razão social (PJ)
  COMMIT;
END;
/

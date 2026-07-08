-- 123_orders_unique_platform_order.sql
-- Impede pedidos DUPLICADOS por corrida na sincronização (webhook + job sync_orders
-- inserindo o mesmo pedido ao mesmo tempo, sem trava no banco).
--
-- Cria índice ÚNICO em orders(platform, platform_order_id, dropshipper_id). Pedidos
-- manuais (platform_order_id NULL) NÃO entram na unicidade — no Oracle, linhas com
-- qualquer coluna do índice composto NULL não são consideradas duplicadas.
--
-- Idempotente. Faz um dedup DEFENSIVO antes (mantém o menor id) — em produção a limpeza
-- já foi feita pela aplicação com recompute de estoque; aqui é rede de segurança para
-- outros ambientes / re-execução.

DECLARE
  e_exists  EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_exists, -955);    -- ORA-00955: name already used
  e_dup_idx EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_dup_idx, -1408);  -- ORA-01408: such column list already indexed
BEGIN
  -- 1) movimentos das linhas duplicadas (FK sem ON DELETE CASCADE) — mantém o menor id
  DELETE FROM stock_movements WHERE order_id IN (
    SELECT o.id FROM orders o
     WHERE o.platform_order_id IS NOT NULL
       AND o.id > (SELECT MIN(o2.id) FROM orders o2
                    WHERE o2.platform          = o.platform
                      AND o2.platform_order_id = o.platform_order_id
                      AND o2.dropshipper_id    = o.dropshipper_id)
  );

  -- 2) linhas duplicadas (order_items caem por ON DELETE CASCADE)
  DELETE FROM orders o
   WHERE o.platform_order_id IS NOT NULL
     AND o.id > (SELECT MIN(o2.id) FROM orders o2
                  WHERE o2.platform          = o.platform
                    AND o2.platform_order_id = o.platform_order_id
                    AND o2.dropshipper_id    = o.dropshipper_id);

  -- 3) índice único (a defesa definitiva contra a corrida)
  BEGIN
    EXECUTE IMMEDIATE
      'CREATE UNIQUE INDEX ux_orders_plat_poid_drop '
      || 'ON orders(platform, platform_order_id, dropshipper_id)';
  EXCEPTION
    WHEN e_exists  THEN NULL;
    WHEN e_dup_idx THEN NULL;
  END;

  COMMIT;
END;
/

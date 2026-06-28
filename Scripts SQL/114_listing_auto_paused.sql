-- 114_listing_auto_paused.sql — pausa/reativação automática de anúncios por estoque (ADR-0014)
--
-- auto_paused = 1 quando o SISTEMA pausou o anúncio porque o disponível (LOCAL+FULL) zerou.
-- O sync_stock só reativa anúncios com auto_paused=1; nunca reativa um anúncio pausado
-- manualmente pelo dono (auto_paused=0). Isso também evita brigar com o status que o job
-- horário de metadados (sync_listings_from_ml) traz do ML.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE product_listings ADD auto_paused NUMBER(1) DEFAULT 0 NOT NULL';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

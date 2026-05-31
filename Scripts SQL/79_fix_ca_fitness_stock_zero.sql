-- Migration 79: zera estoque dos anuncios da CA FITNESS importados com bug "or 1"
--
-- Contexto: antes do fix em routers/anuncios.py:1014, importacao usava
--   available_qty = item.get("available_quantity") or item.get("initial_quantity") or 1
-- O operador `or` do Python avalia 0 como falsy, entao anuncios sem estoque
-- (available_quantity=0) viravam 1 no DB local.
--
-- A conta CA FITNESS (account_id=61, seller_id=29382874) tem 555 anuncios todos
-- com status=under_review + sub_status=suspended_for_prevention, todos com
-- estoque 0 no ML. Importados via bug, ficaram com 1 no DB local.
--
-- Filtro defensivo: zera APENAS os com available_quantity=1, preservando
-- valores 2+ caso algum tenha estoque real ou tenha sido editado manualmente.

UPDATE product_listings
SET available_quantity = 0,
    qty_local = 0
WHERE account_id = 61;

COMMIT;

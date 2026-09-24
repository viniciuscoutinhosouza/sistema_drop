-- Migration 141: logo e tema de cor por Galpão (branding por warehouse).
--
-- Permite ao Galpão ter identidade visual própria: um LOGO (canto superior esquerdo, acima do menu)
-- e até 5 cores de tema que o sistema aplica para os usuários daquele galpão.
--   logo_url          → caminho do arquivo enviado (/static/uploads/warehouse-logos/<uuid>.<ext>)
--   theme_sidebar     → fundo da barra lateral
--   theme_accent      → item ativo / destaque
--   theme_topbar      → barra superior (navbar)
--   theme_sidebar_text→ texto/ícones da barra lateral
--   theme_link        → links e realces
-- Cores no formato hex #RRGGBB (7 chars). Todas NULL = tema padrão MIG.
--
-- Idempotente: cada ADD é isolado e ORA-01430 (coluna já existe) é ignorado.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_ddl VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_ddl;
  EXCEPTION
    WHEN e_col_exists THEN NULL;
  END;
BEGIN
  add_col('ALTER TABLE warehouses ADD (logo_url VARCHAR2(500))');
  add_col('ALTER TABLE warehouses ADD (theme_sidebar VARCHAR2(7))');
  add_col('ALTER TABLE warehouses ADD (theme_accent VARCHAR2(7))');
  add_col('ALTER TABLE warehouses ADD (theme_topbar VARCHAR2(7))');
  add_col('ALTER TABLE warehouses ADD (theme_sidebar_text VARCHAR2(7))');
  add_col('ALTER TABLE warehouses ADD (theme_link VARCHAR2(7))');
END;
/

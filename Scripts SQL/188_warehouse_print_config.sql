-- Migration 188: Config de IMPRESSÃO por galpão (Separação / Carrinho Gaiola, modo Bipagem automática).
-- Impressora da etiqueta + da DANFE (nomes como o QZ Tray enxerga no PC de despacho — DEFAULT do galpão,
-- com override por-máquina no front via localStorage), formato/tamanho da etiqueta e auto-ações ao concluir
-- a bipagem (imprimir etiqueta / DANFE / tirar foto). Idempotente.

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE warehouses ADD print_label_printer VARCHAR2(200)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE warehouses ADD print_danfe_printer VARCHAR2(200)';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Formato da etiqueta: 'pdf' | 'zpl'
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE warehouses ADD print_label_format VARCHAR2(10) DEFAULT 'pdf']';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Tamanho do PDF da etiqueta (quando formato=pdf): 'a4' | '10x15'
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE q'[ALTER TABLE warehouses ADD print_label_pdf_size VARCHAR2(10) DEFAULT '10x15']';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

-- Auto-ações ao concluir a bipagem de um pedido (0/1)
DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE warehouses ADD print_auto_label NUMBER(1) DEFAULT 0';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE warehouses ADD print_auto_danfe NUMBER(1) DEFAULT 0';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE warehouses ADD print_auto_photo NUMBER(1) DEFAULT 0';
EXCEPTION WHEN e_col_exists THEN NULL;
END;
/

COMMIT;

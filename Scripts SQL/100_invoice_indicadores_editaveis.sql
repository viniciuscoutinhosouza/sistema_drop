-- Migration 100: Indicadores da NF-e persistidos (antes eram constantes/derivados na emissão)
-- Parte do refactor "todos os campos da NF-e visíveis + editáveis no rascunho" (matriz por campo).
--
-- Antes, o `sefaz_service.build_nota_emissao` cravava esses indicadores no código
-- (ind_presenca=9, ind_intermed=0, ind_pag=0). Passam a ser colunas EDITÁVEIS no rascunho;
-- NULL = usa o default histórico na emissão (não altera notas já emitidas).
-- Idempotente via EXCEPTION WHEN e_col_exists (ORA-01430).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);

  PROCEDURE add_col(p_col VARCHAR2, p_def VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE invoices ADD (' || p_col || ' ' || p_def || ')';
  EXCEPTION WHEN e_col_exists THEN NULL;
  END;
BEGIN
  -- indPresença: 0 não se aplica; 1 presencial; 2 internet; 9 não presencial/outros (default).
  add_col('ind_presenca',   'NUMBER(1)');
  -- indIntermediador: 0 sem intermediador (default); 1 operação em site/plataforma de terceiro (marketplace).
  add_col('ind_intermed',   'NUMBER(1)');
  -- indPag do detPag: 0 à vista (default); 1 a prazo. (tPag e vPag continuam em payment_method/derivado.)
  add_col('ind_pag',        'NUMBER(1)');
  DBMS_OUTPUT.PUT_LINE('Colunas de indicadores editaveis adicionadas a invoices.');
END;
/

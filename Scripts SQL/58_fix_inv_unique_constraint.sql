-- Migration 58: Corrige constraint uq_inv_serie_number para permitir multiplos rascunhos
-- O constraint anterior bloqueava criar mais de uma NF-e em rascunho por CMIG+model
-- porque Oracle trata (cmig_id=1, model='55', NULL, NULL) como duplicata.
-- Solução: substituir por índice único funcional que só atua quando serie e nfe_number não são NULL.

DECLARE
  v_count NUMBER;
BEGIN
  -- Remove constraint original (se existir)
  SELECT COUNT(*) INTO v_count
    FROM user_constraints
   WHERE constraint_name = 'UQ_INV_SERIE_NUMBER'
     AND table_name = 'INVOICES';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'ALTER TABLE invoices DROP CONSTRAINT uq_inv_serie_number';
  END IF;

  -- Remove índice funcional se já existir (idempotente)
  SELECT COUNT(*) INTO v_count
    FROM user_indexes
   WHERE index_name = 'UQ_INV_SERIE_NUMBER'
     AND table_name = 'INVOICES';
  IF v_count > 0 THEN
    EXECUTE IMMEDIATE 'DROP INDEX uq_inv_serie_number';
  END IF;
END;
/

-- Cria índice único funcional: só aplica unicidade quando serie e nfe_number são preenchidos.
-- Linhas com serie NULL ou nfe_number NULL geram NULL no índice => não são comparadas.
CREATE UNIQUE INDEX uq_inv_serie_number ON invoices (
    CASE WHEN serie IS NOT NULL AND nfe_number IS NOT NULL THEN cmig_id  END,
    CASE WHEN serie IS NOT NULL AND nfe_number IS NOT NULL THEN model    END,
    CASE WHEN serie IS NOT NULL AND nfe_number IS NOT NULL THEN serie    END,
    CASE WHEN serie IS NOT NULL AND nfe_number IS NOT NULL THEN nfe_number END
);

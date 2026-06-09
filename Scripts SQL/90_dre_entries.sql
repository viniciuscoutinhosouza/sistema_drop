-- Migration 90: Tabela `dre_entries` — lançamentos manuais da DRE por CMIG.
-- Tipos: 'entrada' | 'custo_operacional' | 'custo_fixo'.
-- Recorrência: ao cadastrar N parcelas a partir de (ano,mês), o backend gera N linhas
-- (uma por mês) compartilhando o mesmo recurrence_group_id.
-- Idempotente.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE dre_entries (
      id                   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cmig_id              NUMBER NOT NULL,
      created_by           NUMBER,
      category_kind        VARCHAR2(20) NOT NULL
                              CONSTRAINT chk_dree_kind CHECK (category_kind IN ('entrada','custo_operacional','custo_fixo')),
      description          VARCHAR2(500),
      category             VARCHAR2(100),
      amount               NUMBER(15,2) NOT NULL,
      ref_year             NUMBER(4) NOT NULL,
      ref_month            NUMBER(2) NOT NULL
                              CONSTRAINT chk_dree_month CHECK (ref_month BETWEEN 1 AND 12),
      recurrence_group_id  VARCHAR2(40),
      installment_no       NUMBER(4),
      total_installments   NUMBER(4),
      created_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      updated_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_dree_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
      CONSTRAINT fk_dree_user FOREIGN KEY (created_by) REFERENCES users(id)
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_dree_cmig_period ON dre_entries (cmig_id, ref_year, ref_month)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

COMMIT;

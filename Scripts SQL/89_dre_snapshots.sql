-- Migration 89: Tabela `dre_snapshots` — cache mensal sincronizado da DRE por CMIG.
-- Cada linha = valores do Mercado Livre (operacional + billing + ADS) de um (cmig, ano, mês).
-- Recalculado sob demanda pelo botão de sincronização do mês na tela Gestão Financeira.
-- Idempotente.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE dre_snapshots (
      id                   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cmig_id              NUMBER NOT NULL,
      ref_year             NUMBER(4) NOT NULL,
      ref_month            NUMBER(2) NOT NULL
                              CONSTRAINT chk_dres_month CHECK (ref_month BETWEEN 1 AND 12),
      faturamento          NUMBER(15,2) DEFAULT 0,
      vendas_canceladas    NUMBER(15,2) DEFAULT 0,
      tarifa_venda         NUMBER(15,2) DEFAULT 0,
      devolucao_parcial    NUMBER(15,2) DEFAULT 0,
      custo_produtos       NUMBER(15,2) DEFAULT 0,
      frete_vendedor       NUMBER(15,2) DEFAULT 0,
      gasto_ads            NUMBER(15,2) DEFAULT 0,
      source               VARCHAR2(20) DEFAULT 'operational'
                              CONSTRAINT chk_dres_source CHECK (source IN ('operational','billing','reconciled')),
      billing_json         CLOB,
      last_synced_at       TIMESTAMP WITH TIME ZONE,
      created_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      updated_at           TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_dres_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
      CONSTRAINT uq_dres_cmig_period UNIQUE (cmig_id, ref_year, ref_month)
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

COMMIT;

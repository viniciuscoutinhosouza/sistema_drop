-- Migration 41: Tabela `invoices` — NFes emitidas (saída) e recebidas (entrada)
-- Idempotente.
-- NOTA: usamos `nfe_number` (não `number`) e demais nomes seguros porque algumas
-- palavras como NUMBER, SEQUENCE, ORDER são reservadas no Oracle.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE invoices (
      id                          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cmig_id                     NUMBER NOT NULL,
      direction                   VARCHAR2(3) NOT NULL
                                      CONSTRAINT chk_inv_direction CHECK (direction IN ('out','in')),
      purpose                     VARCHAR2(20) DEFAULT 'venda'
                                      CONSTRAINT chk_inv_purpose CHECK (
                                          purpose IN ('venda','devolucao','remessa','retorno',
                                                       'transferencia','complementar','ajuste','outros')),
      model                       VARCHAR2(2) DEFAULT '55',
      serie                       NUMBER,
      nfe_number                  NUMBER,
      access_key                  VARCHAR2(50),
      person_id                   NUMBER,
      order_id                    NUMBER,
      inbound_invoice_id          NUMBER,
      natureza_operacao           VARCHAR2(255),
      issue_date                  TIMESTAMP WITH TIME ZONE,
      exit_date                   TIMESTAMP WITH TIME ZONE,
      status                      VARCHAR2(20) DEFAULT 'draft'
                                      CONSTRAINT chk_inv_status CHECK (
                                          status IN ('draft','queued','processing','authorized',
                                                      'rejected','cancelled','denied')),
      inbound_source              VARCHAR2(20)
                                      CONSTRAINT chk_inv_inbound_source CHECK (
                                          inbound_source IS NULL OR
                                          inbound_source IN ('xml_upload','manual','dfe_focus')),
      manifestation               VARCHAR2(20)
                                      CONSTRAINT chk_inv_manifestation CHECK (
                                          manifestation IS NULL OR
                                          manifestation IN ('pending','ciencia','confirmacao',
                                                             'desconhecimento','nao_realizada','not_required')),
      manifestation_at            TIMESTAMP WITH TIME ZONE,
      manifestation_protocol      VARCHAR2(50),
      stock_updated               NUMBER(1) DEFAULT 0
                                      CONSTRAINT chk_inv_stock_updated CHECK (stock_updated IN (0,1)),
      focus_ref                   VARCHAR2(100),
      focus_status                VARCHAR2(50),
      focus_message               VARCHAR2(2000),
      xml_url                     VARCHAR2(1000),
      danfe_url                   VARCHAR2(1000),
      xml_local_path              VARCHAR2(1000),
      total_products              NUMBER(15,2) DEFAULT 0,
      total_freight               NUMBER(15,2) DEFAULT 0,
      total_insurance             NUMBER(15,2) DEFAULT 0,
      total_discount              NUMBER(15,2) DEFAULT 0,
      total_other                 NUMBER(15,2) DEFAULT 0,
      total_icms                  NUMBER(15,2) DEFAULT 0,
      total_icms_st               NUMBER(15,2) DEFAULT 0,
      total_pis                   NUMBER(15,2) DEFAULT 0,
      total_cofins                NUMBER(15,2) DEFAULT 0,
      total_ipi                   NUMBER(15,2) DEFAULT 0,
      total_invoice               NUMBER(15,2) DEFAULT 0,
      freight_modality            NUMBER(1)
                                      CONSTRAINT chk_inv_freight CHECK (
                                          freight_modality IS NULL OR freight_modality IN (0,1,2,3,4,9)),
      carrier_person_id           NUMBER,
      payment_method              VARCHAR2(2),
      payment_terms_json          CLOB,
      additional_info             VARCHAR2(2000),
      fiscal_info                 VARCHAR2(2000),
      cancelled_at                TIMESTAMP WITH TIME ZONE,
      cancel_reason               VARCHAR2(500),
      cancel_protocol             VARCHAR2(50),
      created_at                  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      updated_at                  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      created_by_user_id          NUMBER,
      CONSTRAINT fk_inv_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
      CONSTRAINT fk_inv_person FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL,
      CONSTRAINT fk_inv_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL,
      CONSTRAINT fk_inv_inbound FOREIGN KEY (inbound_invoice_id) REFERENCES invoices(id) ON DELETE SET NULL,
      CONSTRAINT fk_inv_carrier FOREIGN KEY (carrier_person_id) REFERENCES people(id) ON DELETE SET NULL,
      CONSTRAINT fk_inv_user FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
      CONSTRAINT uq_inv_serie_number UNIQUE (cmig_id, model, serie, nfe_number),
      CONSTRAINT uq_inv_access_key UNIQUE (access_key)
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_inv_cmig_status ON invoices(cmig_id, status)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_inv_cmig_issue ON invoices(cmig_id, issue_date)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_inv_cmig_direction ON invoices(cmig_id, direction)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_inv_focus_ref ON invoices(focus_ref)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_inv_person ON invoices(person_id)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

-- Migration 39: Tabela `people` — cadastro unificado Cliente/Fornecedor/Transportador
-- Idempotente: usa DECLARE/EXCEPTION para tabela e indexes; safe to re-run.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE people (
      id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      cmig_id         NUMBER NOT NULL,
      person_type     VARCHAR2(2) NOT NULL
                          CONSTRAINT chk_people_type CHECK (person_type IN ('PF','PJ')),
      document        VARCHAR2(20) NOT NULL,
      ie              VARCHAR2(20),
      ie_isento       NUMBER(1) DEFAULT 0
                          CONSTRAINT chk_people_ie_isento CHECK (ie_isento IN (0,1)),
      im              VARCHAR2(20),
      name            VARCHAR2(255) NOT NULL,
      trade_name      VARCHAR2(255),
      email           VARCHAR2(255),
      phone           VARCHAR2(20),
      zip_code        VARCHAR2(9),
      street          VARCHAR2(255),
      address_number  VARCHAR2(20),
      complement      VARCHAR2(100),
      neighborhood    VARCHAR2(100),
      city            VARCHAR2(100),
      state           VARCHAR2(2),
      ibge_code       VARCHAR2(7),
      country_code    VARCHAR2(4) DEFAULT '1058',
      is_customer     NUMBER(1) DEFAULT 1
                          CONSTRAINT chk_people_is_customer CHECK (is_customer IN (0,1)),
      is_supplier     NUMBER(1) DEFAULT 0
                          CONSTRAINT chk_people_is_supplier CHECK (is_supplier IN (0,1)),
      is_carrier      NUMBER(1) DEFAULT 0
                          CONSTRAINT chk_people_is_carrier CHECK (is_carrier IN (0,1)),
      notes           VARCHAR2(2000),
      is_active       NUMBER(1) DEFAULT 1
                          CONSTRAINT chk_people_is_active CHECK (is_active IN (0,1)),
      created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT fk_people_cmig FOREIGN KEY (cmig_id) REFERENCES cmigs(id) ON DELETE CASCADE,
      CONSTRAINT uq_people_cmig_doc UNIQUE (cmig_id, document)
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_people_cmig_customer ON people(cmig_id, is_customer)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_people_cmig_supplier ON people(cmig_id, is_supplier)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_people_name ON people(name)';
EXCEPTION WHEN e_index_exists THEN NULL;
END;
/

COMMIT;

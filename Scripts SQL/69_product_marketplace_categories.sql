-- ============================================================
-- MIG ECOMMERCE – Script 69: Categorias por Marketplace em Produtos
-- ============================================================
-- Permite cadastrar múltiplas categorias (Mercado Livre, Shopee, ...) em
-- cada produto CMIG ou Catalog (PG), com atributos pré-preenchidos por
-- categoria. Ao publicar um anúncio, o usuário pode reutilizar uma
-- categoria já cadastrada (com seus atributos) ou escolher uma nova.
--
-- Idempotente: usa bloco DECLARE/EXCEPTION para sobreviver a re-runs.

DECLARE
  e_table_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_table_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE product_marketplace_categories (
      id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      catalog_product_id  NUMBER,
      cmig_product_id     NUMBER,
      marketplace         VARCHAR2(30)   NOT NULL,
      category_id         VARCHAR2(100)  NOT NULL,
      category_name       VARCHAR2(300),
      category_path_json  CLOB,
      attributes_json     CLOB,
      created_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      updated_at          TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      CONSTRAINT chk_pmc_owner CHECK (
        (catalog_product_id IS NOT NULL AND cmig_product_id IS NULL) OR
        (catalog_product_id IS NULL AND cmig_product_id IS NOT NULL)
      ),
      CONSTRAINT chk_pmc_marketplace CHECK (marketplace IN ('mercado_livre','shopee')),
      CONSTRAINT fk_pmc_catalog FOREIGN KEY (catalog_product_id)
        REFERENCES catalog_products(id) ON DELETE CASCADE,
      CONSTRAINT fk_pmc_cmig FOREIGN KEY (cmig_product_id)
        REFERENCES cmig_products(id) ON DELETE CASCADE
    )
  ]';
EXCEPTION WHEN e_table_exists THEN NULL;
END;
/

-- Índices: lookup por produto + marketplace é o caminho quente
DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_pmc_catalog_mkt ON product_marketplace_categories(catalog_product_id, marketplace)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX idx_pmc_cmig_mkt ON product_marketplace_categories(cmig_product_id, marketplace)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

-- Unique: mesma categoria não pode ser cadastrada duas vezes no mesmo produto+marketplace
DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_pmc_catalog ON product_marketplace_categories(catalog_product_id, marketplace, category_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

DECLARE
  e_idx_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_idx_exists, -00955);
BEGIN
  EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uq_pmc_cmig ON product_marketplace_categories(cmig_product_id, marketplace, category_id)';
EXCEPTION WHEN e_idx_exists THEN NULL;
END;
/

-- Trigger para manter updated_at sincronizado
CREATE OR REPLACE TRIGGER trg_pmc_updated_at
  BEFORE UPDATE ON product_marketplace_categories
  FOR EACH ROW
BEGIN
  :NEW.updated_at := SYSTIMESTAMP;
END;
/

COMMIT;

-- Migration 178: Rastreio por caixa física — Endereçamento Fase 3c (ADR-0039).
-- A etiqueta/QR (storage_box_labels) já É uma caixa física; esta migration dá a ela CICLO DE VIDA e
-- auditoria de movimentação, para que a caixa possa ser MOVIDA de endereço mantendo o mesmo QR e ser
-- LOCALIZADA. Camada ADITIVA: NÃO cria coluna de saldo e NÃO adiciona location_id (o endereço da
-- caixa é o da sua alocação — fonte única). Mover caixa reusa o ledger net-zero da Fase 3b
-- (transfer_out/transfer_in já no CHECK da 177) → sem 6º reason, sem migration de CHECK.
--
-- `status`: 'closed' (caixa fechada, rastreável/movível) | 'open' (aberta → unidades soltas no mesmo
-- endereço) | 'consumed' (etiqueta retirada: reemissão/DELETE, ou futura baixa por caixa no despacho).
-- INVARIANTE: is_active = (status = 'closed'). `is_active` permanece como compat; `box_labels_to_close`
-- (ponto único) passa a carimbar status='open' junto do is_active=False, e os 2 sites diretos
-- (reemissão/DELETE) carimbam status='consumed'.
--
-- Idempotente: ORA-01430 (coluna já existe), ORA-00955 (nome já usado no índice/constraint),
-- ORA-02264 (nome de constraint já usado).

-- ── storage_box_labels: ciclo de vida + auditoria de movimentação ─────────────
DECLARE e_col EXCEPTION; PRAGMA EXCEPTION_INIT(e_col, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE storage_box_labels ADD status VARCHAR2(12) DEFAULT ''closed'' NOT NULL';
EXCEPTION WHEN e_col THEN NULL; END;
/

DECLARE e_col EXCEPTION; PRAGMA EXCEPTION_INIT(e_col, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE storage_box_labels ADD moved_at TIMESTAMP WITH TIME ZONE';
EXCEPTION WHEN e_col THEN NULL; END;
/

DECLARE e_col EXCEPTION; PRAGMA EXCEPTION_INIT(e_col, -1430);
BEGIN EXECUTE IMMEDIATE 'ALTER TABLE storage_box_labels ADD moved_by NUMBER REFERENCES users(id)';
EXCEPTION WHEN e_col THEN NULL; END;
/

-- Backfill: a coluna nasce com DEFAULT 'closed' (Oracle preenche as linhas existentes com o default);
-- as caixas já desativadas (is_active=0) devem virar 'consumed' p/ honrar o invariante.
BEGIN
  EXECUTE IMMEDIATE 'UPDATE storage_box_labels SET status = ''consumed'' WHERE is_active = 0 AND status = ''closed''';
  COMMIT;
END;
/

-- CHECK dos valores permitidos (idempotente: ignora se o nome já existe).
DECLARE
  e_dup EXCEPTION; PRAGMA EXCEPTION_INIT(e_dup, -2264);
  e_obj EXCEPTION; PRAGMA EXCEPTION_INIT(e_obj, -955);
BEGIN
  EXECUTE IMMEDIATE 'ALTER TABLE storage_box_labels ADD CONSTRAINT ck_box_label_status
                     CHECK (status IN (''closed'',''open'',''consumed''))';
EXCEPTION WHEN e_dup THEN NULL; WHEN e_obj THEN NULL; END;
/

-- Índice p/ o mapa/registro de caixas (por alocação + status) e p/ as consultas do box tracking.
DECLARE e_obj EXCEPTION; PRAGMA EXCEPTION_INIT(e_obj, -955);
BEGIN EXECUTE IMMEDIATE 'CREATE INDEX ix_box_label_alloc_status ON storage_box_labels (allocation_id, status)';
EXCEPTION WHEN e_obj THEN NULL; END;
/

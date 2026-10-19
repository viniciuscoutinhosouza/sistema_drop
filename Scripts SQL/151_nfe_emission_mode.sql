-- 151_nfe_emission_mode.sql
-- Modo de emissão de NF-e POR CONTA de marketplace (CNPJ):
--   'marketplace' (padrão) = Faturador do Mercado Livre (comportamento atual)
--   'own'                  = emissão própria direto na SEFAZ (ADR-0015/0028) + informa o ML
-- Roteia o comando de emissão em Pedidos NÃO-FULL. CPF segue sempre DC-e própria (ADR-0017);
-- produto rastreável segue forçando própria (ADR-0027). FULL fica fora (nota é do ML).
-- Idempotente (ORA-01430 = coluna já existe; ORA-02264 = constraint já existe).

DECLARE
  e_col_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_col_exists, -1430);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE marketplace_accounts ADD (nfe_emission_mode VARCHAR2(12) DEFAULT ''marketplace'' NOT NULL)';
EXCEPTION
  WHEN e_col_exists THEN NULL;
END;
/

DECLARE
  e_constraint_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_constraint_exists, -2264);
BEGIN
  EXECUTE IMMEDIATE
    'ALTER TABLE marketplace_accounts ADD CONSTRAINT chk_acc_nfe_emission_mode '
    || 'CHECK (nfe_emission_mode IN (''marketplace'', ''own''))';
EXCEPTION
  WHEN e_constraint_exists THEN NULL;
END;
/

-- Trava de unicidade (defesa em profundidade): no máximo 1 NF-e de VENDA VIVA por pedido,
-- INDEPENDENTE da origem (própria OU Faturador) — impede a coexistência própria+ML no mesmo
-- pedido (a duplicação que o fiscal marcou como CRITICAL). Índice funcional (Oracle): a chave
-- só existe p/ saída+venda em status "vivo" (draft/processing/transmitida/authorized);
-- canceladas/rejeitadas e devolução/complementar (purpose != 'venda') ficam de fora; pedido NULL
-- também. Se já houver duplicado legado (ORA-01452), NÃO cria o índice e segue — os guards de
-- código (emit_order_nfe + captura ml_fiscal_sync) protegem; o dado legado se limpa à parte.
DECLARE
  e_index_exists EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_index_exists, -955);
  e_dup_keys EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_dup_keys, -1452);
BEGIN
  -- NB: 'draft' fica FORA — um rascunho próprio (criado na prévia, antes de confirmar) não deve
  -- ocupar a vaga única nem bloquear a captura da nota real do Faturador. A unicidade incide só
  -- sobre nota já transmitida/autorizada (o que de fato não pode duplicar).
  EXECUTE IMMEDIATE
    'CREATE UNIQUE INDEX uq_invoice_order_sale_live ON invoices ('
    || 'CASE WHEN direction = ''out'' AND purpose = ''venda'' AND order_id IS NOT NULL '
    || '      AND status IN (''processing'', ''transmitida'', ''authorized'') '
    || '     THEN order_id END)';
EXCEPTION
  WHEN e_index_exists THEN NULL;
  WHEN e_dup_keys THEN
    DBMS_OUTPUT.PUT_LINE('AVISO: uq_invoice_order_sale_live NAO criado (duplicados legados). '
      || 'Guards de codigo protegem; limpar dado e recriar depois.');
END;
/

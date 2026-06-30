-- Migration 117: Numeração fiscal atômica da emissão MANUAL via SEFAZ.
-- Reserva o próximo número da série manual da CMIG sob lock de linha (FOR UPDATE),
-- desdobrado por ambiente (produção x homologação) para não queimar números de
-- produção nos testes. O lock é mantido por milissegundos — a chamada à SEFAZ
-- acontece DEPOIS, fora desta transação (o caller dá COMMIT junto do UPDATE do
-- Invoice). Gaps de numeração são fiscalmente aceitos (número rejeitado é "queimado";
-- número nunca usado resolve-se por inutilização). Idempotente: CREATE OR REPLACE.

CREATE OR REPLACE FUNCTION NFE_NEXTVAL_MANUAL (
    p_cmig_id   IN NUMBER,
    p_ambiente  IN VARCHAR2   -- 'production' | 'homolog'
) RETURN NUMBER IS
    v_numero  NUMBER;
BEGIN
    IF p_ambiente = 'production' THEN
        SELECT manual_nfe_next_number INTO v_numero
          FROM cmig_fiscal_config
         WHERE cmig_id = p_cmig_id
           FOR UPDATE;                       -- serializa emissões concorrentes da mesma CMIG

        UPDATE cmig_fiscal_config
           SET manual_nfe_next_number = manual_nfe_next_number + 1
         WHERE cmig_id = p_cmig_id;
    ELSE
        SELECT manual_nfe_next_number_homolog INTO v_numero
          FROM cmig_fiscal_config
         WHERE cmig_id = p_cmig_id
           FOR UPDATE;

        UPDATE cmig_fiscal_config
           SET manual_nfe_next_number_homolog = manual_nfe_next_number_homolog + 1
         WHERE cmig_id = p_cmig_id;
    END IF;

    RETURN v_numero;                          -- caller faz COMMIT junto do INSERT/UPDATE da nota
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20011,
            'Config fiscal nao encontrada para esta CMIG ao reservar numero de NF-e manual');
END;
/

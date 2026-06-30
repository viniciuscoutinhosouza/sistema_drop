# Guia de Implementação — Módulo de Emissão de NFe no Backend API (Python + Oracle)

> **Objetivo:** adicionar ao seu Backend API um grupo (`nfe`) capaz de emitir
> **NFe-55** e **NFCe-65** pelas SEFAZ estaduais, multiempresa.
> **Origem:** portado do sistema `NFE_VendasProduto` (Flask + Supabase/Postgres),
> validado em produção contra SEFAZ (cStat=100). Aqui adaptado para **Python +
> Oracle 19c+** com **fila assíncrona + worker**.
> **Data:** 2026-06-28 · **Status:** provisório (para revisão antes de implementar).

---

## Índice

1. [Arquitetura do módulo](#1-arquitetura-do-módulo)
2. [Configuração por empresa (o que cadastrar para cada CNPJ emitir)](#2-configuração-por-empresa)
3. [DDL Oracle — tabelas e campos](#3-ddl-oracle)
4. [Numeração fiscal atômica no Oracle](#4-numeração-fiscal-atômica)
5. [Triggers append-only](#5-triggers-append-only)
6. [Camada `fiscal/` (reaproveitável quase 1:1)](#6-camada-fiscal)
7. [Comunicação com os webservices da SEFAZ (SP e RJ) — o "acesso à API do governo"](#7-comunicação-com-os-webservices-da-sefaz)
8. [Endpoints REST (do seu backend)](#8-endpoints-rest)
9. [Fluxo de emissão assíncrona (POST → fila → worker → SEFAZ)](#9-fluxo-de-emissão-assíncrona)
10. [Regras fiscais não-negociáveis](#10-regras-fiscais-não-negociáveis)
11. [Segredos: certificado A1 e CSC](#11-segredos-certificado-a1-e-csc)
12. [Dependências Python](#12-dependências-python)
13. [Checklist de go-live por empresa](#13-checklist-de-go-live-por-empresa)
14. [Adequação à Reforma Tributária (IBS/CBS/IS) — NT 2025.002](#14-adequação-à-reforma-tributária-ibscbsis)

---

## 1. Arquitetura do módulo

Crie um pacote isolado dentro do seu backend, sem misturar com o resto:

```
seu_backend/
  nfe/
    __init__.py
    api/                  # endpoints REST (blueprint/router "nfe")
      empresas.py
      cadastros.py        # produtos / clientes / transportadoras
      notas.py            # emissão, consulta, xml, danfe, cancelar, cc-e
      jobs.py             # GET /jobs/{id} para polling
      auth.py             # autenticação + resolução da empresa/tenant
      idempotency.py      # decorator Idempotency-Key
      schemas.py          # validação de payload (Pydantic)
    fiscal/               # Python puro — sem banco, sem rede além da SEFAZ
      chave.py            # monta chave de acesso (44 dígitos) + DV
      models.py           # dataclasses imutáveis (NotaEmissao, Item, etc.)
      xml_builder.py      # gera o XML da NFe/NFCe 4.00
      signer.py           # assinatura XMLDSig com o .pfx (A1)
      sefaz_client.py     # catálogo de endpoints + POST SOAP mTLS
      emitter.py          # orquestra: monta → assina → envia → parseia
      consulta.py         # nfeConsultaProtocolo (regra N-6)
      cancelamento.py     # RecepcaoEvento4 (cancelamento + CC-e)
      danfe.py            # PDF via BrazilFiscalReport
      exceptions.py       # FiscalError, SefazError, SefazRejeicao...
    persistence/          # repositórios Oracle (python-oracledb)
      db.py               # pool de conexões
      empresas.py
      notas.py
      jobs.py
      numeracao.py        # nextval atômico
    worker/
      processor.py        # processa 1 job: emite e persiste
      runner.py           # loop: pega job (FOR UPDATE SKIP LOCKED) e chama processor
```

**Princípio que torna isso barato de portar:** a pasta `fiscal/` do projeto-fonte
**não toca em banco nem conhece o framework web**. São funções puras que recebem
`dataclasses` e devolvem `dataclasses`. Você copia esses arquivos quase intactos.
Só `persistence/` e `worker/` são reescritos para Oracle.

> **Separação de erros (importante para a fila):**
> - `SefazError` (rede/TLS/timeout/SEFAZ fora do ar) → **reagenda** o job (retry).
> - `FiscalError` (XML inválido, UF não mapeada, regra de negócio) → **falha** o job
>   (não adianta repetir).

---

## 2. Configuração por empresa

Cada **CNPJ emitente** (matriz e cada filial são emitentes independentes) precisa
da configuração abaixo **antes da primeira emissão**. Tudo isso vira uma linha em
`NFE_EMPRESAS` + linhas em `NFE_SERIES`.

| # | Configuração | Campo / destino | Observação |
|---|---|---|---|
| 1 | CNPJ | `NFE_EMPRESAS.CNPJ` | 14 dígitos, só números |
| 2 | Inscrição Estadual (IE) e IE-ST | `IE`, `IE_ST` | IE-ST opcional |
| 3 | Razão social / nome fantasia | `RAZAO_SOCIAL`, `NOME_FANTASIA` | |
| 4 | Tipo | `TIPO` | `matriz` / `filial` |
| 5 | Endereço completo | `LOGRADOURO`, `NUMERO`, `COMPLEMENTO`, `BAIRRO`, `MUNICIPIO_IBGE`, `MUNICIPIO_NOME`, `UF`, `CEP` | **código IBGE de 7 dígitos é obrigatório** |
| 6 | Contato | `TELEFONE`, `EMAIL` | opcional |
| 7 | Regime tributário (CRT) | `CRT` | 1=Simples Nacional, 2=Simples MEI, 3=Regime Normal, 4=Simples Excesso |
| 8 | FECP | `ALIQUOTA_FECP` | ex.: 2.00 no RJ; 0 onde não há |
| 9 | Certificado A1 (.pfx) | `CERT_PATH` + `CERT_PASS_ENV` + `CERT_VALIDADE` | caminho no servidor + **nome da env var** com a senha |
| 10 | CSC + idCSC (só NFCe-65) | `CSC_ID` + `CSC_TOKEN_ENV` | gera o QR Code da NFCe |
| 11 | Séries fiscais | `NFE_SERIES` | uma linha por `(empresa, modelo, série, ambiente)` |
| 12 | Liberação de produção | `PRODUCAO_LIBERADA` | só emite em produção quando =1 (go-live faseado) |
| 13 | Numeração inicial | `NFE_SERIES.PROXIMO_NUMERO` | se migrar do Bling, continue a numeração existente |

### Duas regras aprendidas no projeto-fonte (evitam rejeição na SEFAZ)

- **🔴 Um CNPJ = um certificado.** O certificado A1 da matriz **não emite NFe da
  filial**, mesmo com a mesma raiz de CNPJ. A SEFAZ-SP rejeita com
  `cStat=290 "Certificado Assinatura inválido"`. Cada empresa precisa do seu
  próprio `.pfx`. (ICP-Brasil + SEFAZ validam o CNPJ completo, não a raiz.)
- **🔴 Senha do cert e token CSC nunca no banco.** O banco guarda só o **nome da
  variável de ambiente**. O valor real vive no EnvironmentFile/cofre do servidor
  (chmod 600). Documentos versionados usam `«REDACTED»`.

### Ordem de cadastro de uma empresa nova

```
1. INSERT em NFE_EMPRESAS (PRODUCAO_LIBERADA = 0)
2. Coloque o .pfx no servidor + defina a env var da senha (ex.: NFE_CERT_PASS_EMP_X)
3. INSERT em NFE_SERIES para cada (modelo, série, ambiente) — homologação primeiro
4. Smoke test em HOMOLOGAÇÃO: emitir 1 NFe-55 e 1 NFCe-65 → conferir cStat=100
5. Confirmar credenciamento da empresa na SEFAZ da UF
6. UPDATE NFE_EMPRESAS SET PRODUCAO_LIBERADA = 1  (libera produção)
```

---

## 3. DDL Oracle

> DDL no formato **compatível com Oracle 12.2 → 23c** (roda no seu ambiente
> independente da versão exata): PK `RAW(16) DEFAULT SYS_GUID()`, boolean como
> `NUMBER(1)`, JSON como `CLOB` com `CHECK (... IS JSON)`, timestamps
> `TIMESTAMP WITH TIME ZONE`. Em 21c+ você pode trocar os `CLOB IS JSON` pelo
> tipo `JSON` nativo, e em 23c os `NUMBER(1)` por `BOOLEAN` — opcional.

### 3.1 Configuração

```sql
-- ============================================================
-- NFE_EMPRESAS — emitente (núcleo da configuração por empresa)
-- ============================================================
CREATE TABLE NFE_EMPRESAS (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    CNPJ                CHAR(14)       NOT NULL,
    IE                  VARCHAR2(20)   NOT NULL,
    IE_ST               VARCHAR2(20),
    RAZAO_SOCIAL        VARCHAR2(150)  NOT NULL,
    NOME_FANTASIA       VARCHAR2(150),
    TIPO                VARCHAR2(10)   NOT NULL,  -- matriz | filial
    LOGRADOURO          VARCHAR2(150)  NOT NULL,
    NUMERO              VARCHAR2(20)   NOT NULL,
    COMPLEMENTO         VARCHAR2(80),
    BAIRRO              VARCHAR2(80)   NOT NULL,
    MUNICIPIO_IBGE      CHAR(7)        NOT NULL,
    MUNICIPIO_NOME      VARCHAR2(100)  NOT NULL,
    UF                  CHAR(2)        NOT NULL,
    CEP                 CHAR(8)        NOT NULL,
    PAIS_CODIGO         CHAR(4)        DEFAULT '1058' NOT NULL,
    PAIS_NOME           VARCHAR2(60)   DEFAULT 'Brasil' NOT NULL,
    TELEFONE            VARCHAR2(20),
    EMAIL               VARCHAR2(120),
    CRT                 NUMBER(1)      NOT NULL,   -- 1,2,3,4
    ALIQUOTA_FECP       NUMBER(5,2)    DEFAULT 0 NOT NULL,
    PRODUCAO_LIBERADA   NUMBER(1)      DEFAULT 0 NOT NULL,
    CERT_PATH           VARCHAR2(255)  NOT NULL,
    CERT_PASS_ENV       VARCHAR2(80)   NOT NULL,   -- nome da env var, NÃO a senha
    CERT_VALIDADE       DATE,
    CSC_ID              VARCHAR2(10),               -- NFCe
    CSC_TOKEN_ENV       VARCHAR2(80),               -- nome da env var do CSC
    ATIVO               NUMBER(1)      DEFAULT 1 NOT NULL,
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_EMPRESAS_CNPJ_UK   UNIQUE (CNPJ),
    CONSTRAINT NFE_EMPRESAS_TIPO_CK   CHECK (TIPO IN ('matriz','filial')),
    CONSTRAINT NFE_EMPRESAS_CRT_CK    CHECK (CRT IN (1,2,3,4)),
    CONSTRAINT NFE_EMPRESAS_PROD_CK   CHECK (PRODUCAO_LIBERADA IN (0,1)),
    CONSTRAINT NFE_EMPRESAS_ATIVO_CK  CHECK (ATIVO IN (0,1))
);

-- ============================================================
-- NFE_SERIES — séries fiscais + numeração atômica
-- ============================================================
CREATE TABLE NFE_SERIES (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    EMPRESA_ID          RAW(16)        NOT NULL,
    MODELO              NUMBER(2)      NOT NULL,   -- 55 | 65
    SERIE               NUMBER(3)      NOT NULL,   -- 0..999
    AMBIENTE            VARCHAR2(12)   NOT NULL,   -- homologacao | producao
    PROXIMO_NUMERO      NUMBER(9)      DEFAULT 1 NOT NULL,
    ATIVA               NUMBER(1)      DEFAULT 1 NOT NULL,
    CRIADA_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_SERIES_EMP_FK   FOREIGN KEY (EMPRESA_ID) REFERENCES NFE_EMPRESAS(ID),
    CONSTRAINT NFE_SERIES_UK       UNIQUE (EMPRESA_ID, MODELO, SERIE, AMBIENTE),
    CONSTRAINT NFE_SERIES_MOD_CK   CHECK (MODELO IN (55,65)),
    CONSTRAINT NFE_SERIES_AMB_CK   CHECK (AMBIENTE IN ('homologacao','producao'))
);
```

### 3.2 Cadastros

```sql
-- ============================================================
-- NFE_PRODUTOS — catálogo por empresa
-- ============================================================
CREATE TABLE NFE_PRODUTOS (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    EMPRESA_ID          RAW(16)        NOT NULL,
    CODIGO              VARCHAR2(60)   NOT NULL,
    EAN                 VARCHAR2(14),
    DESCRICAO           VARCHAR2(120)  NOT NULL,
    NCM                 CHAR(8)        NOT NULL,
    CEST                CHAR(7),
    CFOP_INTRA_UF       CHAR(4),
    CFOP_INTER_UF       CHAR(4),
    CSOSN               CHAR(3)        DEFAULT '102' NOT NULL,
    ORIGEM              CHAR(1)        DEFAULT '0' NOT NULL,  -- 0..8
    UNIDADE             VARCHAR2(6)    NOT NULL,
    PESO_KG             NUMBER(10,3),
    PRECO_VENDA         NUMBER(15,2)   NOT NULL,
    ALIQUOTA_ICMS       NUMBER(5,2)    DEFAULT 18 NOT NULL,
    TEM_ST              NUMBER(1)      DEFAULT 0 NOT NULL,
    MVA                 NUMBER(7,4),
    ISENTO_FECP         NUMBER(1)      DEFAULT 0 NOT NULL,
    INFO_ADICIONAL      VARCHAR2(500),
    ATIVO               NUMBER(1)      DEFAULT 1 NOT NULL,
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    ATUALIZADO_EM       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_PROD_EMP_FK FOREIGN KEY (EMPRESA_ID) REFERENCES NFE_EMPRESAS(ID),
    CONSTRAINT NFE_PROD_UK     UNIQUE (EMPRESA_ID, CODIGO),
    CONSTRAINT NFE_PROD_ORI_CK CHECK (ORIGEM IN ('0','1','2','3','4','5','6','7','8'))
);

-- ============================================================
-- NFE_CLIENTES — destinatários por empresa
-- ============================================================
CREATE TABLE NFE_CLIENTES (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    EMPRESA_ID          RAW(16)        NOT NULL,
    TIPO                CHAR(2)        NOT NULL,  -- PF | PJ
    CPF_CNPJ            VARCHAR2(14)   NOT NULL,
    NOME_RAZAO_SOCIAL   VARCHAR2(150)  NOT NULL,
    IE                  VARCHAR2(20),
    INDICADOR_IE        NUMBER(1)      DEFAULT 9 NOT NULL,  -- 1 contrib, 2 isento, 9 não-contrib
    EMAIL               VARCHAR2(120),
    TELEFONE            VARCHAR2(20),
    LOGRADOURO          VARCHAR2(150),
    NUMERO              VARCHAR2(20),
    COMPLEMENTO         VARCHAR2(80),
    BAIRRO              VARCHAR2(80),
    MUNICIPIO_IBGE      CHAR(7),
    MUNICIPIO_NOME      VARCHAR2(100),
    UF                  CHAR(2),
    CEP                 CHAR(8),
    ATIVO               NUMBER(1)      DEFAULT 1 NOT NULL,
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_CLI_EMP_FK FOREIGN KEY (EMPRESA_ID) REFERENCES NFE_EMPRESAS(ID),
    CONSTRAINT NFE_CLI_UK     UNIQUE (EMPRESA_ID, CPF_CNPJ),
    CONSTRAINT NFE_CLI_TIPO_CK CHECK (TIPO IN ('PF','PJ')),
    CONSTRAINT NFE_CLI_IIE_CK  CHECK (INDICADOR_IE IN (1,2,9))
);

-- ============================================================
-- NFE_TRANSPORTADORAS — opcional
-- ============================================================
CREATE TABLE NFE_TRANSPORTADORAS (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    EMPRESA_ID          RAW(16)        NOT NULL,
    TIPO                CHAR(2)        NOT NULL,
    CPF_CNPJ            VARCHAR2(14)   NOT NULL,
    RAZAO_SOCIAL        VARCHAR2(150)  NOT NULL,
    IE                  VARCHAR2(20),
    ENDERECO_COMPLETO   VARCHAR2(255),
    MUNICIPIO_NOME      VARCHAR2(100),
    UF                  CHAR(2),
    ATIVA               NUMBER(1)      DEFAULT 1 NOT NULL,
    CRIADA_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_TRANSP_EMP_FK FOREIGN KEY (EMPRESA_ID) REFERENCES NFE_EMPRESAS(ID),
    CONSTRAINT NFE_TRANSP_TIPO_CK CHECK (TIPO IN ('PF','PJ'))
);
```

### 3.3 Documentos fiscais

```sql
-- ============================================================
-- NFE_NOTAS — cabeçalho NFe-55 e NFCe-65 (discriminadas por MODELO)
-- ============================================================
CREATE TABLE NFE_NOTAS (
    ID                      RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    EMPRESA_ID              RAW(16)        NOT NULL,
    CLIENTE_ID              RAW(16),
    TRANSPORTADORA_ID       RAW(16),
    -- Identificação fiscal
    MODELO                  NUMBER(2)      NOT NULL,   -- 55 | 65
    SERIE                   NUMBER(3)      NOT NULL,
    NUMERO                  NUMBER(9)      NOT NULL,
    AMBIENTE                VARCHAR2(12)   NOT NULL,
    STATUS                  VARCHAR2(15)   DEFAULT 'rascunho' NOT NULL,
    CHAVE_ACESSO            CHAR(44),
    PROTOCOLO_AUTORIZACAO   VARCHAR2(20),
    PROTOCOLO_CANCELAMENTO  VARCHAR2(20),
    -- Natureza
    NATUREZA_OPERACAO       VARCHAR2(120)  NOT NULL,
    FINALIDADE              NUMBER(1)      DEFAULT 1 NOT NULL,  -- 1 normal,2 compl,3 ajuste,4 devol
    NOTA_REFERENCIADA_ID    RAW(16),
    CHAVE_REFERENCIADA      CHAR(44),
    IND_PRESENCA            NUMBER(1)      DEFAULT 9 NOT NULL,
    IND_INTERMED            NUMBER(1),
    IND_FINAL               NUMBER(1)      DEFAULT 0 NOT NULL,
    -- Totais
    VALOR_PRODUTOS          NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_FRETE             NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_SEGURO            NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_DESCONTO          NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_OUTRAS            NUMBER(15,2)   DEFAULT 0 NOT NULL,
    BC_ICMS                 NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_ICMS              NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_FECP              NUMBER(15,2)   DEFAULT 0 NOT NULL,
    BC_ICMS_ST              NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_ICMS_ST           NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_IPI               NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_TOTAL             NUMBER(15,2)   DEFAULT 0 NOT NULL,
    -- DIFAL EC 87/2015 (nullable; só inter-UF B2C)
    V_BC_UF_DEST            NUMBER(15,2),
    P_ICMS_UF_DEST          NUMBER(5,2),
    V_ICMS_UF_DEST          NUMBER(15,2),
    V_ICMS_UF_REMET         NUMBER(15,2),
    V_FCP_UF_DEST           NUMBER(15,2),
    -- Pagamentos (JSON): [{"tPag":"01","valor":"100.00","indPag":0}]
    PAGAMENTOS              CLOB,
    TRANSPORTE_MODALIDADE   NUMBER(1),
    INFO_COMPLEMENTAR       VARCHAR2(2000),
    INFO_FISCO              VARCHAR2(2000),
    IDEMPOTENCY_KEY         VARCHAR2(36),
    -- Timestamps
    EMITIDA_EM              TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    ASSINADA_EM             TIMESTAMP WITH TIME ZONE,
    TRANSMITIDA_EM          TIMESTAMP WITH TIME ZONE,
    AUTORIZADA_EM           TIMESTAMP WITH TIME ZONE,
    CANCELADA_EM            TIMESTAMP WITH TIME ZONE,
    CRIADA_EM               TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_NOTAS_EMP_FK FOREIGN KEY (EMPRESA_ID) REFERENCES NFE_EMPRESAS(ID),
    CONSTRAINT NFE_NOTAS_CLI_FK FOREIGN KEY (CLIENTE_ID) REFERENCES NFE_CLIENTES(ID),
    CONSTRAINT NFE_NOTAS_MOD_CK CHECK (MODELO IN (55,65)),
    CONSTRAINT NFE_NOTAS_AMB_CK CHECK (AMBIENTE IN ('homologacao','producao')),
    CONSTRAINT NFE_NOTAS_PAG_CK CHECK (PAGAMENTOS IS JSON),
    CONSTRAINT NFE_NOTAS_ST_CK  CHECK (STATUS IN (
        'rascunho','assinada','transmitida','autorizada',
        'rejeitada','denegada','cancelada','inutilizada'))
);
-- Numeração única por série/ambiente + busca por chave
CREATE UNIQUE INDEX NFE_NOTAS_SERIE_UK ON NFE_NOTAS (EMPRESA_ID, MODELO, SERIE, NUMERO, AMBIENTE);
CREATE INDEX        NFE_NOTAS_CHAVE_IX ON NFE_NOTAS (CHAVE_ACESSO);
CREATE INDEX        NFE_NOTAS_DASH_IX  ON NFE_NOTAS (EMPRESA_ID, STATUS, CRIADA_EM);

-- ============================================================
-- NFE_NOTAS_ITENS — snapshot fiscal imutável (regra N-2)
-- ============================================================
CREATE TABLE NFE_NOTAS_ITENS (
    ID                      RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    NOTA_ID                 RAW(16)        NOT NULL,
    PRODUTO_ID              RAW(16),
    NUMERO_ITEM             NUMBER(4)      NOT NULL,
    -- Snapshot do produto (congelado no momento da emissão)
    CODIGO_SNAPSHOT         VARCHAR2(60)   NOT NULL,
    EAN_SNAPSHOT            VARCHAR2(14),
    NCM_SNAPSHOT            CHAR(8)        NOT NULL,
    CEST_SNAPSHOT           CHAR(7),
    CFOP_SNAPSHOT           CHAR(4)        NOT NULL,
    CSOSN_SNAPSHOT          CHAR(3)        NOT NULL,
    ORIGEM_SNAPSHOT         CHAR(1)        NOT NULL,
    DESCRICAO_SNAPSHOT      VARCHAR2(120)  NOT NULL,
    UNIDADE_SNAPSHOT        VARCHAR2(6)    NOT NULL,
    ALIQUOTA_ICMS_SNAPSHOT  NUMBER(5,2),
    TEM_ST_SNAPSHOT         NUMBER(1),
    MVA_SNAPSHOT            NUMBER(7,4),
    INFO_ADICIONAL_SNAPSHOT VARCHAR2(500),
    -- Quantidades e valores
    QUANTIDADE              NUMBER(15,4)   NOT NULL,
    PRECO_UNITARIO_SNAPSHOT NUMBER(15,4)   NOT NULL,
    VALOR_PRODUTO           NUMBER(15,2)   NOT NULL,
    VALOR_FRETE             NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_DESCONTO          NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_SEGURO            NUMBER(15,2)   DEFAULT 0 NOT NULL,
    VALOR_OUTRAS            NUMBER(15,2)   DEFAULT 0 NOT NULL,
    -- Tributos calculados
    V_BC                    NUMBER(15,2)   DEFAULT 0 NOT NULL,
    V_ICMS                  NUMBER(15,2)   DEFAULT 0 NOT NULL,
    V_BC_ST                 NUMBER(15,2)   DEFAULT 0 NOT NULL,
    V_ICMS_ST               NUMBER(15,2)   DEFAULT 0 NOT NULL,
    V_FECP                  NUMBER(15,2)   DEFAULT 0 NOT NULL,
    V_IPI                   NUMBER(15,2)   DEFAULT 0 NOT NULL,
    CRIADO_EM               TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_ITENS_NOTA_FK FOREIGN KEY (NOTA_ID) REFERENCES NFE_NOTAS(ID),
    CONSTRAINT NFE_ITENS_UK      UNIQUE (NOTA_ID, NUMERO_ITEM)
);

-- ============================================================
-- NFE_NOTAS_EVENTOS — append-only (histórico de transições/eventos)
-- ============================================================
CREATE TABLE NFE_NOTAS_EVENTOS (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    NOTA_ID             RAW(16)        NOT NULL,
    EMPRESA_ID          RAW(16)        NOT NULL,
    TIPO                VARCHAR2(20)   NOT NULL,
    STATUS_ANTERIOR     VARCHAR2(15),
    STATUS_NOVO         VARCHAR2(15),
    AUTOR_TIPO          VARCHAR2(10)   NOT NULL,  -- user | api_key | system
    AUTOR_ID            VARCHAR2(60),
    PAYLOAD             CLOB,
    MENSAGEM            VARCHAR2(500),
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_EVT_NOTA_FK FOREIGN KEY (NOTA_ID) REFERENCES NFE_NOTAS(ID),
    CONSTRAINT NFE_EVT_PAY_CK  CHECK (PAYLOAD IS JSON)
);
CREATE INDEX NFE_EVT_NOTA_IX ON NFE_NOTAS_EVENTOS (NOTA_ID, CRIADO_EM);

-- ============================================================
-- NFE_LOGS_SEFAZ — append-only, retenção 5 anos (XML SOAP completo)
-- ============================================================
CREATE TABLE NFE_LOGS_SEFAZ (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    NOTA_ID             RAW(16)        NOT NULL,
    EMPRESA_ID          RAW(16)        NOT NULL,
    OPERACAO            VARCHAR2(40)   NOT NULL,
    C_STAT              NUMBER(4),
    X_MOTIVO            VARCHAR2(255),
    PAYLOAD_REQUEST     CLOB,
    PAYLOAD_RESPONSE    CLOB,
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_LOG_NOTA_FK FOREIGN KEY (NOTA_ID) REFERENCES NFE_NOTAS(ID)
);
CREATE INDEX NFE_LOG_NOTA_IX ON NFE_LOGS_SEFAZ (NOTA_ID, CRIADO_EM);

-- ============================================================
-- NFE_JOBS — fila assíncrona
-- ============================================================
CREATE TABLE NFE_JOBS (
    ID                  RAW(16)        DEFAULT SYS_GUID() PRIMARY KEY,
    NOTA_ID             RAW(16)        NOT NULL,
    EMPRESA_ID          RAW(16)        NOT NULL,
    TIPO                VARCHAR2(10)   NOT NULL,  -- emitir | cancelar
    STATUS              VARCHAR2(12)   DEFAULT 'pendente' NOT NULL,
    ERROR_MESSAGE       VARCHAR2(1000),
    TENTATIVAS          NUMBER(3)      DEFAULT 0 NOT NULL,
    PROXIMO_RETRY_EM    TIMESTAMP WITH TIME ZONE,
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    PROCESSADO_EM       TIMESTAMP WITH TIME ZONE,
    CONSTRAINT NFE_JOBS_NOTA_FK FOREIGN KEY (NOTA_ID) REFERENCES NFE_NOTAS(ID),
    CONSTRAINT NFE_JOBS_TIPO_CK CHECK (TIPO IN ('emitir','cancelar')),
    CONSTRAINT NFE_JOBS_ST_CK   CHECK (STATUS IN ('pendente','processando','concluido','falhou'))
);
CREATE INDEX NFE_JOBS_PICKUP_IX ON NFE_JOBS (STATUS, PROXIMO_RETRY_EM);

-- ============================================================
-- NFE_IDEMPOTENCIA — cache de Idempotency-Key (TTL 24h)
-- ============================================================
CREATE TABLE NFE_IDEMPOTENCIA (
    IDEMP_KEY           VARCHAR2(36)   NOT NULL,
    EMPRESA_ID          RAW(16)        NOT NULL,
    METHOD              VARCHAR2(10)   NOT NULL,
    PATH                VARCHAR2(255)  NOT NULL,
    HASH_BODY           VARCHAR2(64)   NOT NULL,
    STATUS_CODE         NUMBER(3)      NOT NULL,
    RESPONSE_CACHED     CLOB           NOT NULL,
    CRIADO_EM           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT NFE_IDEMP_PK PRIMARY KEY (IDEMP_KEY, EMPRESA_ID),
    CONSTRAINT NFE_IDEMP_CK CHECK (RESPONSE_CACHED IS JSON)
);
```

### 3.4 Catálogo fiscal (read-only)

```sql
CREATE TABLE NFE_REF_NCM        (CODIGO CHAR(8) PRIMARY KEY, DESCRICAO VARCHAR2(400));
CREATE TABLE NFE_REF_CFOP       (CODIGO CHAR(4) PRIMARY KEY, DESCRICAO VARCHAR2(400), APLICACAO VARCHAR2(40));
CREATE TABLE NFE_REF_CSOSN      (CODIGO CHAR(3) PRIMARY KEY, DESCRICAO VARCHAR2(200));
CREATE TABLE NFE_REF_CST        (CODIGO CHAR(3), TIPO_TRIBUTO VARCHAR2(10), DESCRICAO VARCHAR2(200),
                                 CONSTRAINT NFE_REF_CST_PK PRIMARY KEY (CODIGO, TIPO_TRIBUTO));
CREATE TABLE NFE_REF_MUNICIPIOS (CODIGO CHAR(7) PRIMARY KEY, NOME VARCHAR2(100), UF CHAR(2));
CREATE TABLE NFE_REF_ALIQ_INTER (UF_ORIGEM CHAR(2), UF_DESTINO CHAR(2), ALIQUOTA NUMBER(5,2),
                                 VIGENCIA_INICIO DATE DEFAULT DATE '2016-01-01',
                                 CONSTRAINT NFE_REF_ALIQ_PK PRIMARY KEY (UF_ORIGEM, UF_DESTINO, VIGENCIA_INICIO));
```

> **Multi-tenant no Oracle:** o Supabase usava RLS no banco. No Oracle, sem
> Enterprise/VPD, o isolamento por empresa é feito **na camada de aplicação**:
> todo `SELECT/UPDATE/DELETE` carrega `WHERE EMPRESA_ID = :empresa_id`, e
> `auth.py` resolve a empresa autenticada antes de cada request. Se você já tem
> um conceito de "empresa/cliente" no seu sistema, `NFE_EMPRESAS.ID` pode
> referenciar essa tabela mestre em vez de ser independente.

---

## 4. Numeração fiscal atômica

O projeto-fonte usa `SEQUENCE` Postgres por chave composta. No Oracle, a forma
mais simples e robusta é incrementar `NFE_SERIES.PROXIMO_NUMERO` sob lock de linha
(`SELECT ... FOR UPDATE`). Gaps são fiscalmente aceitos (número rejeitado é
"queimado"). Pacote PL/SQL:

```sql
CREATE OR REPLACE FUNCTION NFE_NEXTVAL_SERIE (
    p_empresa_id  IN RAW,
    p_modelo      IN NUMBER,
    p_serie       IN NUMBER,
    p_ambiente    IN VARCHAR2
) RETURN NUMBER IS
    v_numero  NUMBER;
BEGIN
    SELECT PROXIMO_NUMERO INTO v_numero
      FROM NFE_SERIES
     WHERE EMPRESA_ID = p_empresa_id
       AND MODELO     = p_modelo
       AND SERIE      = p_serie
       AND AMBIENTE   = p_ambiente
       FOR UPDATE;                       -- lock de linha: emissões concorrentes serializam

    UPDATE NFE_SERIES
       SET PROXIMO_NUMERO = PROXIMO_NUMERO + 1
     WHERE EMPRESA_ID = p_empresa_id
       AND MODELO     = p_modelo
       AND SERIE      = p_serie
       AND AMBIENTE   = p_ambiente;

    RETURN v_numero;                      -- caller faz COMMIT junto do INSERT da nota
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20010,
            'Serie fiscal nao cadastrada para esta empresa/modelo/ambiente');
END;
```

> O lock é mantido só até o `COMMIT` da transação de criação da nota (milissegundos
> — **a chamada à SEFAZ acontece depois, no worker**, fora dessa transação). Isso
> evita o problema de "lock segurado durante chamada de rede" que o projeto-fonte
> teve que resolver à parte.

---

## 5. Triggers append-only

Replicam a defesa fiscal do projeto (tabelas imutáveis após INSERT):

```sql
CREATE OR REPLACE TRIGGER NFE_TRG_EVENTOS_IMMUTABLE
BEFORE UPDATE OR DELETE ON NFE_NOTAS_EVENTOS
BEGIN
    RAISE_APPLICATION_ERROR(-20007,
        'Tabela imutavel: UPDATE/DELETE proibido por politica fiscal');
END;
/

CREATE OR REPLACE TRIGGER NFE_TRG_LOGS_IMMUTABLE
BEFORE UPDATE OR DELETE ON NFE_LOGS_SEFAZ
BEGIN
    RAISE_APPLICATION_ERROR(-20007,
        'Tabela imutavel: UPDATE/DELETE proibido por politica fiscal');
END;
/

CREATE OR REPLACE TRIGGER NFE_TRG_ITENS_IMMUTABLE
BEFORE UPDATE OR DELETE ON NFE_NOTAS_ITENS
BEGIN
    RAISE_APPLICATION_ERROR(-20007,
        'Tabela imutavel: UPDATE/DELETE proibido por politica fiscal');
END;
/
```

---

## 6. Camada `fiscal/`

Copie do projeto-fonte (`backend/src/nfe_service/fiscal/`) **praticamente intacto**.
Os arquivos são Python puro e independentes de banco:

| Arquivo | Função | Precisa mudar? |
|---|---|---|
| `models.py` | dataclasses imutáveis (`Endereco`, `Estabelecimento`, `Cliente`, `Produto`, `ItemEmissao`, `Pagamento`, `NotaEmissao`) com validação no `__post_init__` | **Não** |
| `chave.py` | monta chave de acesso (44 dígitos) + dígito verificador + cNF | **Não** |
| `xml_builder.py` | gera XML da NFe/NFCe 4.00 (minificado) | **Não** |
| `signer.py` | assina XMLDSig SHA-1 a partir do `.pfx` (A1) | **Não** |
| `sefaz_client.py` | catálogo `SEFAZ_NFE_ENDPOINTS_POR_UF` (RJ/SVRS, SP/WS próprio…) + `post_sefaz()` mTLS + parsers `extract_cstat/nprot/chnfe` | só estende o dict para novas UFs |
| `emitter.py` | pipeline: `montar_xml → assinar → enviNFe → SOAP → POST → parse` → `RetornoEmissao` | **Não** (não toca em banco) |
| `consulta.py` | `nfeConsultaProtocolo` (regra N-6) | **Não** |
| `cancelamento.py` | `RecepcaoEvento4` (cancelamento + CC-e) | **Não** |
| `danfe.py` | DANFE PDF via `BrazilFiscalReport` | **Não** |
| `exceptions.py` | `FiscalError`, `SefazError`, `SefazRejeicao`, `XmlBuildError`, `ChaveAcessoError` | **Não** |

A interface de emissão é uma função pura:

```python
from nfe.fiscal.emitter import emitir_nfe   # devolve RetornoEmissao
retorno = emitir_nfe(
    nota,                      # NotaEmissao (dataclass montada pela persistence)
    pfx_path=cert_path,        # caminho do .pfx da empresa
    pfx_password=senha,        # lida da env var (CERT_PASS_ENV)
    verify_ssl=is_production,  # True em prod (exige cabundle ICP-Brasil)
)
# retorno.autorizada / retorno.cstat_final / retorno.nprot / retorno.xml_signed
```

---

## 7. Comunicação com os webservices da SEFAZ

> **Esta é a parte do "acessar as APIs do governo e gerar NFe por SP e RJ".**
> Não existe uma "API REST do governo" com token: a SEFAZ expõe **webservices
> SOAP** (um conjunto de `.asmx`), e a autenticação é feita por **mTLS +
> assinatura digital do XML** usando o certificado A1 da empresa. Não há
> usuário/senha nem API key — *a sua identidade é o próprio certificado*.

### 7.1 Pré-requisitos legais (sem isto, nenhuma chamada funciona)

| # | Requisito | Como obter | Vale para |
|---|---|---|---|
| 1 | **Certificado digital A1 e-CNPJ (ICP-Brasil)** | Comprar numa AC (Serasa, Certisign, Soluti, Valid, AC SAFEWEB…). Vem um arquivo `.pfx`/`.p12` + senha. **Um por CNPJ.** | SP e RJ |
| 2 | **Credenciamento como emissor de NFe** | Portal da SEFAZ da UF da empresa. **SP:** posto fiscal / sistema **Cadesp**. **RJ:** portal SEFAZ-RJ / SUCIEF. | por UF |
| 3 | **Inscrição Estadual ativa** | já deve existir para a empresa operar | por UF |
| 4 | **CSC — Código de Segurança do Contribuinte** (só **NFCe-65**) | Solicitado no portal da SEFAZ da UF; devolve `idCSC` + token. Usado para gerar o QR Code. | por UF, só NFCe |

> Sem credenciamento, a SEFAZ rejeita a emissão mesmo com cert válido. Por isso
> o checklist de go-live (§13) tem "confirmar credenciamento" antes de ligar a
> produção. No projeto-fonte, o credenciamento da matriz RJ ficou pendente de
> confirmação — é um passo administrativo, não de código.

### 7.2 A SEFAZ é SOAP, não REST — e cada UF tem seus endpoints

São 5 webservices por UF/ambiente (os que o módulo usa):

| Serviço (WSDL) | Para quê |
|---|---|
| `NFeStatusServico4` | health-check da SEFAZ (use antes de emitir em lote) |
| `NFeAutorizacao4` | **enviar a NFe/NFCe para autorização** (o principal) |
| `NFeRetAutorizacao4` | consultar recibo do lote (modo assíncrono) |
| `NFeConsultaProtocolo4` | consultar situação de uma chave (regra N-6, antes de retry) |
| `RecepcaoEvento4` | cancelamento, carta de correção, manifestação |

**Quirk crítico aprendido no projeto-fonte:**
- **RJ não usa servidor próprio** — a autorização de **NFe-55** do RJ é feita pelo
  **SVRS** (`svrs.rs.gov.br`), **não** por `nfe.fazenda.rj.gov.br`.
- **SP usa servidor próprio** (`nfe.fazenda.sp.gov.br`).
- Para **NFCe-65 do RJ**, o autorizador pode ser outro host — confirmar no portal
  da SEFAZ-RJ ao implementar NFCe.

### 7.3 URLs reais dos webservices (homologação e produção)

> Valores extraídos do `sefaz_client.py` já validado em produção (cStat=100).
> Estes são os endereços que vão no catálogo `SEFAZ_NFE_ENDPOINTS_POR_UF`.

#### SEFAZ-RJ — NFe-55 via SVRS

| Serviço | Homologação | Produção |
|---|---|---|
| Status | `https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx` | `https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx` |
| **Autorização** | `https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx` | `https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx` |
| Ret. Autorização | `https://nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx` | `https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx` |
| Consulta Protocolo | `https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx` | `https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx` |
| Recepção Evento | `https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx` | `https://nfe.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx` |

#### SEFAZ-SP — webservice próprio

| Serviço | Homologação | Produção |
|---|---|---|
| Status | `https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx` | `https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx` |
| **Autorização** | `https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx` | `https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx` |
| Ret. Autorização | `https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx` | `https://nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx` |
| Consulta Protocolo | `https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx` | `https://nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx` |
| Recepção Evento | `https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx` | `https://nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx` |

> **Outras UFs:** a lista oficial e sempre atualizada está no **Portal Nacional da
> NF-e** → menu *Serviços > Status Serviço / Webservices*
> (`https://www.nfe.fazenda.gov.br`). Adicionar uma UF = só estender o dict
> `SEFAZ_NFE_ENDPOINTS_POR_UF` no `sefaz_client.py`. NFCe-65 tem catálogo próprio
> (cada UF publica seus WS de NFCe separadamente).

No código, o catálogo fica assim (copiar do projeto-fonte):

```python
SEFAZ_NFE_ENDPOINTS_POR_UF = {
    "RJ": SEFAZ_RJ_NFE_ENDPOINTS,   # SVRS
    "SP": SEFAZ_SP_NFE_ENDPOINTS,   # WS próprio
}
# resolve o endpoint a partir da UF da empresa emitente + ambiente:
url = SEFAZ_NFE_ENDPOINTS_POR_UF[empresa.uf][ambiente]["autorizacao"]
```

### 7.4 Como a autenticação funciona (não tem token!)

Duas camadas, ambas baseadas no **certificado A1 da empresa**:

1. **mTLS (TLS mútuo) no transporte** — no handshake HTTPS, o cliente apresenta o
   **certificado da empresa** (extraído do `.pfx`). A SEFAZ valida que é um cert
   ICP-Brasil válido e do CNPJ credenciado. É isso que substitui "login".
2. **Assinatura digital do XML (XMLDSig)** — o XML da NFe é **assinado** com a
   mesma chave privada do `.pfx` (tag `<Signature>`). A SEFAZ confere a assinatura
   contra o CNPJ do `<emit>`. → É por isso que **o cert da matriz não emite a
   nota da filial** (`cStat=290`): o CNPJ do cert tem que bater com o emitente.

### 7.5 Detalhes técnicos da chamada (do código real — `post_sefaz`)

Particularidades que **fazem a diferença entre funcionar e tomar `Connection
reset`** — todas já resolvidas no `sefaz_client.py`:

- **SOAP 1.2** → `Content-Type: application/soap+xml; charset=utf-8`.
- **Sem header `SOAPAction`** separado — o SVRS reseta a conexão quando ele vai
  como header. (SOAP 1.2 permite `action="..."` dentro do Content-Type, mas o
  melhor resultado foi sem nenhum action.)
- **TLS legado obrigatório:** `SECLEVEL=1` + `OP_LEGACY_SERVER_CONNECT` +
  `minimum_version = TLSv1.2`. Sem isso, OpenSSL 3.x recusa o handshake
  (principalmente com a SEFAZ-SP).
- **Use `urllib3` direto, não `requests`** — o `requests` sobrescreve o
  `SSLContext` no `HTTPAdapter` e ignora as flags legadas.
- **`verify_ssl=True` em produção** exige o **cabundle ICP-Brasil** instalado
  (`apt-get install ca-certificates-acraiz-icpbrasil`). Em dev local,
  `verify_ssl=False`.
- **Retry com backoff (1s, 2s, 4s)** — o SVRS reseta a conexão intermitentemente
  (~20-30% com payload > 6KB). Reenvio é seguro: o mesmo `idLote` não duplica a
  nota (SVRS responde `cStat=204` se já processou).

Esqueleto do POST mTLS (resumo do `post_sefaz`):

```python
import ssl, urllib3
from urllib.parse import urlparse

def post_sefaz(url, soap_body, cert_pem, key_pem, *, timeout=60, verify_ssl=True):
    ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")                 # TLS legado SEFAZ
    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=cert_pem, keyfile=key_pem)  # <-- mTLS: cert da empresa

    p = urlparse(url)
    pool = urllib3.HTTPSConnectionPool(
        host=p.hostname, port=p.port or 443, ssl_context=ctx,
        cert_reqs="CERT_REQUIRED" if verify_ssl else "CERT_NONE",
        timeout=urllib3.Timeout(connect=10, read=timeout), retries=False,
    )
    r = pool.request("POST", p.path, body=soap_body.encode("utf-8"), headers={
        "Content-Type": "application/soap+xml; charset=utf-8",   # SOAP 1.2
        "Accept": "application/soap+xml, application/xml, */*",
    })
    return r.status, r.data.decode("utf-8", errors="replace")
```

O `.pfx` é convertido para PEM (cert + key) em arquivos temporários antes do
handshake, porque `load_cert_chain` precisa de arquivos em disco (função
`extract_cert_pem` no projeto-fonte). Em produção, grave esses PEMs num diretório
restrito (chmod 700) e apague-os com `try/finally` após o POST.

### 7.6 O envelope SOAP e o que vai dentro

Para autorizar, o corpo é: `soap_envelope("NFeAutorizacao4", enviNFe)` onde
`enviNFe` é o lote contendo a `<NFe>` **já assinada**:

```xml
<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
      <enviNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
        <idLote>123</idLote>
        <indSinc>1</indSinc>          <!-- 1 = síncrono: resposta imediata -->
        <NFe>... XML assinado com <Signature> ...</NFe>
      </enviNFe>
    </nfeDadosMsg>
  </soap12:Body>
</soap12:Envelope>
```

- `xmlns` do `<nfeDadosMsg>` = `http://www.portalfiscal.inf.br/nfe/wsdl/{servico}`.
- `indSinc=1` (síncrono) → a SEFAZ devolve o `<protNFe>` na mesma resposta. Foi o
  modo validado no smoke. (`indSinc=0` → consultar recibo depois via
  `NFeRetAutorizacao4`.)

### 7.7 Pipeline de uma emissão (protocolo SEFAZ ponta a ponta)

```
1. montar_xml_nfe(nota)        → XML da NFe 4.00 (não assinado)
2. assinar_xml(...)            → insere <Signature> XMLDSig com a key do .pfx
3. montar_enviNFe(...)         → embrulha em <enviNFe> (lote de 1, idLote=nNF)
4. soap_envelope("NFeAutorizacao4", enviNFe)  → envelope SOAP 1.2
5. post_sefaz(url, envelope, cert_pem, key_pem)  → POST mTLS
6. parse da resposta:
     <retEnviNFe><cStat>  = status do LOTE (104 = processado)
     <protNFe><infProt><cStat> = status da NOTA (100 = AUTORIZADA) + <nProt>
7. cStat=100 → grava chave + protocolo + XML autorizado (proc) no storage
```

Tudo isso já está no `emitter.py` — a sua camada só chama `emitir_nfe(nota, …)`.

### 7.8 Códigos de retorno (cStat) que você vai tratar

| cStat | Significado | Ação no worker |
|---|---|---|
| **100** | NFe **autorizada** | sucesso — grava protocolo + XML, job `concluido` |
| 103 | Lote recebido (assíncrono) | consultar recibo (`NFeRetAutorizacao4`) |
| 104 | Lote processado | ler o `<protNFe>` interno para o cStat real da nota |
| 204 / 539 | Duplicidade (chave/idLote já usado) | tratar como já emitida (idempotência) |
| 110 / 301 / 302 | Denegada (problema cadastral do dest.) | terminal — job `falhou` |
| 217 | NFe não consta (na consulta) | pode reenviar |
| **290 / 291 / 292** | Certificado inválido/vencido/revogado | terminal — cert errado (ver §7.4) |
| 225 / 215 | Falha de schema no XML | terminal — bug no `xml_builder`, job `falhou` |
| outros | rejeição de validação | terminal — registrar `xMotivo` e job `falhou` |

> Regra N-6: antes de **reenviar** (retry), o worker chama `NFeConsultaProtocolo4`
> com a chave. Se a SEFAZ já tem a nota como autorizada, **não reenvia** — evita
> duplicidade fiscal.

### 7.9 Particularidade da SEFAZ-SP (cipher mismatch)

A SEFAZ-SP costuma dar **cipher mismatch** no OpenSSL 3.0+. As flags
`SECLEVEL=1` + `OP_LEGACY_SERVER_CONNECT` (já no `_build_ssl_context`) resolvem.
Teste o handshake antes do go-live da empresa de SP:

```bash
openssl s_client -connect homologacao.nfe.fazenda.sp.gov.br:443 \
  -cert cert.pem -key key.pem -cipher 'DEFAULT@SECLEVEL=1' -tls1_2
```

Se ajustar o `/etc/ssl/openssl.cnf` global do servidor, lembre que isso afeta os
demais serviços que rodam na mesma máquina — prefira configurar no `SSLContext`
do processo (como o código faz), não no openssl.cnf global.

---

## 8. Endpoints REST (do seu backend)

Todos sob `/api/v1`. Autenticação resolve a **empresa** corrente em `auth.py`
(API key → empresa, ou usuário → empresa). Todo acesso filtra por `EMPRESA_ID`.

### Configuração de empresas (admin)

| Método | Rota | Função |
|---|---|---|
| POST | `/empresas` | cadastra empresa emitente |
| GET | `/empresas` | lista empresas |
| GET | `/empresas/{id}` | detalhe |
| PUT | `/empresas/{id}` | edita (inclui liberar produção) |
| POST | `/empresas/{id}/certificado` | registra `.pfx` + nome da env da senha + validade |
| POST | `/empresas/{id}/series` | cria série `(modelo, série, ambiente)` |
| GET | `/empresas/{id}/series` | lista séries |
| GET | `/empresas/{id}/status-sefaz` | `nfeStatusServico` da UF |

### Cadastros

| Método | Rota |
|---|---|
| GET/POST | `/produtos` · `/produtos/importar` (planilha) |
| GET/PUT | `/produtos/{id}` |
| GET/POST | `/clientes` · GET/PUT `/clientes/{id}` |
| GET/POST | `/transportadoras` · GET/PUT `/transportadoras/{id}` |

### Emissão fiscal

| Método | Rota | Retorno |
|---|---|---|
| POST | `/notas` | **202** + `job_id` (cria rascunho, reserva número, enfileira) |
| GET | `/notas` | lista paginada (filtros: empresa, modelo, status, período, busca) |
| GET | `/notas/{id}` | cabeçalho da nota |
| GET | `/notas/{id}/xml` | XML autorizado (`application/xml`) |
| GET | `/notas/{id}/danfe` | DANFE PDF (gera on-the-fly e cacheia) |
| POST | `/notas/{id}/cancelar` | `{justificativa}` (15–255 chars), dentro do prazo |
| POST | `/notas/{id}/carta-correcao` | CC-e (texto livre) |
| GET | `/jobs/{id}` | status do job (polling) |

### Catálogo

`GET /ref/ncm` · `GET /ref/cfop` · `GET /ref/csosn` · `GET /ref/municipios?uf=` ·
`GET /ref/aliquotas-interestaduais`

### Exemplo de payload — `POST /api/v1/notas`

```http
POST /api/v1/notas
Authorization: Bearer <api_key|jwt>
Idempotency-Key: 3f1c5e8a-...-uuid   (OBRIGATÓRIO)
Content-Type: application/json
```
```json
{
  "empresa_id": "EMP-UUID",
  "cliente_id": "CLI-UUID",
  "modelo": 55,
  "serie": 1,
  "ambiente": "homologacao",
  "natureza_operacao": "Venda de mercadoria",
  "finalidade": 1,
  "ind_presenca": 1,
  "ind_intermed": 0,
  "ind_final": 0,
  "transporte_modalidade": 9,
  "itens": [
    {
      "produto_id": "PROD-UUID",
      "quantidade": "2",
      "preco_unitario": "150.00",
      "cfop": "5102",
      "valor_frete": "0",
      "valor_desconto": "0"
    }
  ],
  "pagamentos": [
    { "forma_pag": "01", "valor": "300.00", "ind_pag": 0 }
  ],
  "info_complementar": "Pedido #1234"
}
```
Resposta:
```json
{ "job_id": "JOB-UUID", "nota_fiscal_id": "NOTA-UUID", "chave_acesso": "3326..." }
```
Polling: `GET /api/v1/jobs/{job_id}` →
`{ "status": "concluido", "chave_acesso": "...", "protocolo": "...", "danfe_url": "..." }`

---

## 9. Fluxo de emissão assíncrona

```
POST /api/v1/notas
   ├─ valida payload (Pydantic)
   ├─ valida Idempotency-Key (NFE_IDEMPOTENCIA)
   ├─ confere empresa e cliente (mesma empresa/tenant)
   ├─ NFE_NEXTVAL_SERIE → reserva número (lock de linha, curtíssimo)
   ├─ monta chave de acesso (44 díg.) em fiscal/chave.py
   ├─ INSERT NFE_NOTAS (status='rascunho') + INSERT itens (snapshot N-2)
   ├─ INSERT NFE_JOBS (status='pendente')
   ├─ COMMIT  → libera o lock
   └─ devolve 202 + job_id
                       │
                       ▼
         worker/runner.py (processo systemd separado, loop)
   ├─ SELECT ... FROM NFE_JOBS WHERE status='pendente'
   │      AND (proximo_retry_em IS NULL OR proximo_retry_em <= SYSTIMESTAMP)
   │      FOR UPDATE SKIP LOCKED   (1 job por vez, sem corrida entre workers)
   ├─ marca status='processando', tentativas += 1, COMMIT (separado)
   ├─ monta NotaEmissao a partir do banco
   ├─ se tentativas > 1 → consulta SEFAZ antes (regra N-6, evita duplicidade)
   ├─ emitir_nfe(...) → fala com a SEFAZ
   ├─ grava NFE_LOGS_SEFAZ (request+response) e NFE_NOTAS_EVENTOS
   ├─ autorizada (cStat=100): UPDATE NFE_NOTAS status='autorizada',
   │      chave, protocolo; grava XML+PDF no storage; job='concluido'
   ├─ rejeitada (FiscalError): job='falhou' (não reenvia)
   └─ SEFAZ fora (SefazError): job volta p/ 'pendente' + proximo_retry_em (backoff)
```

Pickup do worker no Oracle:

```sql
SELECT ID, NOTA_ID, EMPRESA_ID, TIPO, TENTATIVAS
  FROM NFE_JOBS
 WHERE STATUS = 'pendente'
   AND (PROXIMO_RETRY_EM IS NULL OR PROXIMO_RETRY_EM <= SYSTIMESTAMP)
 ORDER BY CRIADO_EM
 FETCH FIRST 1 ROWS ONLY
 FOR UPDATE SKIP LOCKED;
```

> **Watchdog (recuperação de zumbis):** um job preso em `processando` há mais de
> 5 min (worker morreu no meio) deve voltar a `pendente`. Faça isso no início de
> cada ciclo de pickup com um `UPDATE ... WHERE status='processando' AND
> processado_em < SYSTIMESTAMP - INTERVAL '5' MINUTE`.

---

## 10. Regras fiscais não-negociáveis

Traga estas regras do projeto-fonte — são defesas que evitam multa/duplicidade:

| Regra | O que é | Onde |
|---|---|---|
| **N-2 Snapshot fiscal** | item congela NCM/CFOP/CSOSN/preço/alíquota na emissão; editar o produto depois **não** altera nota emitida | `NFE_NOTAS_ITENS.*_SNAPSHOT` |
| **N-3 Idempotency-Key** | sem o header no POST de emissão → HTTP 400; cache 24h evita nota duplicada por retry de rede | `NFE_IDEMPOTENCIA` |
| **N-5 Numeração atômica** | número reservado sob lock; gaps aceitos | `NFE_NEXTVAL_SERIE` |
| **N-6 Consulta antes do retry** | antes de reenviar, consulta a SEFAZ pela chave; cStats terminais não reenviam | `fiscal/consulta.py` |
| **Append-only** | eventos e logs SEFAZ imutáveis após INSERT | triggers §5 |
| **Segredo fora do banco** | senha do cert e CSC só via env var | `CERT_PASS_ENV`, `CSC_TOKEN_ENV` |

### Regras tributárias (caso o seu cenário seja Simples Nacional, como o da MIG)

- **CSOSN** padrão `102` (sem permissão de crédito); `500` quando o produto tem ST.
- **ICMS** 18% padrão; tabela `NFE_REF_ALIQ_INTER` para DIFAL interestadual.
- **FECP** (ex. RJ 2%) aplicado automaticamente quando `ALIQUOTA_FECP > 0` e o
  produto não é `ISENTO_FECP`.
- **PIS/COFINS** não destacados (Simples recolhe no DAS) — CST 49/99.
- **IPI** não destacado na saída (comerciante, não industrial) — CST 53.
- **DIFAL** EC 87/2015 para venda B2C interestadual (4% importado / 7%/12% por
  região, partilha 100% destino).

> ⚠️ Se o regime das suas empresas **não** for Simples Nacional, a tributação
> muda (CST de ICMS em vez de CSOSN, PIS/COFINS destacados, etc.). Marque isso
> como ponto a esclarecer antes de implementar o `xml_builder` para Regime Normal.

---

## 11. Segredos: certificado A1 e CSC

- O `.pfx` de cada empresa fica em diretório do servidor com permissão restrita
  (ex.: `/opt/seu_backend/certificados/`, dono da aplicação, chmod 700).
- O banco guarda **só** `CERT_PATH` (caminho) e `CERT_PASS_ENV` (nome da env var).
- A senha real vai no EnvironmentFile do systemd (chmod 600) ou cofre. Exemplo:
  ```
  NFE_CERT_PASS_EMP_MATRIZ_RJ=«REDACTED»
  NFE_CSC_TOKEN_EMP_MATRIZ_RJ=«REDACTED»
  ```
- Em produção, `verify_ssl=True` exige o **cabundle ICP-Brasil** instalado:
  ```bash
  apt-get install ca-certificates-acraiz-icpbrasil && update-ca-certificates
  ```
- **SEFAZ-SP** pode exigir ajuste de cipher no OpenSSL 3.0+ (`SECLEVEL=1` +
  `MinProtocol=TLSv1.2`) — teste o handshake antes do go-live da empresa SP.
- Alerta de **cert vencendo**: job diário comparando `CERT_VALIDADE` com hoje.

---

## 12. Dependências Python

```
oracledb           # driver Oracle (python-oracledb) — substitui psycopg
signxml            # assinatura A1 (XMLDSig)
cryptography       # leitura do .pfx (PKCS#12)
lxml               # manipulação de XML
urllib3            # POST SOAP mTLS direto (sem zeep)
BrazilFiscalReport # geração de DANFE/DANFCE PDF
pydantic           # validação de payload
# + seu framework web atual (Flask/FastAPI) e seu pool de conexões
```

> Troca-chave em relação ao projeto-fonte: **`psycopg` (Postgres) → `oracledb`
> (Oracle)**. Toda a pasta `persistence/` é reescrita com `oracledb`; o resto
> permanece.

### Esqueleto do `persistence/db.py`

```python
import oracledb

_pool = oracledb.create_pool(
    user="SEU_USER", password="...", dsn="host:1521/service",
    min=2, max=10, increment=1,
)

def connect():
    return _pool.acquire()   # devolva com conn.close() (volta ao pool)
```

---

## 13. Checklist de go-live por empresa

- [ ] `INSERT NFE_EMPRESAS` com `PRODUCAO_LIBERADA = 0`.
- [ ] `.pfx` da empresa no servidor + env var da senha definida.
- [ ] Validade do certificado preenchida (`CERT_VALIDADE`).
- [ ] (NFCe) CSC + idCSC configurados (`CSC_ID`, `CSC_TOKEN_ENV`).
- [ ] Séries cadastradas em `NFE_SERIES` (homologação **e** produção).
- [ ] Cabundle ICP-Brasil instalado no servidor.
- [ ] (SP) handshake TLS testado contra a SEFAZ-SP.
- [ ] **Smoke homologação:** 1 NFe-55 + 1 NFCe-65 → `cStat=100`.
- [ ] DANFE/DANFCE PDF gerados e conferidos manualmente.
- [ ] Credenciamento da empresa confirmado na SEFAZ da UF.
- [ ] `UPDATE NFE_EMPRESAS SET PRODUCAO_LIBERADA = 1`.
- [ ] **Smoke produção:** 1 emissão real → `cStat=100` + cancelamento de teste.

---

## 14. Adequação à Reforma Tributária (IBS/CBS/IS)

> **Status no código-fonte:** ⚠️ **NÃO coberto.** O `NFE_VendasProduto` (e por
> tabela este guia) foi feito para o leiaute NFe **4.00 atual** (ICMS/FECP/CSOSN).
> Ele **não tem** os grupos IBS/CBS/IS. Esta seção é o plano de adequação.
> **Fonte oficial:** **NT 2025.002** (substitui a NT 2024.002) no Portal Nacional
> da NF-e — sempre confira a versão vigente e o XSD publicado antes de codificar.

### 14.1 O que muda

A EC 132/2023 + LC 214/2025 criam três tributos que passam a ser **destacados no
próprio XML** da NFe/NFCe:

- **CBS** — Contribuição sobre Bens e Serviços (federal) → substitui PIS/COFINS.
- **IBS** — Imposto sobre Bens e Serviços (estadual + municipal) → substitui ICMS/ISS.
- **IS** — Imposto Seletivo ("imposto do pecado": cigarro, bebida, etc.).

A NT 2025.002 acrescenta ao leiaute um **grupo de tributação IBS/CBS/IS por item**
+ um **grupo de totais**, além de eventos novos. Em 2025 o preenchimento é
opcional; a partir de 2026 as regras de validação passam a valer.

### 14.2 Cronograma — e o que vale para as SUAS empresas

| Data | Marco | A quem se aplica |
|---|---|---|
| 2025 | Campos disponíveis em homologação/produção (preenchimento **opcional**) | todos |
| **2026** | **Ano de teste** — emitir conforme as NTs **dispensa o recolhimento** de IBS/CBS | todos |
| **01/07/2026** | **Homologação obrigatória** dos campos IBS/CBS | **CRT 3 (Regime Normal)** |
| **🔴 03/08/2026** | **Produção obrigatória** dos campos IBS/CBS | **CRT 3 (Regime Normal)** |
| 01/09/2026 | Devolução passa a exigir referência via `DFeReferenciado` | conforme NT |
| 03/11/2026 | Produção da tributação **monofásica** reformulada (combustíveis) | setores específicos |
| **🔴 04/01/2027** | **Obrigatoriedade** dos campos IBS/CBS/IS | **CRT 1 / 2 / 4 — Simples Nacional, excesso, MEI** (Art. 348 LC 214/2025) |
| 2027 | CBS plenamente vigente; **PIS/COFINS extintos**; **IS** inicia | todos |

> **Tradução para o seu caso:** os marcos que você perguntou são exatamente estes.
> - Se a empresa for **Regime Normal (CRT 3)** → preparar para **agosto/2026**.
> - Se for **Simples Nacional / EPP / MEI (CRT 1/2/4)** — como as empresas do tipo
>   MIG — a obrigatoriedade é **janeiro/2027**. (No projeto-fonte as empresas são
>   Simples EPP, CRT 1 → janela jan/2027.)
>
> Em ambos os casos, **2026 é ano de teste**: vale começar a emitir já com os
> campos preenchidos em homologação para validar o `xml_builder` cedo.

### 14.3 Novos grupos e campos do XML (NT 2025.002)

Por item (Grupo **UB** — "Informações dos tributos IBS/CBS e Imposto Seletivo"):

| Grupo / campo | O que é |
|---|---|
| `CST` (IBS/CBS) | Código de Situação Tributária dos novos tributos (≠ CST do ICMS) |
| `cClassTrib` | Código de Classificação Tributária (define o tratamento) |
| `gIBSUF` → `pIBSUF`, `vIBSUF` | alíquota e valor do **IBS estadual** |
| `gIBSMun` → `pIBSMun`, `vIBSMun` | alíquota e valor do **IBS municipal** |
| `gCBS` → `pCBS`, `vCBS` | alíquota e valor da **CBS** |
| `gIS` → `vIS` | **Imposto Seletivo** |
| `gIBSCBSMono` | tributação **monofásica** |
| `gAjusteCompet`, `gEstornoCred`, `gCredPresOper` | ajustes de competência, estorno e crédito presumido |
| `vBC` | base de cálculo dos novos tributos |
| `indDoacao`, `pDevTrib` | natureza de doação e **cashback** (devolução de tributo) |

Totais (Grupo **W03** — "Total da NF-e IBS/CBS/IS"): somatórios de `vIBSUF`,
`vIBSMun`, `vCBS`, `vIS` no nível da nota. E o Grupo **VC** (`DFeReferenciado`)
para referenciar itens por chave (devolução).

> ⚠️ **Não fixe códigos de CST/cClassTrib de memória.** A tabela de `cClassTrib`
> e os CST do IBS/CBS são publicados junto da NT e ainda recebem revisões
> (v1.30 → v1.40 → v1.50…). Trate-os como **tabela de catálogo** carregada da NT
> vigente, igual aos `NFE_REF_*`.

### 14.4 Impacto no schema Oracle (ALTER TABLE)

Os novos valores entram no **snapshot por item** (regra N-2 continua valendo) e
nos totais da nota. Como o preenchimento é faseado/opcional, todas as colunas são
**nullable**:

```sql
-- Snapshot IBS/CBS/IS por item
ALTER TABLE NFE_NOTAS_ITENS ADD (
    CST_IBSCBS_SNAPSHOT     CHAR(3),        -- CST dos novos tributos
    CCLASSTRIB_SNAPSHOT     VARCHAR2(6),    -- código de classificação tributária
    V_BC_IBSCBS             NUMBER(15,2),   -- base de cálculo IBS/CBS
    P_IBS_UF                NUMBER(7,4),    -- alíquota IBS estadual
    V_IBS_UF                NUMBER(15,2),
    P_IBS_MUN               NUMBER(7,4),    -- alíquota IBS municipal
    V_IBS_MUN               NUMBER(15,2),
    P_CBS                   NUMBER(7,4),    -- alíquota CBS
    V_CBS                   NUMBER(15,2),
    V_IS                    NUMBER(15,2),   -- Imposto Seletivo
    P_DEV_TRIB              NUMBER(7,4)     -- cashback (pDevTrib)
);

-- Totais IBS/CBS/IS na nota
ALTER TABLE NFE_NOTAS ADD (
    V_TOT_IBS_UF            NUMBER(15,2),
    V_TOT_IBS_MUN           NUMBER(15,2),
    V_TOT_CBS              NUMBER(15,2),
    V_TOT_IS               NUMBER(15,2)
);

-- Catálogo de classificação tributária (carregar da NT vigente)
CREATE TABLE NFE_REF_CCLASSTRIB (
    CCLASSTRIB   VARCHAR2(6)  PRIMARY KEY,
    CST          CHAR(3),
    DESCRICAO    VARCHAR2(300),
    VIGENCIA_INICIO DATE
);

-- Versão de leiaute aplicada por empresa (controle do faseamento)
ALTER TABLE NFE_EMPRESAS ADD (
    LAYOUT_RT_ATIVO    NUMBER(1)    DEFAULT 0 NOT NULL,  -- 1 = já emite com IBS/CBS
    NT_VERSAO          VARCHAR2(10)                       -- ex.: '2025.002 v1.50'
);
```

### 14.5 Impacto no código

| Camada | Mudança |
|---|---|
| `fiscal/xml_builder.py` | gerar o **Grupo UB** (IBS/CBS/IS) por item + **Grupo W03** (totais), conforme o XSD da NT vigente. Condicional ao CRT/data (faseamento). |
| `fiscal/models.py` | acrescentar campos IBS/CBS/IS ao `ItemEmissao` e aos totais de `NotaEmissao`. |
| Validação | baixar o **XSD novo** da SEFAZ e validar o XML em homologação antes de transmitir. |
| Cálculo tributário | motor que decide `CST`/`cClassTrib` e alíquotas IBS/CBS por operação (provavelmente o ponto mais complexo — alíquotas de referência ainda em definição pelos entes). |
| Eventos | a NT cria eventos novos (ex.: crédito, perecimento) — fora do mínimo de emissão. |

### 14.6 Estratégia recomendada

1. **Agora:** deixar o schema preparado (rodar os `ALTER TABLE` da §14.4) e tratar
   `cClassTrib`/CST como catálogo versionado.
2. **2026 (ano de teste):** implementar o Grupo UB no `xml_builder` atrás de uma
   flag por empresa (`LAYOUT_RT_ATIVO`) e emitir em **homologação** com os campos
   preenchidos — valida cedo, sem risco (recolhimento dispensado).
3. **Ligar produção** conforme o CRT da empresa: **CRT 3 → 03/08/2026**;
   **CRT 1/2/4 → 04/01/2027**.
4. **Versão da NT:** registre em `NFE_EMPRESAS.NT_VERSAO` qual versão do leiaute o
   `xml_builder` implementa, e acompanhe as revisões no portal.

**Fontes:**
- [Portal Nacional da NF-e — Reforma Tributária / NT 2025.002 (oficial)](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY%3D)
- [Adequações NF-e/NFC-e — Reforma Tributária do Consumo (PDF oficial)](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=AklZnck3o6I%3D)
- [Receita Federal — Orientações da Reforma Tributária para 2026](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-consumo/orientacoes-2026)
- [SEFAZ-AM — campos IBS/CBS obrigatórios (jan/2026)](https://www.sefaz.am.gov.br/noticias/31893)
- [Análise NT 2025.002 v1.40/v1.50 — cronograma por CRT (NS Tecnologia)](https://blog.nstecnologia.com.br/reforma-tributaria-nfe/)
- [Tecnospeed — grupos e campos IBS/CBS/IS da NT 2025.002](https://blog.tecnospeed.com.br/nota-tecnica-reforma-tributaria-nfe-nfce/)

> ⚠️ Datas e campos refletem a NT 2025.002 nas versões públicas até jun/2026 e
> **ainda sofrem revisão**. Antes de implementar, baixe a versão vigente da NT e
> o XSD no Portal Nacional da NF-e.

---

## Pontos a esclarecer antes de implementar (⚠️)

1. **Regime tributário das empresas:** Simples Nacional (CSOSN) ou Regime Normal
   (CST + PIS/COFINS/IPI destacados)? Muda o `xml_builder`.
2. **Identidade/empresa:** `NFE_EMPRESAS` é independente ou referencia uma tabela
   mestre de empresas que você já tem?
3. **Autenticação:** como o seu backend autentica hoje (JWT próprio? API key?) —
   `auth.py` precisa se encaixar nisso para resolver a empresa corrente.
4. **Storage de XML/PDF:** filesystem do servidor (como no projeto-fonte) ou
   algum object storage?
5. **UFs a suportar além de RJ/SP:** cada nova UF exige só estender o catálogo de
   endpoints em `sefaz_client.py`.
```

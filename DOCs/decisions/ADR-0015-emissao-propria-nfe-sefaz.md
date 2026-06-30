# ADR-0015 — Emissão própria de NF-e direto à SEFAZ (mTLS + XMLDSig), substituindo o provedor Focus

**Data:** 2026-06-29
**Status:** Aceito (implementado — pendente smoke em homologação RJ/SP)
**Decisores:** Vinicius (proprietário)

## Contexto

A emissão fiscal manual (entrada/saída) e o recebimento de NF-e (DFe) usavam a **API
Focus NFe** como intermediário. O dono decidiu trazer a emissão para dentro do sistema,
comunicando-se **diretamente com os webservices da SEFAZ** (NFe 4.0), para autonomia,
redução de custo de SaaS e controle do ciclo fiscal. Há um sistema-fonte do mesmo grupo
(`NFE_VendasProduto`) já validado em produção (cStat=100) cuja camada `fiscal/` foi
**portada e reescrita** no padrão do Sistema Drop.

A NF-e dos **pedidos de marketplace** NÃO usa Focus — vem do Faturador ML (XMLs já
autorizados, ADR-0008). Esse caminho é preservado. Esta decisão cobre apenas a emissão
**manual** e o recebimento próprio.

A correção fiscal foi validada pelo agente Consultor-Fiscal-NFE: para Simples Nacional
(CRT 1, caso das CMIGs) — CSOSN 102/500, PIS/COFINS **CST 99** zerado, **sem grupo IPI**,
**sem ICMSUFDest/DIFAL de partilha** (STF Tema 1093). UFs iniciais: RJ (via SVRS) e SP
(webservice próprio).

## Decisões

### 1. Camada fiscal pura + adaptador

- `services/fiscal/sefaz/` — Python puro, sem ORM/rede além da SEFAZ: `chave` (DV mód 11),
  `xml_builder` (NFe 4.00), `signer` (XMLDSig SHA-1 via `signxml`, X509 só do emissor),
  `sefaz_client` (SOAP 1.2 + mTLS via `urllib3`, TLS legado `SECLEVEL=1` + `OP_LEGACY`),
  `emitter`, `consulta` (N-6), `cancelamento` (110111 + CC-e 110110 + manifestação),
  `inutilizacao`, `danfe` (BrazilFiscalReport), `distribuicao` (ver ADR-0016).
- `services/fiscal/sefaz_service.py` — adaptador que monta `NotaEmissao` a partir de
  `Invoice`/`CMIG`/`Person`/`CMIGProduct`, persiste o resultado e grava log SEFAZ. As
  chamadas bloqueantes rodam em `asyncio.to_thread` (não bloqueiam o event loop).
- **Reuso do schema existente** (não recriar): `CMIG`+`CMIGFiscalConfig`=emitente,
  `Person`=destinatário, `Invoice`/`InvoiceItem`=nota, `InvoiceEvent`=eventos. Colunas
  novas aditivas (migrations 115/116/118): protocolo/cStat/ambiente/`emission_provider`,
  série manual, `cmigs.ibge_code`, `invoice_sefaz_logs` (append-only/imutável).

### 2. Série específica configurável, separada do marketplace

- A emissão manual usa `CMIGFiscalConfig.manual_nfe_serie` (distinta de `nfe_serie` do
  Faturador ML — validação anticolisão no PATCH da config). Numeração atômica por
  PL/SQL `NFE_NEXTVAL_MANUAL(cmig, ambiente)` sob `SELECT ... FOR UPDATE`, desdobrada por
  ambiente (produção x homologação) para não queimar números de produção em testes.

### 3. Transmissão SÍNCRONA (indSinc=1), não fila/worker

- A nota é transmitida **dentro do request** (commit do número curto → chamada SEFAZ via
  `to_thread`). Justificativa: instância Oracle Free única + APScheduler in-process + PM2,
  volume manual baixo — não se quis um worker/systemd novo. A nota fica em `processing` se
  a rede cair e é **recuperável** por consulta N-6 (`refresh-status`) e pelo job
  `fiscal_alerts._refresh_stale_invoices`. Fila assíncrona fica como evolução futura.

### 4. Cofre do certificado A1 (senha cifrada no banco)

- O `.pfx` de cada CMIG fica em diretório restrito **fora de `static/`** (`NFE_CERTS_DIR`,
  chmod 600). A **senha** é cifrada com **Fernet** (`cert_crypto.py`), chave derivada por
  SHA-256 de `settings.NFE_CERT_MASTER_KEY` (env var, nunca commitada). O banco guarda só o
  token cifrado (`cmig_fiscal_config.cert_pass_encrypted`) — nunca a senha em claro.
- O **XML autorizado** (procNFe) é gravado em `NFE_XML_DIR` (também fora de `static/`) — é
  dado fiscal/LGPD de terceiros; só é baixável pelo endpoint autenticado
  `GET /invoices/{id}/xml`. **Nunca** servir XML/.pfx pelo mount estático.
- TLS é **sempre verificado em produção** (`verify_ssl=True` quando `environment=producao`,
  anti-MITM no mTLS), exigindo o cabundle ICP-Brasil no servidor.

## Consequências

- **Positivas:** autonomia fiscal, sem custo/limite de SaaS, log SOAP completo (auditoria 5
  anos), controle de numeração/eventos, correções fiscais sob nossa governança.
- **Negativas / responsabilidades novas:** credenciamento da empresa na SEFAZ por UF;
  cabundle ICP-Brasil no deploy; manutenção do catálogo de endpoints por UF; a latência da
  SEFAZ acopla ao request (mitigada por retry + recuperação N-6); **perder a
  `NFE_CERT_MASTER_KEY` inutiliza as senhas cifradas** (backup seguro obrigatório).
- **Go-live faseado por empresa** (`production_released`): só emite produção após smoke em
  homologação (cStat=100 RJ e SP) + credenciamento confirmado.

## Preserva / referencia

- ADR-0008 (NF-e batch ML), ADR-0009 (devolução NF-e-driven), ADR-0010 (FULL sempre CMIG):
  **inalteradas** — a emissão própria é só dos lançamentos manuais, série separada, sem
  tocar nos ciclos de estoque/devolução/Faturador ML.
- ADR-0013 (UTC no armazenamento, conversão na borda): a `dhEmi` do XML usa
  `to_br(issue_date)` (America/Sao_Paulo com offset), armazenamento permanece UTC.
- Reforma Tributária (IBS/CBS/IS): fora do escopo (CRT 1 obriga só jan/2027); schema já
  preparado (`InvoiceItem`, migration 98).

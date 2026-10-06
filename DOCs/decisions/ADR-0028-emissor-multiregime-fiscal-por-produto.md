# ADR-0028 — Emissor NF-e multi-regime + codificação fiscal por produto

**Status:** Aceito
**Data:** 2026-10-06
**Emenda:** [ADR-0015](ADR-0015-emissao-propria-nfe-sefaz.md) (emissão própria SEFAZ — escopo de regime)
**Relacionada:** [ADR-0027](ADR-0027-rastreabilidade-lote-validade-serial.md) (padrão de snapshot imutável do item na emissão)

## Contexto

A emissão própria SEFAZ (ADR-0015) cobria **apenas Simples Nacional**: o `xml_builder` só montava `ICMSSN102/500`, PIS/COFINS CST 99 zerado, sem IPI, e `ICMSTot` todo zerado. Uma CMIG de **Regime Normal** (Lucro Presumido/Real, CRT 3) **não conseguia emitir NF-e correta**. Além disso, o CST/CSOSN era **hardcoded por regime** no `tax_calculator` (102 p/ Simples, 00 p/ Normal) e esse resultado nem chegava ao emissor — cada produto não tinha como ter a sua tributação. Pedido do dono (PEGORARO, farmacêutica Lucro Real): codificação **por produto** (monofásico, ST, redução de base convivendo na mesma empresa).

## Decisão

### 1. Codificação fiscal por produto, com default na CMIG e fallback (modelo da cascata)
- **Produto** (CMIGProduct/CatalogProduct, migration 147) ganha campos fiscais nullable: `cfop`, `icms_cst`, `icms_aliquota`, `icms_reducao_bc`, `fcp_aliquota`, `pis_cst`, `cofins_cst`, `pis_aliquota`, `cofins_aliquota`, `ipi_cst`, `ipi_aliquota`, `ipi_cenq`, `ibscbs_cst`, `cclasstrib`, `cbenef`, `mot_des_icms`. Reusa `ncm`/`cest`/`csosn`/`origin`.
- **CMIGFiscalConfig** ganha `default_*` (o padrão "por atividade").
- **Resolução em cascata** (`services/fiscal/fiscal_resolver.py`): para cada campo, **produto → default da CMIG → fallback**. Ramifica por `cfg.crt` (CRT 1/2/4 = Simples usa CSOSN; CRT 3 = Normal usa CST). **Falha alto**: CRT 3 sem CST de ICMS (produto e default) **bloqueia** a emissão (não chuta alíquota) — regra "falhar alto" do CLAUDE.md.
- **Snapshot imutável na criação da nota**: a cascata grava os códigos resolvidos nas colunas fiscais do `InvoiceItem` em `create_invoice_from_order`/`add_item` (só preenche vazio — edição manual vence), congelando a tributação como a ADR-0027 faz com rastro/med. A migration 148 alinhou o `invoice_items` com os campos do snapshot (`icms_reducao_bc`, `fcp_*`, `mot_des_icms`, `cbenef`, `ipi_cenq`).

### 2. Emissor multi-regime (`xml_builder`)
- **Simples permanece byte-idêntico** (ICMSSN102/500 + PIS/COFINS 99 + ICMSTot zerado) — ramo intocado, provado por teste de identidade. Zero regressão.
- **Regime Normal (CRT 3):** grupos `ICMS00/20/40/41/50/60` (+ `ICMS90` como fallback válido p/ 10/70/90), grupo `IPI` (quando houver CST de IPI), **PIS/COFINS reais** por CST (`PISAliq`/`COFINSAliq` p/ 01/02; `PISNT`/`COFINSNT` p/ 04/06/07/08/09 monofásico/zero; `PISOutr`/`COFINSOutr` p/ 49/99), `cBenef`/`motDesICMS` quando presentes, e `ICMSTot` com **somatórios reais** dos itens.
- `Produto` (sefaz/models.py) valida **CSOSN (3 díg) XOR icms_cst (2 díg)** — nunca os dois. O builder recusa nota que **misture** CSOSN e CST.

### 3. Reforma Tributária (IBS/CBS/IS) — GATED
O cadastro já guarda `ibscbs_cst`/`cclasstrib` por produto. Os **grupos IBS/CBS/IS no XML NÃO são emitidos no modo `legacy`** (default de `tax_regime_mode`) — só entrarão sob `transition`/`reform`, confirmando a **NT vigente** (o leiaute evolui 2026→2033). Assim a nota permanece válida hoje.

## Consequências

- **Positivo:** NF-e correta por regime e por produto (o caso PEGORARO: 89 itens ST/CST 60, 87 monofásico PIS/COFINS 04, redução de base, cBenef). Simples intocado. Tributação é snapshot imutável na emissão.
- **Fases futuras (registradas):** `ICMS10/70` completos (hoje caem em `ICMS90` genérico válido); **DIFAL/partilha** B2C inter-UF no Regime Normal; **grupos IBS/CBS/IS** no XML (ativar com a NT vigente); NFC-e 65.
- **Pré-requisito operacional:** para uma CMIG emitir em Regime Normal faltam os dados fiscais dela (CRT=3, IE, IBGE, série manual, ambiente) e o **certificado A1** — setup do dono/contador. **Validar em homologação (cStat 100) antes de produção.**

## Verificação

19 testes (`tests/test_emissor_multiregime.py`), incl. round-trip real item→resolve→snapshot→emissão provando CST 20 com `pRedBC=65`/vBC reduzido/`cBenef`, e **zero-regressão Simples byte-a-byte** (CSOSN 102 e 500 idênticos ao histórico). Auditado (quality-guardian — HIGH de colunas faltantes corrigido pela migration 148; adr-consistency-checker — conforme ADR-0015/0027).

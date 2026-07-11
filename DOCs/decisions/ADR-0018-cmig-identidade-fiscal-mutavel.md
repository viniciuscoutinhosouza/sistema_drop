# ADR-0018 — Identidade fiscal da CMIG é mutável (conversão CPF ⇆ CNPJ)

**Data:** 2026-07-11
**Status:** ✅ Aceito
**Decisores:** Vinicius (proprietário)

## Contexto

Uma CMIG nasce como **Pessoa Física (CPF + Nome)** ou **Pessoa Jurídica (CNPJ + Razão Social)** —
exatamente um documento (`CMIGCreate` valida mutualidade). Até aqui a identidade fiscal era, na
prática, **imutável**: o `update_cmig` usava `model_dump(exclude_none=True)`, o que torna
**impossível limpar** o CPF (enviar `cpf: null` é descartado), e o formulário só oferecia *adicionar*
CNPJ mantendo o CPF — o que deixaria a conta com **os dois documentos**, violando a regra de criação.

Vendedores que se cadastraram como CPF e depois **formalizaram como empresa** (ou erraram o tipo no
cadastro) precisam converter a conta para CNPJ. O tipo fiscal governa o fluxo de documento fiscal:
`_order_issuer_type` (`routers/orders.py`) decide **live** — `cnpj` presente → NF-e (PJ); senão
`cpf` → DC-e (PF). ADR-0015/0016/0017 assumiam esse tipo estável.

## Decisão

A identidade fiscal da CMIG passa a ser **mutável, por substituição** (não aditiva): converter troca
o documento e **zera o anterior**, preservando o invariante "exatamente um de CPF/CNPJ".

- **Backend (`update_cmig`):** o documento é tratado **fora** do `exclude_none`, a partir de
  `model_fields_set`. Um normalizador em `CMIGUpdate` transforma `''`/espaços em `None` mas mantém o
  campo em `fields_set` — é isso que distingue "quero zerar o CPF" de "não mexi no CPF". Valida o
  **estado final** (exatamente um documento), checa unicidade e seta ambos os campos explicitamente
  (permitindo limpar o antigo). Razão Social é obrigatória para PJ.
- **Autorização:** alterar o **tipo** fiscal exige papel `ac`/`admin` (paridade com a criação).
  Edições que não tocam no documento seguem abertas ao acesso normal (incl. UGO do galpão).
- **Pré-requisitos PJ:** converter **CPF→CNPJ** exige **IE** (mora em `CMIGFiscalConfig.ie`) e
  **código IBGE** (`cmigs.ibge_code`) — informados no próprio formulário; a IE é upsertada no
  `fiscal_config`. Assim a PJ nasce apta ao próximo passo fiscal (não emite NF-e sem IE/IBGE).
- **Efeitos colaterais são AVISADOS, não bloqueados** (decisão do proprietário — a conta a converter
  costuma ser cadastro novo/errado, sem histórico real):
  - Pedidos **ainda pendentes** de documento fiscal passam a exigir o documento do **novo** tipo
    (regime `live`). Documentos **já emitidos** ficam intactos — são snapshot histórico
    (`order_dce.emit_cpf`, `invoices`), nunca reinterpretados.
  - Integração **eShip**: o cadastro no WMS é filtrado por CPF/CNPJ; após converter é preciso
    **recadastrar** os produtos na nova identidade (o `EShipCreds` hoje só carrega `cnpj`).
  - O tipo de pessoa da **conta no marketplace** não muda por aqui — uma conta ML-CPF continua
    exigindo DC-e no ML independentemente do cadastro interno.

## Consequências

- **Positivas:** correção/formalização de conta sem recriar CMIG (que arrastaria produtos, anúncios,
  pedidos e config). Invariante "exatamente um documento" agora vale também na atualização.
- **Negativas / riscos:** conversão com operação em andamento pode gerar recadastro no eShip e mudar
  o regime de pedidos pendentes. Mitigado por avisos explícitos no formulário. Emitir NF-e como PJ
  ainda depende de credenciamento SEFAZ + `production_released` (ADR-0015), fora do escopo da
  conversão.
- **Sem migration:** `cnpj`/`cpf` já eram `nullable` e `unique` (migration 49); no Oracle o UNIQUE
  aceita múltiplos `NULL`, então limpar o documento antigo é seguro.

## Alternativas consideradas

- **Bloquear a conversão quando há histórico (eShip com saldo / pedidos pendentes):** rejeitada pelo
  proprietário em favor de "só avisar", por atrito operacional; o snapshot histórico já protege
  documentos emitidos.
- **Upgrade aditivo (manter CPF e adicionar CNPJ):** rejeitada — deixa os dois documentos, viola o
  invariante de criação e torna o `_order_issuer_type` ambíguo (hoje o `cnpj` venceria silenciosamente).

## Arquivos

- `BACKEND/schemas/cmig.py` — `CMIGUpdate` (normalizador `''→None`, campos `ie`/`ibge_code`); `CMIGOut` (`ibge_code`).
- `BACKEND/routers/cmigs.py` — `update_cmig` (tratamento explícito de documento + gate de tipo + IE/IBGE na conversão).
- `FRONTEND/src/views/cmig/CmigFormView.vue` — toggle PJ/PF na edição, aviso de impacto, campos IE/IBGE na conversão.
- `BACKEND/tests/test_cmig_conversion.py` — invariantes do normalizador que habilitam limpar o documento.

# ADR-0016 — Distribuição de DFe própria (Ambiente Nacional) com controle de NSU por CMIG

**Data:** 2026-06-29
**Status:** Aceito (implementado — pendente smoke em homologação)
**Decisores:** Vinicius (proprietário)

## Contexto

Ao sair do Focus (ADR-0015), o recebimento de NF-e de fornecedores (entrada) — que vinha
do `list_received`/`download` do Focus — precisava de uma fonte própria. O guia portado
não cobria isso. A SEFAZ expõe o webservice **NFeDistribuicaoDFe** no **Ambiente Nacional**
(não por UF) para o destinatário puxar os documentos emitidos contra seu CNPJ.

## Decisões

### 1. Pull via NFeDistribuicaoDFe (distNSU), controle de NSU por CMIG

- `services/fiscal/sefaz/distribuicao.py` monta `distDFeInt` **versão 1.01** (envelope
  `nfeDistDFeInteresse > nfeDadosMsg > distDFeInt`), consulta por `distNSU/ultNSU` e
  decodifica os `docZip` (base64 + gzip). Estrutura confirmada na NT 2014.002 (Portal NF-e).
- O **último NSU** processado é persistido por CMIG em `cmig_fiscal_config.ultimo_nsu`. O
  job `sync_dfe` (`dfe_service.sync_received_for_cmig`) itera `ultNSU → maxNSU` em lotes
  **bounded** (máx. 20 por execução) e cria `Invoice direction='in'` para NF-e completas
  novas (dedup por NSU em `dfe_recebidos` e por chave em `invoices`).

### 2. Rate-limit e classificação de documentos

- Quando `ultNSU == maxNSU` (sem novos), **não reconsultar antes de ~1h**. `cStat 656`
  (consumo indevido) é tratado como "aguardar", não erro terminal. `138` = docs
  encontrados, `137` = nenhum documento.
- Os `docZip` vêm com `schema` (`procNFe`/`resNFe`/`resEvento`/`procEventoNFe`): NF-e
  completa vira Invoice; resumo/evento é só registrado em `dfe_recebidos`.

### 3. Manifestação do destinatário própria

- Eventos de manifestação (Ciência 210210, Confirmação 210200, Desconhecimento 210220,
  Operação não realizada 210240) são enviados via `RecepcaoEvento4` ao **Ambiente Nacional**
  (`cOrgao=91`, endpoint `SEFAZ_EVENTO_AN`). Desconhecimento/Operação não realizada exigem
  justificativa (15–255 chars).

### 4. Segurança do parsing (conteúdo de terceiros)

- O `docZip` é gerado por terceiros (emitentes contra o CNPJ) → conteúdo **não confiável**.
  O parser lxml é endurecido (`resolve_entities=False, no_network=True, huge_tree=False` —
  anti billion-laughs/XXE) e a descompressão tem **teto de 8 MB por documento** (anti
  zip-bomb), com leitura em stream.

## Consequências

- Recebimento de NF-e deixa de depender de terceiro; integra ao ciclo NF-e-driven
  (ADR-0009) sem alterá-lo (`update_stock_from_invoice`, débito FULL via ADR-0010
  preservados). O valor `inbound_source='dfe_focus'` foi mantido como **legado** (já existe
  em dados/constraint/UI) — relabel só na exibição.
- **A confirmar em homologação** (não testável sem certificado + AN): os endpoints AN
  (`SEFAZ_DFE_AN`, `SEFAZ_EVENTO_AN`) e a `versao=1.01` do `distDFeInt` — ajustáveis no
  catálogo sem mudança de lógica.
- Respeitar o intervalo de consulta evita bloqueio por consumo indevido (656).

## Referencia

- ADR-0015 (emissão própria — mesma camada/cofre de certificado), ADR-0009 (devolução
  NF-e-driven), ADR-0010 (FULL sempre CMIG).

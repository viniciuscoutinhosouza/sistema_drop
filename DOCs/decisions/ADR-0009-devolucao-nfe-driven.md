# ADR-0009 — Devolução NF-e-driven: NF-e fiscal-only + contadores de inspeção como fonte canônica

**Data:** 2026-06-17
**Status:** Aceito (implementado — Fase B)
**Decisores:** Vinicius (proprietário)

## Contexto

A Devolução física (`models.return_.Return` + `routers/returns.py`, ADR-0005/ADR-0007)
ganhou um modo **dirigido por NF-e**: o operador importa o XML da NF-e de devolução
(ou, futuramente, sincroniza do ML), o sistema casa o pedido original pela NF-e
referenciada (`refNFe → Order.nfe_key`) e registra a devolução para inspeção. O operador
marca **apto** (volta ao estoque vendável) ou **não apto** (vai para descarte). A
quantidade considerada é a da NF-e (suporta devolução parcial).

Isso colide com o **estoque LOCAL event-sourced** (ADR-0004): `stock_quantity` é um cache
recomputado a partir do replay das NF-e (`stock_calculator.recompute_after_invoice_change`).
O replay só inclui uma `Invoice` quando **`stock_updated == True`** e
`status in (authorized, finalized)` — ou seja, `stock_updated=True` é condição de
**inclusão** no recompute, não de exclusão.

Dois problemas surgem se a NF-e de devolução participar do replay:
1. **Dupla contagem no apto:** a NF-e de entrada somaria `nfe_in` no recompute *e* a
   validação somaria via UPDATE direto — o produto entraria duas vezes.
2. **Fura o portão de inspeção:** o event-sourcing não modela "aguardando inspeção";
   se a NF-e fosse contada no ingest, o produto viraria vendável **antes** da conferência.

## Decisão

**A NF-e de devolução e a nota de descarte são documentos puramente fiscais, inertes ao
recompute; os contadores de inspeção (UPDATE direto) são a fonte canônica do estoque.**

- **NF-e de devolução** (`_ingest_devolution`): criada com `purpose='devolucao'`,
  `status='authorized'` e **`stock_updated=False`** → o recompute a ignora por completo.
  Os itens recebem `source_type`/FK via `_resolve_item_match` apenas para que
  `receive_return_items`/`validate_return_items` saibam qual produto mexer — não para o replay.
- **Recebimento** (`receive_return_items`): `pending_validation_quantity += qty` (não vendável).
- **Validação apto** (`validate_return_items`, approved): `pending−`, `stock_quantity+`
  (UPDATE direto) + `schedule_push`. **É aqui — e só aqui — que o estoque vendável sobe.**
- **Validação não apto:** `pending−`, `unfit_quantity+` (fora do vendável). Gera uma
  **nota de descarte** (`_create_discard_note`): `purpose='ajuste'`, `direction='out'`,
  `status='finalized'`, **sem transmissão à SEFAFZ** e **`stock_updated=False`** →
  documento fiscal inerte ao recompute. A baixa já ocorreu via `unfit_quantity`.
- **Idempotência:** `receive_return_items`/`validate_return_items` guardam por
  `StockMovement.return_id + movement_type` antes de mutar.
- Mantém **paridade com o caminho legado** `validate_return` (devolução por pedido), que
  já usava contadores UPDATE direto — nunca foi event-sourced.

### Regra geral derivada

Um documento fiscal é **inerte ao recompute** quando `stock_updated=False`. Esta é a
forma canônica de registrar uma NF-e fiscal-only (que não deve afetar `stock_quantity`).
Não confiar em "itens sem `source_type`/FK/EAN" como mecanismo de inércia — o filtro
real do replay é `Invoice.stock_updated == True`.

## Consequências

- Contadores `pending_validation_quantity`/`unfit_quantity` permanecem fora do
  event-sourcing (coerente com ADR-0004, que só event-sourcia `stock_quantity`/`reserved_quantity`).
- `available_quantity = stock_quantity − reserved_quantity` (unfit/pending não entram no disponível).
- O recompute pode rodar a qualquer momento sem desfazer a devolução: as NF-e de
  devolução/descarte são invisíveis a ele; o efeito vive em `stock_quantity` (apto) ou
  `unfit_quantity` (não apto), aplicado uma única vez.
- Trilha fiscal preservada: as NF-e existem como documentos (aparecem nas listagens
  fiscais), apenas não movem o cache de estoque.

## Pendências conhecidas (fora do escopo deste incremento)

- **Sync ML de devoluções** (botão "sincronizar só devoluções"): hoje a entrada é só por
  upload de XML. Quando implementado, seguir o padrão de `/invoices/outbound/sync-ml`
  (lotes, `limit/remaining`, reuso do `download_invoices_batch`), filtrando devolução por
  CFOP/`refNFe`/natureza, e resolver o `dropshipper_id` (sem usuário logado no job).
- **Escopo por galpão nos endpoints legados** de `returns` (`/pending-validation`,
  `GET /{id}`, `PUT /{id}/status`): o caminho NF-e-driven (`import-xml`, `validate`) já
  valida via `_check_cmig_access`; os legados permanecem com gap pré-existente.

## Referências
- `BACKEND/routers/returns.py` (`_ingest_devolution`, `_create_discard_note`,
  `validate_return_endpoint`), `BACKEND/services/stock_reservation_service.py`
  (`receive_return_items`, `validate_return_items`),
  `BACKEND/services/stock_history.py` (filtro `stock_updated == True`),
  `BACKEND/services/fiscal/nfe_xml_parser.py` (`referenced_keys`, `sku`),
  `Scripts SQL/110_returns_nfe.sql`.
- ADR-0004 (estoque SSOT event-sourced), ADR-0005 (Return físico), ADR-0007 (claims vs return).

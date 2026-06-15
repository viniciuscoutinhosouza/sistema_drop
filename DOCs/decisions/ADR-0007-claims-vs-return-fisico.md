# ADR-0007 — Reclamações pós-venda (claims ML) como subsistema próprio, distinto da Devolução física (Return)

**Data:** 2026-06-14
**Status:** Aceito (implementado — sub-fase 1/2)
**Decisores:** Vinicius (proprietário)

## Contexto

A palavra "devolução" já existia no sistema como `models.return_.Return` +
`routers/returns.py`: o fluxo **físico do galpão** (estados `awaiting_validation`/
`returned`, reserva/baixa de estoque, conferência do operador logístico — ADR-0005).

A nova feature de Atendimento → Reclamações consome a API **post-purchase/v1/claims**
do Mercado Livre: reclamações do comprador (PNR/PDD/CS), mediação do ML, mensagens
com comprador/mediador, ações financeiras (reembolso total/parcial), e a *devolução
do ML* (`/claims/{id}/returns`, `related_entities type=return`). Há sobreposição de
vocabulário ("devolução") mas os conceitos são diferentes.

## Decisão

**Tratar reclamações como subsistema próprio, desacoplado da Devolução física.**

- Tabelas novas dedicadas (migration 107): `claims`, `claim_messages` (2 canais:
  `complainant`/`mediator`), `claim_actions` (histórico + auditoria local com
  `triggered_by_user_id`). **Sem FK** para `conversation_threads`/`conversation_messages`
  nem para `returns` — ligação apenas por dado (`platform_order_id`, `order_id`).
- A "devolução do ML" dentro de um claim (etiqueta, status no ML) é lida ao vivo via
  `/claims/{id}/returns` e **não** cria automaticamente um `Return` físico. Se/quando o
  produto retornar fisicamente ao galpão, o fluxo `Return` (ADR-0005) é que cuida do
  estoque. Os dois podem ser correlacionados depois por pedido, mas permanecem
  sistemas distintos.
- Reclamações reusam o **controle de acesso** da Central de Atendimento
  (`services.atendimento_access.get_accessible_account_ids`: admin = todas; ac = contas
  das suas CMIGs; demais = 403) e a mesma `menu_key` `atendimento` (entram como aba).

## Consequências

- Claro o limite: claim = relação comercial/mediação no ML (mensagens, reembolso,
  reputação); Return = logística física/estoque. Nada de misturar status entre eles.
- Mensagens de claim **não** reusam `ConversationMessage` (canais e papéis — incl.
  `mediator` — e campos ricos do claim não cabem no modelo de conversa; `platform_message_id`
  de conversa é global-unique e colidiria). Persistência própria e idempotente por
  `platform_hash` (mensagens) e `(platform_claim_id, marketplace_account_id)` (claim).
- Ações financeiras: o dispatcher valida contra `available_actions` (fonte de verdade do
  ML), bloqueia reembolso duplicado e registra auditoria (`triggered_by_user_id`).
- Sync ao vivo + persistência: job 15 min (`sync_all_claims`) + webhook tópico `claims`
  + on-demand. Coerente com ADR-0006 (aqui escolhemos **persistir**, pois o usuário pediu
  histórico/status no banco e há necessidade de trilha).

## Referências
- `BACKEND/models/claim.py`, `BACKEND/services/claims_service.py`,
  `BACKEND/tasks/claims_sync.py`, `BACKEND/routers/claims.py`, `Scripts SQL/107_claims.sql`.
- ADR-0005 (Return físico / separação), ADR-0006 (métricas live vs snapshot).

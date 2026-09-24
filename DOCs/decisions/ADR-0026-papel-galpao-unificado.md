# ADR-0026 — Papel único "Galpão" (unificação de `go` + `ugo`)

**Status:** Aceito
**Data:** 2026-09-24
**Emenda a:** [ADR-0025](ADR-0025-rbac-permissoes-acao-editaveis.md)
**Contexto do pedido:** O dono pediu para unificar os papéis GO e GL (ugo) — "todos os dados de
Galpão" — num único papel "Galpão", e diferenciar o que cada perfil faz pelas permissões editáveis
(ADR-0025). Decisão de isolamento tomada explicitamente por ele: **cada Galpão vê só o próprio galpão**.

## Contexto

O sistema tinha dois papéis de galpão com semânticas opostas de **escopo de dados**:
- `go` (Gestor Operacional) — o **mais isolado**: via só os dados do próprio `warehouse_id`
  (catálogo, contas ML/Shopee, estoque, anúncios, inventário). É o comportamento do "fix de
  isolamento do GO" (Harmony) feito antes.
- `ugo` (Gestor Logístico / "GL") — o **mais permissivo**: tinha **bypass global** em ~10 pontos
  (via dados de TODOS os galpões).

Manter os dois confundia escopo (por galpão) com capacidade (o que faz). Com a ADR-0025, capacidade
já é permissão editável por perfil (menu + ação). Faltava colapsar o **escopo**.

## Decisão

**Um único papel de escopo "Galpão", valor canônico `go`.** `ugo` é **aposentado** (mantido no CHECK
`chk_users_role` só para rollback; não mais oferecido nem atribuído).

1. **Comportamento canônico = ISOLADO POR GALPÃO.** Todo Galpão enxerga só o próprio `warehouse_id`;
   **só `admin`** tem visão global. Os bypasses globais do antigo `ugo` foram **removidos** (não
   "nivelados por cima"): `users.list_users`, `returns ?all`/bypass de dono, recompute global de
   estoque, e os ramos `("admin","ugo")` de anúncios/eShip/simulador/campanhas viraram `admin`-only,
   com o Galpão caindo no ramo isolado por `warehouse_id`/CMIG.
2. **Dono-vs-operador deixou de ser papel → virou permissão + posse.** Um Galpão que POSSUI um
   registro em `goes` (`goes.user_id == user.id`) é **dono** (gerencia empresa/galpão, pode ter
   vários galpões do seu GO); os demais são **operadores** (picking, PG, estoque, fiscal), restritos
   ao próprio `warehouse_id`. O sinal de dono é a **posse do registro em `goes`** — **não** o
   `base_role` (é `go` para os dois) nem ter `go_id` setado (operadores herdam o `go_id` do dono).
   Fonte única: `warehouse._owned_go_id()` + `_can_access_warehouse()`.
3. **Gestão de galpão/empresa** é gated pelos menus `go_empresa`/`go_usuarios` (ADR-0025); o
   dono-de-GO nasce só no fluxo dedicado `goes.py:create_go`. Cadastro pela tela de Usuários e
   `register_ugo`/`register_user` criam **operador** (`role='go'`) e **não** geram registro em `goes`.
4. **Capacidades que eram do `ugo`** (eShip WMS, import/sync CMIG→PG, desmontar kit) passaram a
   incluir `go`. Ações **globais** por natureza (recompute de estoque de todos os galpões) ficaram
   **admin-only** (não cabem a um papel isolado por galpão).

### Migração (140)

`users.role` e `user_profiles.base_role` `ugo→go`; consolidação dos 2 perfis de sistema `base_role='go'`
(antigo `go` + `gl`) num único perfil "Galpão" com a **UNIÃO** de menus e ações (reaponta
`users.profile_id` antes de remover o redundante). **Sem backfill de `go_id`** (dono = posse em `goes`,
não `go_id`). Idempotente. `ugo` preservado no CHECK para rollback.

## Emenda à ADR-0025

A ADR-0025 declarava que as ~150 checagens `role == "..."` de escopo de dados **não** foram tocadas.
Esta decisão **toca deliberadamente** ~40 dessas checagens (unifica `ugo→go` e remove os bypasses
globais). É a mudança correta — o **escopo do papel** mudou. O inventário "intocado" da ADR-0025 fica
por esta ADR **atualizado**.

## Consequências

- **Positivo:** um só conceito "Galpão", isolado por galpão (preserva e **reforça** o fix de
  isolamento — `_owned_go_id` é mais robusto que o antigo `warehouse.go_id == user.go_id`, que vazava
  galpão irmão para operador com `go_id` herdado). Dono-vs-operador é permissão, não papel.
- **Negativo / limites:**
  - **Devoluções não são escopadas por galpão** (keyed por `dropshipper_id`). Sob isolamento, a visão
    global de devoluções virou **admin-only**; um Galpão vê só as próprias. Escopar devolução ao
    galpão (join Return→Order→CMIG→warehouse) é **follow-up**.
  - `ugo` continua válido no CHECK (rollback) — a UI e os fluxos não o oferecem mais.
  - Metas de rota legadas `meta.role:'ugo'` (frontend) seguem cobertas por rede de segurança no guard;
    limpeza cosmética é follow-up.

## Relacionadas

[ADR-0025](ADR-0025-rbac-permissoes-acao-editaveis.md) (permissão = perfil), [ADR-0024](ADR-0024-galpao-work-type-dropship-multilojas.md)
(work_type é keyed por `warehouse.work_type`, independente de papel — não afetado).

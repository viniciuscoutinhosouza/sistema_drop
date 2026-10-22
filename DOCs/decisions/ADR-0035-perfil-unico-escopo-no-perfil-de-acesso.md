# ADR-0035 — Perfil único: eliminar `users.role` e mover o escopo de dados para o Perfil de Acesso

**Status:** Em implementação (Fase 1 entregue — 2026-10-22)
**Emenda/continua:** [ADR-0025](ADR-0025-rbac-permissoes-acao-editaveis.md) (permissões de ação editáveis), [ADR-0026](ADR-0026-papel-galpao-unificado.md) (papel único "Galpão")

## Contexto

O sistema tinha **duas classificações** do usuário:
- **"PERFIL"** = `users.role` (= cópia desnormalizada de `user_profiles.base_role`): `admin|ac|go` (+`ugo` aposentado).
- **"Perfil de Acesso"** = `UserProfile`: menus (`profile_menu_permissions`) + ações (`profile_action_permissions`), editável na UI.

O dono quer **uma única classificação** (o Perfil de Acesso) determinando **tudo**, e **remover o campo "PERFIL"**.

A ADR-0025 já moveu as **ações** (os `require_role` → `require_permission`) para o Perfil de Acesso, mas **deixou de propósito** o **ESCOPO DE DADOS** (isolamento por galpão/CMIG — ~150 checagens `role ==`) amarrado ao `base_role`. O escopo é crítico de segurança (errar = vazar dado entre galpões/CMIGs) e **não pode simplesmente sumir**: ele decide, por usuário, **qual estratégia de filtro** aplicar (global / por galpão / por CMIG). Os **vínculos** que carregam o "qual" (`warehouse_id`, `cmig_administrators`, posse em `goes`) já são independentes de `role`.

## Decisão

**O "modo de escopo" passa a ser atributo do Perfil de Acesso** (Opção A, escolhida pelo dono): reaproveita o `UserProfile.base_role` (rotulado na UI como **"Escopo de dados"**: Global / Por Galpão / Por Conta-CMIG). O **usuário** mantém só `profile_id` + os **vínculos** (`warehouse_id`, CMIGs administradas) — porque dois usuários do mesmo perfil "Operador de Galpão" trabalham em galpões diferentes. A coluna `users.role` é **removida** ao fim.

### Ponto de apoio técnico
`get_current_user` recarrega o `User` do banco; o claim `role` do JWT **não é lido** para autorizar. E `users.role` **já é** cópia de `profile.base_role`. Logo a transição é incremental (sem "big bang"): centralizar → repontar leituras → remover a coluna por último.

### Plano faseado
- **Fase 1 (entregue):** SSOT do escopo em `services/data_scope.py` (`scope_mode`, `warehouse_scope`, `accessible_cmig_ids` = tríade canônica admin/galpão/ac, `administered_cmig_ids`). Repontados os sites 1:1 equivalentes (eShip `_accessible_cmig_ids`, traceability `_scope`, inventories `_ac_cmig_ids`). **Migration 156**: backfill de `profile_id` em todos os usuários (materializa o fallback atual → zero-regressão). `scope_mode` ainda lê `user.role` — é o **único ponto** que a Fase 3 repontará para o Perfil de Acesso. O Atendimento (`atendimento_access`) **não** foi tocado: sua política (AC+admin-only, galpão=vazio) é distinta da tríade.
- **Fase 2:** migrar as ~150 leituras `user.role ==` (escopo) para `data_scope.scope_mode(...)`/helpers; migrar os ~25 gates de ação inline e os 17 `require_role` do eShip para `require_permission` (novas chaves eShip); remover `role` do JWT; front: `meta.role`→menuKey/permissão, botões por permissão, getters na store.
- **Fase 3:** `DROP COLUMN users.role`; `scope_mode` passa a ler do Perfil de Acesso; remover os fallbacks por `base_role`; `profile_id` NOT NULL; UI renomeia "Papel base (API)"→"Escopo de dados".
- **Fase 4:** matriz de testes de isolamento (global/galpão/conta vê só o próprio dado em todo endpoint) + auditoria de segurança.

## Consequências
- **Positivo:** uma só classificação (Perfil de Acesso) governa menus + ações + modo de escopo; fim da desnormalização `role`↔`base_role`; ponto único de escopo (`data_scope`) elimina as cópias inline.
- **Zero-regressão por fase:** Fase 1 não muda comportamento (os 3 sites repontados são equivalentes provados; backfill espelha o fallback). Cada fase é deployável e verificável isolada.
- **Risco controlado:** o isolamento de dados é crítico — a Fase 4 (matriz de isolamento) é obrigatória antes de considerar a migração concluída.
- **Verificação Fase 1:** `tests/test_data_scope.py` (modo/normalização ugo→go/warehouse_scope/tríade) + testes do eShip/inventário/rastreabilidade existentes. Backfill conferido em produção.

## Nota
`ugo` segue aceito no CHECK de `users.role`/`base_role` (rollback, ADR-0026) e é normalizado para `go` no `scope_mode`.

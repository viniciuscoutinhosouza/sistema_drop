# ADR-0025 — RBAC: permissões de ação editáveis por perfil (Opção B)

**Status:** Aceito
**Data:** 2026-09-24
**Contexto do pedido:** O dono queria, na *Gestão de Perfil de Acesso*, poder definir cada item de
permissão contido no "Papel Base API" — não ficar preso às 4 opções fixas (`admin`/`ac`/`ugo`/`go`).

## Contexto

A autorização do sistema misturava dois conceitos no mesmo campo `users.role` / `UserProfile.base_role`:

1. **O que o usuário PODE FAZER** — ~47 gates `require_role(...)` espalhados pelos routers
   (ex.: só `admin` emite config de marketplace; só `ac`/`admin` gerencia NF-e).
2. **QUAL ESCOPO DE DADOS ele enxerga** — ~150 checagens `current_user.role == "..."` que filtram
   por galpão (GO/UGO) e por CMIG (AC). Essa é a **isolação** de dados (ADR de GO isolation,
   work_type etc.) e **não pode ser quebrada**.

O menu já era data-driven por perfil (`profile_menu_permissions` + `require_menu_permission`, ~133
sites). Faltava o mesmo para as **ações**: elas estavam cravadas em código por papel, então o dono
não conseguia, por exemplo, criar um perfil base `ac` que também emitisse config de e-mail.

## Decisão

Adotada a **Opção B — permissões de ação editáveis**, decompondo os gates `require_role` em
**permissões de ação nomeadas**, concedidas por perfil e editáveis pela UI. O `base_role`
**permanece** como o **modo de escopo de dados** (renomeável no label do perfil), governando as ~150
checagens de isolação — que **não** foram tocadas.

### Peças

- **Catálogo em código** (`services/action_permissions.py`): lista `ACTION_PERMISSIONS` de
  `{key, label, group, default_base_roles}`. 15 chaves cobrindo os 47 gates
  (`usuarios_gerenciar`, `perfis_gerenciar`, `go_gerenciar`, `api_console`, `usuarios_criar`,
  `criar_ac`, `nfe_gerenciar`, `cfop_gerenciar`, `ncm_gerenciar`, `config_marketplace`,
  `config_email`, `ia_config`, `relatorio_vendas`, `pg_admin`, `anuncios_admin`).
- **Tabela** `profile_action_permissions` (migration 138): `(profile_id FK→user_profiles ON DELETE
  CASCADE, permission_key)`, único por `(profile_id, permission_key)`.
- **Dependency** `require_permission(*keys)` (`dependencies.py`): substitui `require_role` nos
  routers. Admin bypassa tudo (`role == "admin"`). Resolve as `action_keys` do perfil do usuário
  (com fallback pro perfil de sistema do `base_role`). **Fallback de compatibilidade:** se o usuário
  não tem nenhuma permissão semeada (legado/sem perfil), cai no default do `base_role` via
  `roles_for_keys(keys)` — assim nada trava no deploy.
- **Seed** de paridade: cada perfil ganha `default_keys_for_base_role(base_role)` na fase 1, então o
  comportamento é **idêntico** ao dos antigos `require_role` no momento do deploy.
- **UI** (`ProfilesView.vue`): editor de checkboxes agrupado por domínio (`GET /profiles/action-keys`),
  exibição das ações no card, e o label de "Papel base" reescrito para "modo de escopo de dados".

## Regra de ouro

Costuras **aditivas**: a decomposição entrou trocando a **dependência** do `Depends(...)`, sem alterar
a lógica de nenhum endpoint, e **sem tocar** as ~150 checagens `role == "..."` de escopo de dados.
`require_role` continua existindo (usado por `users.py:327` = "qualquer autenticado" e pelo eShip).

## Consequências

- **Positivo:** o dono cria/edita perfis com controle fino do que cada um executa, mantendo a
  isolação de dados intacta. Novos perfis herdam o default do papel base (seguro por omissão).
- **Negativo / limites:**
  - Chaves de permissão são definidas em **código** (cada uma casa com endpoints reais). A UI edita
    *quais* permissões um perfil tem e *o label de exibição*, mas **criar uma chave funcional nova**
    exige fiação no backend — permissão sem endpoint não faz nada.
  - `integrations/eship/router.py` (17 gates `require_role` multi-papel) **segue role-based** por ora;
    o menu eShip já é governado por `require_menu_permission("integracao_envio")`. Decompor o eShip
    em permissões de ação é trabalho futuro, se o dono quiser controle per-perfil ali.

## Alternativas descartadas

- **Opção A — mais papéis base fixos:** não resolve; continua cravado em código.
- **Opção C — permissões 100% dinâmicas (chave criável do zero na UI):** uma chave sem endpoint que a
  consuma é inócua e vira falsa sensação de segurança; alto risco de deixar rota aberta.

## Relacionadas

Menu data-driven (`require_menu_permission`); ADR-0024 (work_type) e isolação GO — ambas dependem do
`base_role`/escopo de dados que esta ADR **preserva**.

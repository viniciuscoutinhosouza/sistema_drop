# ADR-0036 — Capacidade nunca se amarra em helper de escopo (CMIG/fiscal/PG/estoque configuráveis por Perfil)

**Status:** Aceita
**Data:** 2026-10-24
**Emenda:** ADR-0025 (permissões de ação editáveis), ADR-0035 (papel único; escopo no Perfil). Toca também ADR-0017 (DC-e) e ADR-0018 (tipo fiscal da CMIG) — ver "Decisões sensíveis".

## Contexto

A ADR-0025 decompôs os `require_role` em **permissões de ação** editáveis por Perfil, e a ADR-0035
unificou o papel, deixando o **escopo de dados** (isolamento por galpão/CMIG) no `base_role` e no
SSOT `services/data_scope.py`. Mas sobrou um anti-padrão: várias **capacidades** (o que a pessoa
pode FAZER) estavam amarradas no **helper de ESCOPO** (`is_conta/is_galpao/is_global`) dentro do
corpo do handler, ex.:

```python
if not (is_conta(current_user) or is_global(current_user)):
    raise HTTPException(403, "Apenas AC pode criar CMIG")
```

Como esses gates não eram `require_permission`, **não existia chave no catálogo** e **a tela de
Perfil não conseguia liberá-los**. Efeito concreto relatado pelo dono: o usuário dono de galpão
(`go`) não conseguia **criar conta CMIG** nem **enviar o certificado digital (A1)** de uma CMIG, e
não havia onde habilitar isso no Perfil de Acesso. O mesmo anti-padrão aparecia no espelho
galpão-only (import/sync CMIG→PG) e em pontos fiscais/estoque avulsos.

## Decisão

**Capacidade é permissão de ação (editável por Perfil); escopo é escopo (fica no `data_scope`).**
Nenhum gate de capacidade pode se amarrar em `is_conta/is_galpao/is_global`. A autorização de uma
ação mutante passa a ser **permissão (capacidade) AND `assert_cmig_access` (escopo — qual CMIG)**.

### Regra de separação
- **Vira permissão** todo `if not (is_X): raise 403` que trava uma **ação/mutação** e que já tem um
  **check de escopo separado** (`_check_cmig_access`/`assert_cmig_access`) ao lado — o `is_X` ali é
  capacidade, não isolamento.
- **Continua escopo** (NÃO vira toggle de UI): `assert_cmig_access` e os filtros de listagem
  (`accessible_cmig_ids`, `is_global/is_galpao/is_conta` que decidem *quais linhas* a pessoa vê).
  Transformar isso em permissão quebraria o isolamento por galpão (ADR-0026) e a LGPD.
- **Pisos não-discriminantes permanecem:** guardas que liberam *todos* os escopos
  (`is_global or is_galpao or is_conta`) não discriminam papel — o menu correspondente já gateia a
  visibilidade; não viram permissão (seria churn sem ganho).

### Chaves novas (catálogo `services/action_permissions.py`, aninhadas sob o menu; migration 162 semeia os perfis-SISTEMA → zero-regressão)
| Chave | Menu | default_base_roles | Cobre |
|---|---|---|---|
| `cmig_gerenciar` | `cmig` | ac, admin | criar/editar CMIG, co-admin/convite, integração eShip da CMIG |
| `cmig_tipo_fiscal` | `cmig` | ac, admin | alterar tipo fiscal CPF⇄CNPJ (ADR-0018) |
| `cmig_fiscal_config` | `fiscal_config` | ac, admin | configuração fiscal + **certificado A1** + modo de emissão NF-e |
| `cmig_dce_authorized` | `fiscal_config` | **admin** | autorizar DC-e por conta e ordem (ADR-0017) |
| `pg_importar` | `pg` | go, admin | importar Produto CMIG → PG |
| `pg_sincronizar` | `pg` | go, admin | sincronizar Produto CMIG → PG |
| `estoque_movimentar` | `estoque` | go, admin | desmontar KIT / movimentação física manual |

`invoices.py /inutilize` passou a reusar a chave existente `nfe_gerenciar` (estava inconsistente
com os irmãos finalizar/cancelar).

### Dono de galpão = proprietário da CMIG do galpão
`assert_cmig_access(..., require_owner=True)` passou a reconhecer o **dono do galpão** (posse de
registro em `goes` do próprio galpão — ADR-0026) como proprietário, em vez de recusar todo galpão.
Operador (go sem posse) continua barrado nas ações de proprietário. O modelo AC (owner via
`cmig_administrators.is_owner`) permanece intacto — colaborador AC convidado continua **sem** poder
as ações de proprietário.

Por decisão explícita do dono ("uma única permissão cobre tudo"), `cmig_gerenciar` + posse também
habilita o dono do galpão nas ações de **co-administração** (`add_cmig_admin`/`invite_collaborator`/
`remove_cmig_admin`, do modelo CONTA). É escopo-seguro (passa por `assert_cmig_access` require_owner)
e intencional, ainda que, na prática, convidar colaborador AC numa CMIG de galpão seja raro.

### `create_cmig` virou scope-aware
A capacidade (`cmig_gerenciar`) não basta para o escopo: ao criar CMIG, o **galpão é forçado ao
próprio `warehouse_id`** (fail-closed se sem vínculo) — senão, com a permissão, criaria CMIG em
galpão alheio. Galpão **não** gera `CMIGAdministrator` fantasma (o escopo galpão deriva posse pelo
`warehouse_id`, nunca consulta essa tabela); só AC/admin viram administrador-proprietário.

### Canal de permissão de AÇÃO no frontend
O login/refresh passou a devolver `action_permissions` (efetivas, mesma régua do backend) no
`TokenResponse`; `stores/auth.js` persiste e expõe `hasAction(key)`/`hasMenu(key)` (bypass admin);
o guard do router ganhou `meta.actionKey`. Sem isso o botão apareceria e o clique tomaria 403.

## Decisões sensíveis (emendas)
- **ADR-0018** (tipo fiscal só ac/admin): vira a permissão `cmig_tipo_fiscal`, **editável** por
  Perfil, com default semeado em ac/admin (preserva a regra no deploy). A restrição deixa de ser
  "papel fixo" e passa a ser "permissão configurável".
- **ADR-0017** (DC-e expõe o CNPJ da MIG): vira `cmig_dce_authorized`, **default admin** e com
  aviso na UI. Continua restrita por padrão; o admin pode delegar conscientemente.

## Consequências
- O dono do galpão (ou qualquer perfil que o admin habilite) gerencia CMIG/certificado **desde que
  tenha acesso àquela CMIG** — exatamente o pedido do dono.
- Zero-regressão no deploy: os defaults semeados reproduzem o comportamento anterior; quem ganha
  algo novo é só quem o admin habilitar no Perfil.
- `require_role` segue morto (0 usos). O escopo (`data_scope`) não foi afrouxado.

## Follow-ups (NÃO nesta entrega — exigem verificação de seed por item p/ não trancar ninguém)
O guard de rota é **fail-closed**: migrar `meta.role`→`menuKey` de uma rota cujo menu-alvo não esteja
semeado ao papel atual tranca o usuário. Por isso ficaram para um passo verificado:
- Rotas de operador ainda em `meta.role`: `returns/aguardando-*`, `estoque`, `estoque/movimentacao`,
  `rastreabilidade`, `settings/users` (role→`config_usuarios`), `settings/warehouse`,
  `cmig-products/*`, `anuncios`, `campanha-ads`, `full-cnpjs`, `cmig-reports`, `monitoring/jobs`.
- Views com `role===` ainda por migrar: `CmigProductListView` (botões de produto × import/sync PG),
  `IntegrationsView` (edição de conta — hoje por posse `is_owner`), `CollaboratorsModal`.
- `messages.py` diagnósticos e os pisos `is_global or is_galpao or is_conta` de `stock.py`:
  mantidos (seguem a política AC+admin do Atendimento / piso não-discriminante do menu `estoque`).

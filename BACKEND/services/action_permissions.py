"""Catálogo de PERMISSÕES DE AÇÃO dos perfis de acesso (ADR-0025 / Opção B).

Cada permissão nomeada substitui um `require_role(...)` — decompõe o "Papel Base API" em itens
editáveis por perfil (como os menus). A CHAVE é do código (protege endpoints reais); o RÓTULO é
default e pode ser sobrescrito por perfil na UI. `default_base_roles` = os papéis que o
`require_role` original liberava — usado (a) para o SEED dos perfis built-in (preserva o
comportamento atual no deploy) e (b) como fallback para usuários sem perfil (legado).

O ESCOPO DE DADOS (isolamento por galpão/CMIG — os `role ==` espalhados) NÃO é permissão de ação:
continua no `base_role` (modo de escopo). Aqui só entra "o que a pessoa pode FAZER".
"""
from __future__ import annotations

# key, label (default), menu (menu_key ao qual a ação pertence — aninha a ação sob o menu na
# tela de Perfil; None = ação sem menu próprio, cai em "Outras ações"), default_base_roles
# (papéis que o require_role liberava). `menu` referencia VALID_KEYS (menus), não VALID_ACTION_KEYS;
# é validado no load de routers/profiles.py (falha alto em typo).
ACTION_PERMISSIONS: list[dict] = [
    # Administração / Usuários / Perfis
    {"key": "usuarios_gerenciar", "label": "Gerenciar usuários", "menu": "config_usuarios",
     "default_base_roles": ["admin"]},
    {"key": "usuarios_criar", "label": "Cadastrar usuário (Galpão)", "menu": "config_usuarios",
     "default_base_roles": ["admin", "go"]},
    {"key": "perfis_gerenciar", "label": "Gerenciar perfis de acesso", "menu": "config_perfis",
     "default_base_roles": ["admin"]},
    # (removido) `go_gerenciar` — a tela "Gestores Operacionais" foi aposentada; o cadastro de dono
    # de Galpão virou o bloco `owner` de `POST /warehouse` (admin-only), dentro da tela Galpões.
    # Migration 161 limpa os grants órfãos desta chave.
    {"key": "api_console", "label": "Console de API (diagnóstico)", "menu": "config_api_console",
     "default_base_roles": ["admin"]},
    # CMIG (Contas MIG) — capacidades decompostas dos gates `is_conta/is_global` que estavam
    # amarrados no helper de ESCOPO (ADR-0036). Agora quem gerencia CMIG/fiscal é definido por
    # PERFIL (capacidade) + acesso à CMIG (escopo, via `assert_cmig_access` — NÃO mexido).
    # default_base_roles = papéis que o gate inline liberava → ZERO-REGRESSÃO no seed/fallback.
    {"key": "cmig_gerenciar", "label": "Gerenciar CMIG (criar/editar/co-admin/convidar/integração)",
     "menu": "cmig", "default_base_roles": ["ac", "admin"]},
    {"key": "cmig_tipo_fiscal", "label": "Alterar tipo fiscal da CMIG (CPF ⇄ CNPJ)",
     "menu": "cmig", "default_base_roles": ["ac", "admin"]},
    {"key": "cmig_fiscal_config", "label": "Configuração fiscal da CMIG + certificado digital (A1)",
     "menu": "fiscal_config", "default_base_roles": ["ac", "admin"]},
    {"key": "cmig_dce_authorized",
     "label": "Autorizar emissão de DC-e por conta e ordem (expõe o CNPJ da MIG — ADR-0017)",
     "menu": "fiscal_config", "default_base_roles": ["admin"]},
    # PG — espelho galpão-flavored do mesmo anti-padrão (import/sync CMIG→PG estavam em
    # `is_galpao/is_global`). default = os papéis que o gate liberava (galpão canônico `go` + admin).
    {"key": "pg_importar", "label": "Importar produto CMIG para o Produto Geral (PG)",
     "menu": "pg", "default_base_roles": ["go", "admin"]},
    {"key": "pg_sincronizar", "label": "Sincronizar dados do Produto CMIG para o PG vinculado",
     "menu": "pg", "default_base_roles": ["go", "admin"]},
    # Estoque — movimentação física que era galpão-only inline (desmontar KIT etc.). O menu
    # `estoque` já controla a visibilidade; esta ação discrimina quem MOVIMENTA (galpão/admin).
    {"key": "estoque_movimentar", "label": "Movimentar estoque físico (desmontar KIT, ajustes manuais)",
     "menu": "estoque", "default_base_roles": ["go", "admin"]},
    # Fiscal
    {"key": "nfe_gerenciar", "label": "Ações fiscais de NF-e (finalizar/cancelar/inutilizar)",
     "menu": "fiscal_saidas", "default_base_roles": ["ac", "admin"]},
    {"key": "cfop_gerenciar", "label": "Gerenciar CFOPs", "menu": "fiscal_cfop",
     "default_base_roles": ["admin"]},
    {"key": "ncm_gerenciar", "label": "Gerenciar NCM", "menu": "config_ncm",
     "default_base_roles": ["admin"]},
    # Configurações
    {"key": "config_marketplace", "label": "Configuração por marketplace", "menu": "config_marketplaces",
     "default_base_roles": ["admin"]},
    {"key": "config_email", "label": "Configuração de e-mail", "menu": "config_email",
     "default_base_roles": ["admin"]},
    {"key": "ia_config", "label": "Configuração de IA", "menu": "config_ai",
     "default_base_roles": ["admin"]},
    # Relatórios / Produtos / Anúncios
    {"key": "relatorio_vendas", "label": "Relatório de vendas", "menu": "relatorio_vendas",
     "default_base_roles": ["admin", "ac", "go"]},
    {"key": "pg_admin", "label": "Ação administrativa no Produto Geral", "menu": "pg",
     "default_base_roles": ["admin"]},
    {"key": "anuncios_admin", "label": "Ação administrativa em Anúncios", "menu": "anuncios",
     "default_base_roles": ["admin"]},
    # eShip (WMS) — migrados de require_role (ADR-0035 Fase 2e). default_base_roles = EXATAMENTE
    # os papéis que o require_role liberava (preserva o comportamento no seed/fallback).
    {"key": "eship_consultar", "label": "eShip: consultar (CMIG, saldo, produtos, push)", "menu": "integracao_envio",
     "default_base_roles": ["admin", "ugo", "go", "ac"]},
    {"key": "eship_operar", "label": "eShip: operar ordem (enviar/sincronizar/cancelar/conciliar)", "menu": "integracao_envio",
     "default_base_roles": ["admin", "ugo", "go"]},
    {"key": "eship_config", "label": "eShip: configurar galpão", "menu": "config_eship",
     "default_base_roles": ["admin"]},
    # Venda / Saída + Financeiro (ADR-0037 — cancelamento de venda direta + crédito do cliente).
    {"key": "pedido_cancelar", "label": "Cancelar pedido (venda direta)", "menu": "devolucoes",
     "default_base_roles": ["admin", "go", "ac"]},
    {"key": "credito_cliente_gerenciar", "label": "Gerenciar crédito do cliente (lançar/baixar)",
     "menu": "financeiro", "default_base_roles": ["admin", "go", "ac"]},
    # Pagamento do pedido (confirmar manual com comprovante / cancelar informando motivo).
    {"key": "pagamento_confirmar", "label": "Confirmar pagamento manual (com comprovante)",
     "menu": "pedidos", "default_base_roles": ["admin", "go", "ac"]},
    {"key": "pagamento_cancelar", "label": "Cancelar pagamento (informando motivo)",
     "menu": "pedidos", "default_base_roles": ["admin", "go", "ac"]},
]

_BY_KEY = {p["key"]: p for p in ACTION_PERMISSIONS}
VALID_ACTION_KEYS = set(_BY_KEY)


def default_keys_for_base_role(base_role: str) -> list[str]:
    """Permissões que um perfil com este `base_role` recebe no SEED (preserva o comportamento).

    Admin recebe TODAS (embora o `require_permission` já dê bypass ao admin — deixa explícito na UI)."""
    if base_role == "admin":
        return [p["key"] for p in ACTION_PERMISSIONS]
    return [p["key"] for p in ACTION_PERMISSIONS if base_role in p["default_base_roles"]]


async def system_profile_id_for(base_role: str, db) -> int | None:
    """id do perfil-SISTEMA (is_system=1, is_active=1) do `base_role` — para ATRIBUIR na criação de
    usuário (ADR-0035 Fase 3: o usuário nasce com Perfil de Acesso; `role` deriva dele). O mais
    antigo (MIN id), espelhando o fallback de resolução. None se não houver perfil casável."""
    from sqlalchemy import select

    from models.user import UserProfile

    return (
        await db.execute(
            select(UserProfile.id)
            .where(
                UserProfile.is_system == 1,
                UserProfile.is_active == 1,
                UserProfile.base_role == base_role,
            )
            .order_by(UserProfile.id)
        )
    ).scalars().first()


def roles_for_keys(keys) -> set[str]:
    """União dos `default_base_roles` das chaves — fallback p/ usuário SEM perfil (legado)."""
    out: set[str] = set()
    for k in keys:
        p = _BY_KEY.get(k)
        if p:
            out.update(p["default_base_roles"])
    return out

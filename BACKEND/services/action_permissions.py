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

# key, label (default), group, default_base_roles (papéis que o require_role liberava)
ACTION_PERMISSIONS: list[dict] = [
    # Administração
    {"key": "usuarios_gerenciar", "label": "Gerenciar usuários", "group": "Administração",
     "default_base_roles": ["admin"]},
    {"key": "perfis_gerenciar", "label": "Gerenciar perfis de acesso", "group": "Administração",
     "default_base_roles": ["admin"]},
    {"key": "go_gerenciar", "label": "Gerenciar Gestores Operacionais (GO)", "group": "Administração",
     "default_base_roles": ["admin"]},
    {"key": "api_console", "label": "Console de API (diagnóstico)", "group": "Administração",
     "default_base_roles": ["admin"]},
    # Usuários — criação (endpoints distintos por papel)
    {"key": "usuarios_criar", "label": "Cadastrar usuário / UGO", "group": "Usuários",
     "default_base_roles": ["admin", "go"]},
    {"key": "criar_ac", "label": "Cadastrar Gestor de Conta (AC)", "group": "Usuários",
     "default_base_roles": ["admin", "ugo"]},
    # Fiscal
    {"key": "nfe_gerenciar", "label": "Ações fiscais de NF-e (finalizar/cancelar/inutilizar)",
     "group": "Fiscal", "default_base_roles": ["ac", "admin"]},
    {"key": "cfop_gerenciar", "label": "Gerenciar CFOPs", "group": "Fiscal",
     "default_base_roles": ["admin"]},
    {"key": "ncm_gerenciar", "label": "Gerenciar NCM", "group": "Fiscal",
     "default_base_roles": ["admin"]},
    # Configurações
    {"key": "config_marketplace", "label": "Configuração por marketplace", "group": "Configurações",
     "default_base_roles": ["admin"]},
    {"key": "config_email", "label": "Configuração de e-mail", "group": "Configurações",
     "default_base_roles": ["admin"]},
    {"key": "ia_config", "label": "Configuração de IA", "group": "Configurações",
     "default_base_roles": ["admin"]},
    # Relatórios / Produtos / Anúncios
    {"key": "relatorio_vendas", "label": "Relatório de vendas", "group": "Relatórios",
     "default_base_roles": ["admin", "ac", "go"]},
    {"key": "pg_admin", "label": "Ação administrativa no Produto Geral", "group": "Produtos",
     "default_base_roles": ["admin"]},
    {"key": "anuncios_admin", "label": "Ação administrativa em Anúncios", "group": "Anúncios",
     "default_base_roles": ["admin"]},
]

_BY_KEY = {p["key"]: p for p in ACTION_PERMISSIONS}
VALID_ACTION_KEYS = set(_BY_KEY)


def default_keys_for_base_role(base_role: str) -> list[str]:
    """Permissões que um perfil com este `base_role` recebe no SEED (preserva o comportamento).

    Admin recebe TODAS (embora o `require_permission` já dê bypass ao admin — deixa explícito na UI)."""
    if base_role == "admin":
        return [p["key"] for p in ACTION_PERMISSIONS]
    return [p["key"] for p in ACTION_PERMISSIONS if base_role in p["default_base_roles"]]


def roles_for_keys(keys) -> set[str]:
    """União dos `default_base_roles` das chaves — fallback p/ usuário SEM perfil (legado)."""
    out: set[str] = set()
    for k in keys:
        p = _BY_KEY.get(k)
        if p:
            out.update(p["default_base_roles"])
    return out

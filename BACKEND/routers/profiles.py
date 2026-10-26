"""Router de gestão de perfis de acesso — apenas super admin."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_permission
from models.user import ProfileActionPermission, ProfileMenuPermission, User, UserProfile
from services.action_permissions import (
    ACTION_PERMISSIONS,
    VALID_ACTION_KEYS,
    default_keys_for_base_role,
)
from services.data_scope import is_global

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Catálogo de menu_keys disponíveis ────────────────────────────────────────
# Cada entrada: (key, label, section)
# A ORDEM e as SEÇÕES espelham a árvore do menu lateral (AppSidebar.vue) — a tela de Perfil
# apresenta os menus "exatamente como a árvore é mostrada". Uma `section` por grupo colapsável
# do sidebar; a ordem da lista = a ordem dos grupos/itens no sidebar.
MENU_CATALOG: list[dict] = [
    # ── Cadastro ──
    {"key": "pessoas",            "label": "Pessoas",                   "section": "Cadastro"},
    {"key": "cmig",               "label": "Contas MIG (CMIG)",         "section": "Cadastro"},
    {"key": "pg",                 "label": "Produto Geral (PG)",        "section": "Cadastro"},
    # ── Relatórios ──
    {"key": "cmig_reports",       "label": "Relatórios em PDF",         "section": "Relatórios"},
    {"key": "relatorio_vendas",   "label": "Vendas do Mês",             "section": "Relatórios"},
    # ── Anúncios ──
    {"key": "catalog",            "label": "Catálogo",                  "section": "Anúncios"},
    {"key": "anuncios",           "label": "Anúncios (manutenção)",     "section": "Anúncios"},
    {"key": "atendimento",        "label": "Atendimento",               "section": "Anúncios"},
    {"key": "campanha_ads",       "label": "Campanha ADS",              "section": "Anúncios"},
    # ── Financeiro ──
    {"key": "financeiro",         "label": "Financeiro",                "section": "Financeiro"},
    # ── Venda / Saída ──
    {"key": "pedidos",            "label": "Pedidos Importados",        "section": "Venda / Saída"},
    {"key": "pedido_manual",      "label": "Pedido de Venda - Manual",  "section": "Venda / Saída"},
    {"key": "devolucoes",         "label": "Devoluções / Cancelamento", "section": "Venda / Saída"},
    # ── Compra / Entrada ──
    {"key": "fiscal_entradas",    "label": "Entradas (NF-e) de Compra", "section": "Compra / Entrada"},
    # ── Logística ──
    {"key": "separacao",          "label": "Separação (Gaiola)",        "section": "Logística"},
    # ── Estoque ──
    {"key": "estoque",            "label": "Controle de Estoque",       "section": "Estoque"},
    {"key": "inventario",         "label": "Inventário (ver)",          "section": "Estoque"},
    {"key": "inventario_criar",   "label": "Inventário (criar)",        "section": "Estoque"},
    {"key": "ag_retorno",         "label": "Ag. Retorno Físico",        "section": "Estoque"},
    # ── Fiscal ──
    {"key": "fiscal_saidas",      "label": "Saídas (NF-e)",             "section": "Fiscal"},
    {"key": "fiscal_cfop",        "label": "Cadastro de CFOPs",         "section": "Fiscal"},
    {"key": "fiscal_config",      "label": "Configuração Fiscal",       "section": "Fiscal"},
    {"key": "fiscal_transicao",   "label": "Transição Tributária",      "section": "Fiscal"},
    # ── Integração ──
    {"key": "integracao_envio",   "label": "Envio de Produtos (eShip)", "section": "Integração"},
    # ── Monitoramento ──
    {"key": "rotinas",            "label": "Rotinas Automatizadas",     "section": "Monitoramento"},
    # ── Gestão (GO) ──
    {"key": "go_empresa",         "label": "Minha Empresa",             "section": "Gestão"},
    # ── Administração ──
    {"key": "integrations",       "label": "Contas Marketplace (CM)",   "section": "Administração"},
    {"key": "full_cnpjs",         "label": "CNPJs FULL",                "section": "Administração"},
    {"key": "config_marketplaces","label": "Config. de Marketplaces",   "section": "Administração"},
    {"key": "config_eship",       "label": "Integração eShip",          "section": "Administração"},
    {"key": "config_api_console", "label": "Console de API",            "section": "Administração"},
    {"key": "config_aprovacoes",  "label": "Aprovações de Cadastro",    "section": "Administração"},
    {"key": "config_usuarios",    "label": "Usuários",                  "section": "Administração"},
    {"key": "go_usuarios",        "label": "Usuários (Galpão)",         "section": "Administração"},
    {"key": "config_galpoes",     "label": "Galpões",                   "section": "Administração"},
    {"key": "config_email",       "label": "Servidor de E-mail",        "section": "Administração"},
    {"key": "config_google_drive","label": "Google Drive",              "section": "Administração"},
    {"key": "config_ncm",         "label": "Tabela NCM",                "section": "Administração"},
    {"key": "config_ai",          "label": "Configuração de IA",        "section": "Administração"},
    {"key": "config_perfis",      "label": "Gestão de Perfis",          "section": "Administração"},
]

VALID_KEYS = {m["key"] for m in MENU_CATALOG}

# Falha alto: todo `menu` do catálogo de ações deve apontar para um menu válido (ou None).
# Pega typo no mapeamento ação→menu na subida do app, não em produção.
_bad_action_menus = [
    a["key"] for a in ACTION_PERMISSIONS
    if a.get("menu") is not None and a["menu"] not in VALID_KEYS
]
if _bad_action_menus:  # raise (não assert — assert some sob python -O)
    raise RuntimeError(f"ACTION_PERMISSIONS com menu inválido: {_bad_action_menus}")


def _serialize_profile(p: UserProfile) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "label": p.label,
        "base_role": p.base_role,
        "conta_pg_scope": getattr(p, "conta_pg_scope", "posse") or "posse",
        "is_system": bool(p.is_system),
        "is_active": bool(p.is_active),
        "menu_keys": sorted([m.menu_key for m in (p.menu_permissions or [])]),
        "action_keys": sorted([a.permission_key for a in (p.action_permissions or [])]),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ── GET /profiles/menu-keys ──────────────────────────────────────────────────
@router.get("/menu-keys")
async def list_menu_keys(
    _: User = Depends(require_permission("perfis_gerenciar")),
):
    """Retorna o catálogo completo de chaves de menu disponíveis."""
    return MENU_CATALOG


# ── GET /profiles/action-keys ────────────────────────────────────────────────
@router.get("/action-keys")
async def list_action_keys(
    _: User = Depends(require_permission("perfis_gerenciar")),
):
    """Catálogo de PERMISSÕES DE AÇÃO (o que cada perfil pode fazer — ADR-0025)."""
    return ACTION_PERMISSIONS


# ── GET /profiles ────────────────────────────────────────────────────────────
@router.get("")
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("perfis_gerenciar")),
):
    result = await db.execute(select(UserProfile).order_by(UserProfile.is_system.desc(), UserProfile.name))
    profiles = result.scalars().all()
    return [_serialize_profile(p) for p in profiles]


# ── POST /profiles ───────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_profile(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("perfis_gerenciar")),
):
    label = (body.get("label") or "").strip()
    base_role = (body.get("base_role") or "").strip()
    menu_keys: list[str] = body.get("menu_keys") or []

    if not label:
        raise HTTPException(status_code=422, detail="label é obrigatório")
    if base_role not in ("admin", "ac", "ugo", "go"):
        raise HTTPException(status_code=422, detail="base_role deve ser: admin, ac, ugo ou go")
    # Escopo admin só pode ser concedido por um admin de verdade (perfis_gerenciar é delegável).
    if base_role == "admin" and not is_global(current_user):
        raise HTTPException(status_code=403, detail="Somente um admin pode criar perfil com escopo admin")

    # `name` é só o identificador interno (unique, NOT NULL). A UI não o pede mais — derivamos um
    # slug do label e garantimos unicidade. (Compat: se o cliente ainda mandar `name`, respeitamos.)
    name = (body.get("name") or "").strip()
    if not name:
        import re as _re

        base_slug = _re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "perfil"
        name = base_slug
        _n = 1
        while (
            await db.execute(select(UserProfile).where(UserProfile.name == name))
        ).scalar_one_or_none():
            _suffix = f"_{_n}"
            name = base_slug[: 50 - len(_suffix)] + _suffix
            _n += 1
    elif (await db.execute(select(UserProfile).where(UserProfile.name == name))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Já existe um perfil com o nome '{name}'")

    invalid = [k for k in menu_keys if k not in VALID_KEYS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"menu_keys inválidas: {invalid}")

    # Permissões de ação: se não vierem, o perfil novo herda o default do base_role (comporta como
    # o papel base). Chaves inválidas falham alto.
    if "action_keys" in body:
        action_keys = body.get("action_keys") or []
        bad = [k for k in action_keys if k not in VALID_ACTION_KEYS]
        if bad:
            raise HTTPException(status_code=422, detail=f"action_keys inválidas: {bad}")
    else:
        action_keys = default_keys_for_base_role(base_role)

    # Base de visibilidade de PG do AC (modo CONTA) — só relevante p/ base_role 'ac' (ADR-0035 2d).
    pg_scope = (body.get("conta_pg_scope") or "posse").strip()
    if pg_scope not in ("posse", "administracao", "nenhum"):
        raise HTTPException(
            status_code=422, detail="conta_pg_scope deve ser: posse, administracao ou nenhum"
        )

    profile = UserProfile(
        name=name, label=label, base_role=base_role, conta_pg_scope=pg_scope,
        is_system=0, is_active=1,
    )
    db.add(profile)
    await db.flush()

    for key in menu_keys:
        db.add(ProfileMenuPermission(profile_id=profile.id, menu_key=key))
    for key in action_keys:
        db.add(ProfileActionPermission(profile_id=profile.id, permission_key=key))

    # TOCTOU: dois creates concorrentes podem derivar o mesmo slug e colidir no UNIQUE de `name`.
    # Trata como 409 limpo (espelha create_warehouse) em vez de 500.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um perfil com esse nome. Tente outro.")
    await db.refresh(profile)
    return _serialize_profile(profile)


# ── PUT /profiles/{id} ───────────────────────────────────────────────────────
@router.put("/{profile_id}")
async def update_profile(
    profile_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("perfis_gerenciar")),
):
    result = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if "label" in body:
        profile.label = (body["label"] or "").strip() or profile.label

    # base_role (modo de escopo de dados) é editável em qualquer perfil, inclusive de sistema.
    if "base_role" in body:
        new_role = (body["base_role"] or "").strip()
        if new_role not in ("admin", "ac", "ugo", "go"):
            raise HTTPException(status_code=422, detail="base_role deve ser: admin, ac, ugo ou go")
        # Escopo admin só pode ser concedido por um admin de verdade.
        if new_role == "admin" and not is_global(current_user):
            raise HTTPException(status_code=403, detail="Somente um admin pode conceder escopo admin a um perfil")
        profile.base_role = new_role

    if "conta_pg_scope" in body:
        pg_scope = (body["conta_pg_scope"] or "posse").strip()
        if pg_scope not in ("posse", "administracao", "nenhum"):
            raise HTTPException(
                status_code=422, detail="conta_pg_scope deve ser: posse, administracao ou nenhum"
            )
        profile.conta_pg_scope = pg_scope

    if "is_active" in body:
        profile.is_active = 1 if body["is_active"] else 0

    if "menu_keys" in body:
        menu_keys: list[str] = body["menu_keys"] or []
        invalid = [k for k in menu_keys if k not in VALID_KEYS]
        if invalid:
            raise HTTPException(status_code=422, detail=f"menu_keys inválidas: {invalid}")

        # Recria permissões
        existing_perms = await db.execute(
            select(ProfileMenuPermission).where(ProfileMenuPermission.profile_id == profile_id)
        )
        for perm in existing_perms.scalars().all():
            db.delete(perm)   # síncrono no AsyncSyncSession
        await db.flush()

        for key in menu_keys:
            db.add(ProfileMenuPermission(profile_id=profile_id, menu_key=key))

    if "action_keys" in body:
        action_keys: list[str] = body["action_keys"] or []
        bad = [k for k in action_keys if k not in VALID_ACTION_KEYS]
        if bad:
            raise HTTPException(status_code=422, detail=f"action_keys inválidas: {bad}")
        existing_acts = await db.execute(
            select(ProfileActionPermission).where(ProfileActionPermission.profile_id == profile_id)
        )
        for perm in existing_acts.scalars().all():
            db.delete(perm)   # síncrono no AsyncSyncSession
        await db.flush()
        for key in action_keys:
            db.add(ProfileActionPermission(profile_id=profile_id, permission_key=key))

    await db.commit()
    await db.refresh(profile)
    return _serialize_profile(profile)


# ── DELETE /profiles/{id} ────────────────────────────────────────────────────
@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("perfis_gerenciar")),
):
    result = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    if profile.is_system:
        raise HTTPException(status_code=409, detail="Perfis de sistema não podem ser deletados")

    db.delete(profile)   # síncrono no AsyncSyncSession
    await db.commit()


# ── GET /profiles/{id}/users ─────────────────────────────────────────────────
@router.get("/{profile_id}/users")
async def list_profile_users(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("perfis_gerenciar")),
):
    """Lista usuários vinculados a um perfil."""
    from models.user import User as UserModel
    result = await db.execute(
        select(UserModel).where(UserModel.profile_id == profile_id)
    )
    users = result.scalars().all()
    return [
        {"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role, "is_active": u.is_active}
        for u in users
    ]

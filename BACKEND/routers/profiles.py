"""Router de gestão de perfis de acesso — apenas super admin."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.user import ProfileMenuPermission, User, UserProfile

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Catálogo de menu_keys disponíveis ────────────────────────────────────────
# Cada entrada: (key, label, section)
MENU_CATALOG: list[dict] = [
    # Seção AC
    {"key": "cmig",             "label": "Contas MIG (CMIG)",        "section": "MINHAS CONTAS"},
    {"key": "integrations",     "label": "Contas Marketplace (CM)",  "section": "MINHAS CONTAS"},
    {"key": "cmig_reports",     "label": "Relatórios em PDF",        "section": "RELATÓRIOS"},
    {"key": "relatorio_vendas", "label": "Vendas do Mês",            "section": "RELATÓRIOS"},
    {"key": "full_cnpjs",       "label": "CNPJs FULL",               "section": "MINHAS CONTAS"},
    {"key": "anuncios",         "label": "Anúncios",                 "section": "OPERAÇÕES"},
    {"key": "campanha_ads",     "label": "Campanha ADS",             "section": "OPERAÇÕES"},
    {"key": "atendimento",      "label": "Atendimento",              "section": "OPERAÇÕES"},
    {"key": "financeiro",       "label": "Financeiro",               "section": "OPERAÇÕES"},
    {"key": "pedidos",          "label": "Pedidos",                  "section": "OPERAÇÕES"},
    {"key": "catalog",          "label": "Catálogo",                 "section": "OPERAÇÕES"},
    {"key": "pedido_manual",    "label": "Pedido Manual",            "section": "OPERAÇÕES"},
    {"key": "devolucoes",       "label": "Devoluções",               "section": "OPERAÇÕES"},
    {"key": "estoque",          "label": "Controle de Estoque",      "section": "OPERAÇÕES"},
    {"key": "pessoas",            "label": "Pessoas",                  "section": "FISCAL"},
    {"key": "fiscal_entradas",    "label": "Entradas (NF-e)",          "section": "FISCAL"},
    {"key": "fiscal_saidas",      "label": "Saídas (NF-e)",            "section": "FISCAL"},
    {"key": "fiscal_cfop",        "label": "Cadastro de CFOPs",        "section": "FISCAL"},
    {"key": "fiscal_config",      "label": "Configuração Fiscal",      "section": "FISCAL"},
    {"key": "fiscal_transicao",   "label": "Transição Tributária",     "section": "FISCAL"},
    # Seção UGO
    {"key": "pg",               "label": "Produto Geral (PG)",       "section": "OPERAÇÃO (GL)"},
    {"key": "separacao",        "label": "Separação (Gaiola)",       "section": "SEPARAÇÃO (GL)"},
    {"key": "ag_retorno",       "label": "Ag. Retorno Físico",       "section": "ESTOQUE (GL)"},
    {"key": "inventario",       "label": "Inventário (ver)",         "section": "ESTOQUE (GL)"},
    {"key": "inventario_criar", "label": "Inventário (criar)",       "section": "ESTOQUE (GL)"},
    # Integração
    {"key": "integracao_envio", "label": "Envio de Produtos (eShip)", "section": "INTEGRAÇÃO"},
    # Monitoramento
    {"key": "rotinas",          "label": "Rotinas Automatizadas",    "section": "MONITORAMENTO"},
    # GO
    {"key": "go_empresa",       "label": "Minha Empresa",            "section": "GESTÃO (GO)"},
    {"key": "go_usuarios",      "label": "Usuários (GO)",            "section": "GESTÃO (GO)"},
    # Administração
    {"key": "config_usuarios",    "label": "Usuários",               "section": "ADMINISTRAÇÃO"},
    {"key": "config_galpoes",     "label": "Galpões",                "section": "ADMINISTRAÇÃO"},
    {"key": "config_aprovacoes",  "label": "Aprovações de Cadastro", "section": "ADMINISTRAÇÃO"},
    {"key": "config_email",       "label": "Servidor de E-mail",     "section": "ADMINISTRAÇÃO"},
    {"key": "config_ncm",         "label": "Tabela NCM",             "section": "ADMINISTRAÇÃO"},
    {"key": "config_ai",          "label": "Configuração de IA",     "section": "ADMINISTRAÇÃO"},
    {"key": "config_marketplaces","label": "Config. de Marketplaces","section": "ADMINISTRAÇÃO"},
    {"key": "config_api_console", "label": "Console de API",         "section": "ADMINISTRAÇÃO"},
    {"key": "config_perfis",      "label": "Gestão de Perfis",       "section": "ADMINISTRAÇÃO"},
]

VALID_KEYS = {m["key"] for m in MENU_CATALOG}


def _serialize_profile(p: UserProfile) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "label": p.label,
        "base_role": p.base_role,
        "is_system": bool(p.is_system),
        "is_active": bool(p.is_active),
        "menu_keys": sorted([m.menu_key for m in (p.menu_permissions or [])]),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ── GET /profiles/menu-keys ──────────────────────────────────────────────────
@router.get("/menu-keys")
async def list_menu_keys(
    _: User = Depends(require_role("admin")),
):
    """Retorna o catálogo completo de chaves de menu disponíveis."""
    return MENU_CATALOG


# ── GET /profiles ────────────────────────────────────────────────────────────
@router.get("")
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    result = await db.execute(select(UserProfile).order_by(UserProfile.is_system.desc(), UserProfile.name))
    profiles = result.scalars().all()
    return [_serialize_profile(p) for p in profiles]


# ── POST /profiles ───────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_profile(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    name = (body.get("name") or "").strip()
    label = (body.get("label") or "").strip()
    base_role = (body.get("base_role") or "").strip()
    menu_keys: list[str] = body.get("menu_keys") or []

    if not name or not label:
        raise HTTPException(status_code=422, detail="name e label são obrigatórios")
    if base_role not in ("admin", "ac", "ugo", "go"):
        raise HTTPException(status_code=422, detail="base_role deve ser: admin, ac, ugo ou go")

    existing = await db.execute(select(UserProfile).where(UserProfile.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Já existe um perfil com o nome '{name}'")

    invalid = [k for k in menu_keys if k not in VALID_KEYS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"menu_keys inválidas: {invalid}")

    profile = UserProfile(name=name, label=label, base_role=base_role, is_system=0, is_active=1)
    db.add(profile)
    await db.flush()

    for key in menu_keys:
        db.add(ProfileMenuPermission(profile_id=profile.id, menu_key=key))

    await db.commit()
    await db.refresh(profile)
    return _serialize_profile(profile)


# ── PUT /profiles/{id} ───────────────────────────────────────────────────────
@router.put("/{profile_id}")
async def update_profile(
    profile_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    result = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if "label" in body:
        profile.label = (body["label"] or "").strip() or profile.label

    # base_role só pode ser alterado em perfis não-sistema
    if "base_role" in body and not profile.is_system:
        new_role = (body["base_role"] or "").strip()
        if new_role not in ("admin", "ac", "ugo", "go"):
            raise HTTPException(status_code=422, detail="base_role deve ser: admin, ac, ugo ou go")
        profile.base_role = new_role

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

    await db.commit()
    await db.refresh(profile)
    return _serialize_profile(profile)


# ── DELETE /profiles/{id} ────────────────────────────────────────────────────
@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("admin")),
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
    _: User = Depends(require_role("admin")),
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

"""Catálogo Shopee (Fase 6 + cadastro de categoria no Produto PG): categorias, atributos, marcas.

Só folha (has_children=false) publica. Atributos vêm de get_attribute_tree (get_attributes está
offline) e são NORMALIZADOS aqui para o mesmo shape que o front do ML consome (superset: carrega
value_id/input_kind/max_value_count/unidades para a publicação remontar o attribute_list). Marca 0 =
"Sem marca". Ramo 100% Shopee (ADR-0020). RBAC por posse da conta (owner/admin/AC).
"""
from __future__ import annotations

import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.integration import MarketplaceAccount
from models.user import AccountAdministrator, User
from services import shopee_service
from services.shopee_auth import get_valid_shopee_token

router = APIRouter()


# ── Cache da árvore de categorias em memória por shop_id (TTL) ─────────────────
# A árvore BR tem ~2k categorias, é shop-scoped atrás de token e muda pouco. Cachear evita
# chamar get_category (pesado, rate-limited) a cada busca/breadcrumb/abertura do formulário.
_TREE_TTL = 6 * 3600  # 6h
_tree_cache: dict[int, tuple[float, list, dict]] = {}  # shop_id -> (expira_em, cats, index)


def _norm(s: str | None) -> str:
    """lower + sem acento (para busca por nome tolerante)."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _build_index(cats: list) -> dict:
    """Indexa a árvore achatada: id(int) -> {node, children:[ids]}. Tolerante a id não-numérico."""
    by_id: dict[int, dict] = {}
    for c in cats:
        cid = _as_int(c.get("category_id"))
        if cid is not None:
            by_id[cid] = {"node": c, "children": []}
    for c in cats:
        pid, cid = _as_int(c.get("parent_category_id")), _as_int(c.get("category_id"))
        if pid is not None and cid is not None and pid in by_id:
            by_id[pid]["children"].append(cid)
    return by_id


async def _get_tree(acc: MarketplaceAccount, token: str) -> tuple[list, dict]:
    """Árvore + índice, com cache TTL por shop_id."""
    now = time.time()
    cached = _tree_cache.get(acc.shop_id)
    if cached and cached[0] > now:
        return cached[1], cached[2]
    cats = await shopee_service.get_category(token, acc.shop_id)
    index = _build_index(cats)
    _tree_cache[acc.shop_id] = (now + _TREE_TTL, cats, index)
    return cats, index


def _cat_name(node: dict) -> str:
    return node.get("display_category_name") or node.get("original_category_name") or ""


def _path_from_root(index: dict, category_id: int) -> list:
    """Breadcrumb [{id,name}] da raiz até a categoria (nomes pt-BR). Anti-ciclo."""
    chain, seen = [], set()
    cur = index.get(_as_int(category_id))
    while cur is not None:
        node = cur["node"]
        cid = _as_int(node.get("category_id"))
        if cid is None or cid in seen:
            break
        seen.add(cid)
        chain.append({"id": cid, "name": _cat_name(node)})
        pid = _as_int(node.get("parent_category_id"))
        cur = index.get(pid) if pid else None
    chain.reverse()
    return chain


def _cat_result(index: dict, category_id) -> dict | None:
    node = index.get(_as_int(category_id))
    if not node:
        return None
    has_children = bool(node["node"].get("has_children"))
    return {
        "id": int(category_id),
        "name": _cat_name(node["node"]),
        "has_children": has_children,
        "is_leaf": not has_children,  # só folha publica na Shopee
        "path_from_root": _path_from_root(index, category_id),
    }


# ── Normalização de atributos (get_attribute_tree → shape ML superset) ─────────
# Enums confirmados AO VIVO (get_attribute_tree, campos em `attribute_info`):
#   input_type: 1=DROP_DOWN (single, só lista), 2=COMBO_BOX (single, lista/custom),
#               3=TEXT_FIELD (texto livre, sem lista), 4=MULTIPLE_DROP_DOWN (multi, só lista),
#               5=MULTIPLE_COMBO_BOX (multi, lista/custom).
#   format_type: 1=NORMAL (sem unidade), 2=QUANTITATIVE (número + unidade de attribute_unit_list).
# "Quantitativo" é governado por format_type==2 (independe do input_type). Regra de decisão do
# formulário: format_type==2 → número+unidade; input_type∈{4,5} → multi; 3 → texto; 1/2 → single.


def _label_pt(o: dict) -> str:
    for ml in (o.get("multi_lang") or []):
        if (ml.get("language") or "").lower().startswith("pt"):
            return ml.get("value") or ""
    return o.get("name") or o.get("original_value_name") or o.get("original_attribute_name") or ""


def _derive_kind(info: dict, has_values: bool) -> str:
    input_type = info.get("input_type")
    if info.get("format_type") == 2 or info.get("attribute_unit_list"):
        return "quantitative"          # número + unidade (independe do input_type)
    if input_type in (4, 5):
        return "multi"                 # MULTIPLE_DROP_DOWN / MULTIPLE_COMBO_BOX
    if input_type == 3:
        return "text"                  # TEXT_FIELD (entrada livre)
    if input_type in (1, 2):
        return "single" if has_values else "text"
    return "single" if has_values else "text"  # fallback


def _normalize_attr(attr: dict) -> dict:
    info = attr.get("attribute_info") or {}
    input_type = info.get("input_type")
    kind = _derive_kind(info, bool(attr.get("attribute_value_list")))
    mandatory = bool(attr.get("mandatory"))
    return {
        "id": attr.get("attribute_id"),
        "name": _label_pt(attr) or attr.get("name"),
        "is_required": mandatory,
        "is_recommended": False,  # Shopee não tem tier "recomendado"
        "is_optional": not mandatory,
        "input_kind": kind,                 # single | multi | quantitative | text
        "input_type": input_type,           # cru (auditoria/depuração)
        "max_value_count": info.get("max_value_count") or 1,
        "allowed_units": info.get("attribute_unit_list") or None,
        "values": [
            {"id": v.get("value_id"), "name": _label_pt(v)}
            for v in (attr.get("attribute_value_list") or [])
        ],
    }


# ── RBAC / resolução de conta ─────────────────────────────────────────────────


def _owned_shopee_filter(user: User):
    """Filtro de posse p/ contas Shopee acessíveis ao usuário (admin vê todas)."""
    conds = [MarketplaceAccount.platform == "shopee", MarketplaceAccount.is_active == True]  # noqa: E712
    if user.role != "admin":
        conds.append(or_(
            MarketplaceAccount.owner_id == user.id,
            MarketplaceAccount.id.in_(
                select(AccountAdministrator.account_id).where(AccountAdministrator.user_id == user.id)
            ),
        ))
    return conds


async def _shopee_account(account_id: int, user: User, db: AsyncSession):
    """Resolve a conta Shopee com RBAC de posse (owner/admin/administrador da conta) + token."""
    acc = (await db.execute(
        select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
    )).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    if acc.platform != "shopee":
        raise HTTPException(status_code=400, detail="Conta não é Shopee")
    if user.role != "admin" and acc.owner_id != user.id:
        adm = (await db.execute(
            select(AccountAdministrator).where(
                AccountAdministrator.account_id == account_id,
                AccountAdministrator.user_id == user.id,
            )
        )).scalar_one_or_none()
        if not adm:
            raise HTTPException(status_code=403, detail="Sem acesso a esta conta")
    token = await get_valid_shopee_token(acc, db)
    return acc, token


@router.get("/default-account")
async def default_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """1ª conta Shopee ATIVA acessível ao usuário — o cadastro de categoria usa esta loja para
    puxar árvore/atributos/marcas (endpoints são shop-scoped). Se não houver, `account_id=None`
    e o front BLOQUEIA com mensagem clara (falhar alto — nunca dropdown vazio silencioso)."""
    acc = (await db.execute(
        select(MarketplaceAccount).where(*_owned_shopee_filter(current_user))
        .order_by(MarketplaceAccount.id)
    )).scalars().first()
    if not acc:
        return {"account_id": None, "shop_name": None, "shop_id": None,
                "detail": "Nenhuma conta Shopee conectada. Conecte uma loja Shopee para cadastrar categorias Shopee."}
    return {"account_id": acc.id, "shop_name": acc.platform_username, "shop_id": acc.shop_id}


@router.get("/categories")
async def categories(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Árvore de categorias BR (achatada). Cada item traz has_children (folha=false, só folha publica)."""
    acc, token = await _shopee_account(account_id, current_user, db)
    cats, _ = await _get_tree(acc, token)
    return {"total": len(cats), "categorias": cats}


@router.get("/categories/search")
async def categories_search(
    account_id: int,
    q: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Busca categoria por nome (na árvore cacheada) → [{id,name,is_leaf,path_from_root}].
    Espelha /anuncios/categories/search do ML. Folhas primeiro (só folha publica)."""
    acc, token = await _shopee_account(account_id, current_user, db)
    cats, index = await _get_tree(acc, token)
    ql = _norm(q)
    out = []
    for c in cats:
        if ql in _norm(_cat_name(c)):
            r = _cat_result(index, c.get("category_id"))
            if r:
                out.append(r)
    out.sort(key=lambda r: (not r["is_leaf"], r["name"]))  # folhas primeiro
    return out[:50]


@router.get("/categories/recommend")
async def categories_recommend(
    account_id: int,
    item_name: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sugestão por nome (category_recommend) já ENRIQUECIDA com nome+breadcrumb+folha, só folhas."""
    acc, token = await _shopee_account(account_id, current_user, db)
    cats, index = await _get_tree(acc, token)
    ids = await shopee_service.category_recommend(token, acc.shop_id, item_name)
    out = []
    for cid in ids:
        r = _cat_result(index, cid)
        if r and r["is_leaf"]:  # recomendação pode vir não-folha → filtra
            out.append(r)
    return {"item_name": item_name, "resultados": out}


@router.get("/categories/{category_id}/resolve")
async def category_resolve(
    category_id: int,
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve uma categoria → nome + breadcrumb + folha (espelha GET /anuncios/categories/{id})."""
    acc, token = await _shopee_account(account_id, current_user, db)
    _, index = await _get_tree(acc, token)
    r = _cat_result(index, category_id)
    if not r:
        raise HTTPException(status_code=404, detail="Categoria não encontrada na árvore da loja")
    return r


@router.get("/categories/{category_id}/attributes")
async def category_attributes(
    category_id: int,
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atributos NORMALIZADOS (shape ML superset). `is_required`←`mandatory`; `values[{id,name pt-BR}]`;
    `input_kind` (single/multi/quantitative/text); `max_value_count`; `allowed_units`."""
    acc, token = await _shopee_account(account_id, current_user, db)
    attrs = await shopee_service.get_attribute_tree(token, acc.shop_id, category_id)
    return [_normalize_attr(a) for a in attrs]


@router.get("/categories/{category_id}/brands")
async def category_brands(
    category_id: int,
    account_id: int,
    q: str | None = Query(None),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Marcas da categoria (brand_id 0 = 'Sem marca'). `is_mandatory` diz se a marca é obrigatória.
    `q` filtra por nome (typeahead); pagina por `offset`/`next_offset`."""
    acc, token = await _shopee_account(account_id, current_user, db)
    raw = await shopee_service.get_brand_list(token, acc.shop_id, category_id, offset=offset)
    brands = raw.get("brand_list") or []
    if q:
        ql = _norm(q)
        brands = [b for b in brands if ql in _norm(b.get("display_brand_name") or b.get("original_brand_name"))]
    return {
        "is_mandatory": bool(raw.get("is_mandatory")),
        "has_next_page": bool(raw.get("has_next_page")),
        "next_offset": raw.get("next_offset"),
        "brands": [
            {"brand_id": b.get("brand_id"),
             "name": b.get("display_brand_name") or b.get("original_brand_name")}
            for b in brands
        ],
    }


@router.get("/category-recommend")
async def category_recommend(
    account_id: int,
    item_name: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """(Legado) Sugestão de category_id cru. Prefira /categories/recommend (enriquecido)."""
    acc, token = await _shopee_account(account_id, current_user, db)
    ids = await shopee_service.category_recommend(token, acc.shop_id, item_name)
    return {"item_name": item_name, "category_ids": ids}

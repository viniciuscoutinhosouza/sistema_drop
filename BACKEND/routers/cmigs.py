import os as _os
import secrets as _secrets
import shutil as _shutil
import uuid as _uuid_mod
from datetime import date as _date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy import delete as _sa_delete
from sqlalchemy import update as _sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database import get_db
from dependencies import get_current_user
from models.cmig import (
    CMIG,
    CMIGAdministrator,
    CMIGProduct,
    CMIGProductComponent,
    CMIGProductImage,
    CMIGProductVariant,
)
from models.fiscal import CMIGFiscalConfig
from models.nfe_config import NFeConfig
from models.order import OrderItem
from models.product import (
    CatalogProduct,
    CatalogProductImage,
    CatalogProductVariant,
    ProductListing,
    ProductMarketplaceCategory,
)
from models.user import User, UserInvite
from models.warehouse import Warehouse
from schemas.cmig import (
    CMIGAdminAdd,
    CMIGCreate,
    CMIGOut,
    CMIGProductCreate,
    CMIGProductLinkPG,
    CMIGProductUpdate,
    CMIGUpdate,
    NFeConfigCreate,
    NFeConfigOut,
    NFeConfigUpdate,
)
from services import email_service

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _get_cmig_or_404(cmig_id: int, db: AsyncSession) -> CMIG:
    result = await db.execute(select(CMIG).where(CMIG.id == cmig_id))
    cmig = result.scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    return cmig


async def _check_cmig_access(cmig: CMIG, user: User, db: AsyncSession, require_owner: bool = False):
    """Valida se o usuário pode acessar a CMIG."""
    if user.role == "admin":
        return
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        if require_owner:
            raise HTTPException(
                status_code=403, detail="Apenas o AC proprietário pode realizar esta ação"
            )
        return
    if user.role == "ac":
        result = await db.execute(
            select(CMIGAdministrator).where(
                and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig.id)
            )
        )
        admin = result.scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        if require_owner and not admin.is_owner:
            raise HTTPException(
                status_code=403, detail="Apenas o AC proprietário pode realizar esta ação"
            )
        return
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


# ── Helpers de Produto Composto ────────────────────────────────────────────────


def _calculate_cmig_composite_stock(components) -> int:
    """Estoque montável do CMIG composto. Delega ao ponto único em
    `stock_calculator.composite_stock` (resolve cmig_product ou catalog_product)."""
    from services.fiscal.stock_calculator import composite_stock

    return composite_stock(components)


def _product_specs(src) -> dict:
    """Ficha do produto exibida em cada componente do KIT (dimensões/peso/NCM/CEST) + a
    descrição (usada pelo botão de copiar). CMIGProduct e CatalogProduct têm os MESMOS
    nomes de coluna, então serve para os dois."""
    def _n(v):
        return float(v) if v is not None else None

    return {
        "description": src.description or "",
        "weight_kg": _n(src.weight_kg),
        "height_cm": _n(src.height_cm),
        "width_cm": _n(src.width_cm),
        "length_cm": _n(src.length_cm),
        "ncm": src.ncm or "",
        "cest": src.cest or "",
    }


def _serialize_cmig_product(p: CMIGProduct) -> dict:
    thumbnail = p.images[0].url if p.images else None
    stock = _calculate_cmig_composite_stock(p.components) if p.is_composite else p.stock_quantity
    components = []
    if p.is_composite:
        for comp in p.components:
            source = comp.cmig_product if comp.cmig_product_id else comp.catalog_product
            if source:
                qty = max(comp.quantity, 1)
                components.append(
                    {
                        "id": comp.id,
                        "type": "cmig" if comp.cmig_product_id else "pg",
                        "product_id": comp.cmig_product_id or comp.catalog_product_id,
                        "title": source.title,
                        "sku": source.sku_cmig if comp.cmig_product_id else source.sku,
                        "stock_quantity": source.stock_quantity,
                        "cost_price": float(source.cost_price) if source.cost_price is not None else 0.0,
                        "quantity": comp.quantity,
                        "contribution": source.stock_quantity // qty,
                        # Ficha p/ exibir abaixo do título + copiar a descrição (sem isto, ao
                        # reabrir o KIT em edição os campos sumiam).
                        **_product_specs(source),
                    }
                )
    return {
        "id": p.id,
        "cmig_id": p.cmig_id,
        "sku_cmig": p.sku_cmig,
        "title": p.title,
        "description": p.description,
        "brand": p.brand,
        "model": p.model,
        "ean": p.ean,
        "cost_price": float(p.cost_price) if p.cost_price is not None else None,
        "suggested_price": float(p.suggested_price) if p.suggested_price else None,
        "stock_quantity": stock,
        "weight_kg": float(p.weight_kg) if p.weight_kg else None,
        "height_cm": float(p.height_cm) if p.height_cm else None,
        "width_cm": float(p.width_cm) if p.width_cm else None,
        "length_cm": float(p.length_cm) if p.length_cm else None,
        "ncm": p.ncm,
        "cest": p.cest,
        "origin": p.origin,
        "csosn": p.csosn,
        "category_id": p.category_id,
        "category_name": p.category_name,
        "video_id": p.video_id,
        "attributes_json": p.attributes_json,
        "pictures_json": p.pictures_json,
        "pg_product_id": p.pg_product_id,
        "is_composite": p.is_composite,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "thumbnail": thumbnail,
        "images": [
            {"id": i.id, "url": i.url, "sort_order": i.sort_order, "is_primary": i.is_primary}
            for i in p.images
        ],
        "components": components,
    }


# ── CMIG CRUD ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_cmigs(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Por padrão só CMIGs ativas (todos os dropdowns seletores). A tela de gestão
    # passa include_inactive=true para ver/gerenciar as inativas também.
    base = select(CMIG) if include_inactive else select(CMIG).where(CMIG.is_active == True)  # noqa: E712
    if current_user.role == "admin":
        result = await db.execute(base)
    elif current_user.role == "ugo":
        result = await db.execute(base.where(CMIG.warehouse_id == current_user.warehouse_id))
    elif current_user.role == "ac":
        subq = select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == current_user.id)
        result = await db.execute(base.where(CMIG.id.in_(subq)))
    else:
        raise HTTPException(status_code=403, detail="Permissão insuficiente")

    cmigs_list = result.scalars().all()

    # Carrega is_owner por CMIG para o usuário corrente
    owned_ids: set[int] = set()
    if cmigs_list and current_user.role == "ac":
        ids = [c.id for c in cmigs_list]
        owned = await db.execute(
            select(CMIGAdministrator.cmig_id).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id.in_(ids),
                CMIGAdministrator.is_owner == True,
            )
        )
        owned_ids = {row[0] for row in owned.all()}

    return [
        {
            "id": c.id,
            "owner_ac_id": c.owner_ac_id,
            "warehouse_id": c.warehouse_id,
            "cnpj": c.cnpj,
            "cpf": c.cpf,
            "company_name": c.company_name,
            "trade_name": c.trade_name,
            "email": c.email,
            "phone": c.phone,
            "zip_code": c.zip_code,
            "street": c.street,
            "address_number": c.address_number,
            "complement": c.complement,
            "neighborhood": c.neighborhood,
            "city": c.city,
            "state": c.state,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            # eShip (WMS) — não expõe a apikey, só se está configurada
            "eship_active": bool(getattr(c, "eship_active", 0)),
            "eship_configured": bool(c.eship_base_url and c.eship_api_key),
            # is_owner: AC dono → flag em CMIGAdministrator; admin → sempre True (bypass total)
            "is_owner": current_user.role == "admin" or c.id in owned_ids,
        }
        for c in cmigs_list
    ]


@router.post("", status_code=201, response_model=CMIGOut)
async def create_cmig(
    body: CMIGCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC pode criar CMIG")

    if body.cnpj:
        dup = await db.execute(select(CMIG).where(CMIG.cnpj == body.cnpj))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="CNPJ já cadastrado")
    if body.cpf:
        dup = await db.execute(select(CMIG).where(CMIG.cpf == body.cpf))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="CPF já cadastrado")

    # Validar galpão
    wh = await db.execute(select(Warehouse).where(Warehouse.id == body.warehouse_id))
    if not wh.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    cmig = CMIG(
        owner_ac_id=current_user.id,
        **body.model_dump(),
    )
    db.add(cmig)
    await db.flush()

    # Registrar como administrador proprietário
    admin_entry = CMIGAdministrator(user_id=current_user.id, cmig_id=cmig.id, is_owner=True)
    db.add(admin_entry)
    await db.commit()
    await db.refresh(cmig)
    return cmig


@router.get("/{cmig_id}", response_model=CMIGOut)
async def get_cmig(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    return cmig


@router.put("/{cmig_id}", response_model=CMIGOut)
async def update_cmig(
    cmig_id: int,
    body: CMIGUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    updates = body.model_dump(exclude_none=True)
    sent = body.model_fields_set

    # ── Documento fiscal (CPF/CNPJ) ──────────────────────────────────────────────
    # Tratado FORA do exclude_none para permitir LIMPAR o documento antigo (ex.: converter
    # uma conta PF em PJ zera o CPF e grava o CNPJ). Só mexe se o cliente enviou cnpj/cpf.
    if {"cnpj", "cpf"} & sent:
        old_is_pf = bool((cmig.cpf or "").strip()) and not (cmig.cnpj or "").strip()
        new_cnpj = (cmig.cnpj if "cnpj" not in sent else updates.get("cnpj")) or None
        new_cpf = (cmig.cpf if "cpf" not in sent else updates.get("cpf")) or None

        # Estado final: exatamente um documento (paridade com a regra de criação).
        if new_cnpj and new_cpf:
            raise HTTPException(status_code=422, detail="Informe apenas CNPJ ou CPF, não ambos")
        if not new_cnpj and not new_cpf:
            raise HTTPException(
                status_code=422, detail="Informe o CNPJ (Pessoa Jurídica) ou CPF (Pessoa Física)"
            )

        type_changed = bool(new_cnpj) != bool((cmig.cnpj or "").strip()) or bool(new_cpf) != bool(
            (cmig.cpf or "").strip()
        )
        # Alterar o TIPO fiscal é tão sensível quanto criar → exige AC/admin.
        if type_changed and current_user.role not in ("ac", "admin"):
            raise HTTPException(
                status_code=403,
                detail="Apenas AC ou admin podem alterar o tipo fiscal (CPF/CNPJ) da CMIG",
            )

        # Unicidade
        if new_cnpj and new_cnpj != cmig.cnpj:
            dup = await db.execute(select(CMIG).where(CMIG.cnpj == new_cnpj, CMIG.id != cmig_id))
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="CNPJ já cadastrado em outra CMIG")
        if new_cpf and new_cpf != cmig.cpf:
            dup = await db.execute(select(CMIG).where(CMIG.cpf == new_cpf, CMIG.id != cmig_id))
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="CPF já cadastrado em outra CMIG")

        # Razão Social obrigatória para PJ.
        eff_company = updates.get("company_name", cmig.company_name)
        if new_cnpj and not (eff_company or "").strip():
            raise HTTPException(status_code=422, detail="Informe a Razão Social ao definir o CNPJ")

        # Conversão CPF→CNPJ exige IE + código IBGE (a PJ nasce apta ao próximo passo fiscal).
        if old_is_pf and new_cnpj:
            eff_ibge = (
                updates.get("ibge_code") if "ibge_code" in sent else cmig.ibge_code
            ) or ""
            eff_ibge = eff_ibge.strip()
            cfg = (
                await db.execute(
                    select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id)
                )
            ).scalar_one_or_none()
            eff_ie = (updates.get("ie") if "ie" in sent else (cfg.ie if cfg else None)) or ""
            eff_ie = eff_ie.strip()
            missing = []
            if not eff_ie:
                missing.append("Inscrição Estadual (IE)")
            if not eff_ibge:
                missing.append("Código IBGE do município")
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail="Para converter para CNPJ, informe: " + ", ".join(missing),
                )
            cmig.ibge_code = eff_ibge
            # IE mora no CMIGFiscalConfig — upsert só quando veio no payload da conversão.
            if "ie" in sent and eff_ie:
                if not cfg:
                    cfg = CMIGFiscalConfig(cmig_id=cmig_id)
                    db.add(cfg)
                    await db.flush()
                cfg.ie = eff_ie

        # Aplica o documento explicitamente (permite limpar o antigo).
        cmig.cnpj = new_cnpj
        cmig.cpf = new_cpf

    # `ie` não é atributo do CMIG e cnpj/cpf já foram tratados acima.
    for key in ("cnpj", "cpf", "ie"):
        updates.pop(key, None)
    for field, value in updates.items():
        if hasattr(cmig, field):
            setattr(cmig, field, value)

    await db.commit()
    await db.refresh(cmig)
    return cmig


# ── Configuração eShip (WMS) por empresa ─────────────────────────────────────────


def _serialize_eship(cmig: CMIG) -> dict:
    """Config eShip da CMIG — nunca devolve a apikey, só se está setada."""
    return {
        "cmig_id": cmig.id,
        "eship_active": bool(getattr(cmig, "eship_active", 0)),
        "eship_base_url": cmig.eship_base_url or "",
        "eship_warehouse_code": cmig.eship_warehouse_code or "",
        # Cadastro da empresa no eShip (migration 125) — vão no webServicePostOrdem.
        "eship_id_tipo": getattr(cmig, "eship_id_tipo", None),
        "eship_tipo_ordem": getattr(cmig, "eship_tipo_ordem", None) or "",
        "eship_api_key_set": bool(cmig.eship_api_key),
        "cnpj": cmig.cnpj,
    }


@router.get("/{cmig_id}/eship-config")
async def get_eship_config(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna a config eShip da CMIG (apikey mascarada)."""
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    return _serialize_eship(cmig)


@router.patch("/{cmig_id}/eship-config")
async def update_eship_config(
    cmig_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza a config eShip da CMIG. A apikey só é alterada se vier preenchida."""
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC ou admin podem editar a integração eShip")

    if "eship_base_url" in body:
        cmig.eship_base_url = (body.get("eship_base_url") or "").strip() or None
    if "eship_warehouse_code" in body:
        cmig.eship_warehouse_code = (body.get("eship_warehouse_code") or "").strip() or None
    if "eship_id_tipo" in body:
        raw = body.get("eship_id_tipo")
        try:
            cmig.eship_id_tipo = int(raw) if str(raw).strip() not in ("", "None") else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="idTipo do eShip deve ser um número.")
    if "eship_tipo_ordem" in body:
        cmig.eship_tipo_ordem = (body.get("eship_tipo_ordem") or "").strip() or None
    # apikey: só atualiza se vier preenchida (campo password não reenvia o valor existente)
    api_key = body.get("eship_api_key")
    if api_key:
        cmig.eship_api_key = api_key.strip()
    if "eship_active" in body:
        cmig.eship_active = 1 if body.get("eship_active") else 0

    await db.commit()
    await db.refresh(cmig)
    return _serialize_eship(cmig)


# ── Co-administração ───────────────────────────────────────────────────────────


@router.get("/{cmig_id}/admins")
async def list_cmig_admins(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGAdministrator, User)
        .join(User, CMIGAdministrator.user_id == User.id)
        .where(CMIGAdministrator.cmig_id == cmig_id)
        .order_by(CMIGAdministrator.is_owner.desc(), User.full_name)
    )
    return [
        {
            "user_id": admin.user_id,
            "is_owner": admin.is_owner,
            "full_name": user.full_name,
            "email": user.email,
        }
        for admin, user in result.all()
    ]


@router.get("/{cmig_id}/collaborators/candidates")
async def list_collaborator_candidates(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista ACs ativos elegíveis para virar colaboradores desta CMIG.

    Acessível ao DONO da CMIG (não depende do menu 'config_usuarios'). Exclui quem
    já é administrador e o próprio usuário.
    """
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db, require_owner=True)

    existing = {
        r[0]
        for r in (
            await db.execute(
                select(CMIGAdministrator.user_id).where(CMIGAdministrator.cmig_id == cmig_id)
            )
        ).all()
    }
    rows = (
        await db.execute(
            select(User)
            .where(User.role == "ac", User.is_active == True)  # noqa: E712
            .order_by(User.full_name)
        )
    ).scalars().all()
    return [
        {"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role}
        for u in rows
        if u.id not in existing and u.id != current_user.id
    ]


@router.post("/{cmig_id}/admins", status_code=201)
async def add_cmig_admin(
    cmig_id: int,
    body: CMIGAdminAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db, require_owner=True)

    # Valida o usuário: existe, é AC e está ativo (evita erro genérico de FK).
    target = (
        await db.execute(select(User).where(User.id == body.user_id))
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if target.role != "ac":
        raise HTTPException(status_code=400, detail="Somente Gestores de Conta (AC) podem ser colaboradores")
    if not target.is_active:
        raise HTTPException(
            status_code=400,
            detail="Usuário aguardando liberação do administrador — ainda não pode ser vinculado",
        )

    dup = await db.execute(
        select(CMIGAdministrator).where(
            and_(CMIGAdministrator.user_id == body.user_id, CMIGAdministrator.cmig_id == cmig_id)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Usuário já é administrador desta CMIG")

    entry = CMIGAdministrator(user_id=body.user_id, cmig_id=cmig_id, is_owner=False)
    db.add(entry)
    await db.commit()
    return {"detail": "Co-administrador adicionado com sucesso"}


@router.post("/{cmig_id}/invites", status_code=201)
async def invite_collaborator(
    cmig_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Convida um colaborador por e-mail. O convidado se cadastra por um link e o
    administrador geral libera o acesso; depois o dono vincula pela lista de ACs.

    Se o e-mail já for um AC ativo, informa que ele pode ser adicionado direto.
    """
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db, require_owner=True)

    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Informe um e-mail válido")

    existing_user = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    if existing_user:
        if existing_user.role == "ac" and existing_user.is_active:
            return {
                "already_user": True,
                "message": "Este e-mail já é um Gestor de Conta ativo — selecione-o na lista de ACs para adicionar como colaborador.",
            }
        if existing_user.role == "ac" and not existing_user.is_active:
            raise HTTPException(
                status_code=409,
                detail="Este e-mail já iniciou um cadastro e aguarda a liberação do administrador.",
            )
        raise HTTPException(
            status_code=409,
            detail="Já existe um usuário com este e-mail (não elegível). Verifique com o administrador.",
        )

    # Reaproveita convite pendente do mesmo e-mail/CMIG, se houver.
    invite = (
        await db.execute(
            select(UserInvite).where(
                and_(
                    func.lower(UserInvite.email) == email,
                    UserInvite.cmig_id == cmig_id,
                    UserInvite.status.in_(("pending_registration", "pending_approval")),
                )
            )
        )
    ).scalar_one_or_none()
    if not invite:
        invite = UserInvite(
            cmig_id=cmig_id,
            email=email,
            invited_by_user_id=current_user.id,
            token=_secrets.token_urlsafe(32),
            status="pending_registration",
        )
        db.add(invite)
        await db.flush()

    link = f"{get_settings().FRONTEND_URL.rstrip('/')}/cadastro-convite/{invite.token}"

    # Envia o e-mail (best-effort); se o SMTP estiver off, devolve o link p/ envio manual.
    sent = False
    try:
        subject = "Convite para colaborar em uma conta — MIG ECOMMERCE"
        html = _invite_email_html(cmig, current_user, link)
        await email_service.send_email(db, email, subject, html)
        sent = True
    except Exception:  # noqa: BLE001
        sent = False

    await db.commit()
    return {"already_user": False, "email_sent": sent, "invite_link": link}


def _invite_email_html(cmig, inviter, link: str) -> str:
    empresa = cmig.company_name or cmig.trade_name or "uma conta"
    return f"""\
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
      <h2 style="color:#2c3e50">Você foi convidado(a) para colaborar</h2>
      <p><strong>{inviter.full_name}</strong> convidou você para colaborar na conta
      <strong>{empresa}</strong> no sistema MIG ECOMMERCE.</p>
      <p>Clique no botão abaixo para criar seu cadastro. Após o cadastro, o administrador
      liberará seu acesso.</p>
      <p style="text-align:center;margin:24px 0">
        <a href="{link}" style="background:#007bff;color:#fff;padding:12px 24px;
           border-radius:6px;text-decoration:none">Criar meu cadastro</a>
      </p>
      <p style="color:#888;font-size:13px">Ou copie e cole este link no navegador:<br>{link}</p>
      <hr style="border:none;border-top:1px solid #eee">
      <p style="color:#aaa;font-size:12px">MIG ECOMMERCE — Sistema Drop</p>
    </div>"""


@router.delete("/{cmig_id}/admins/{user_id}", status_code=204)
async def remove_cmig_admin(
    cmig_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db, require_owner=True)

    result = await db.execute(
        select(CMIGAdministrator).where(
            and_(CMIGAdministrator.user_id == user_id, CMIGAdministrator.cmig_id == cmig_id)
        )
    )
    entry = result.scalar_one_or_none()
    if not entry or entry.is_owner:
        raise HTTPException(
            status_code=404, detail="Co-administrador não encontrado ou é o proprietário"
        )

    db.delete(entry)
    await db.commit()


# ── Produtos CMIG ──────────────────────────────────────────────────────────────


@router.get("/{cmig_id}/products")
async def list_cmig_products(
    cmig_id: int,
    composite_only: bool = False,
    simple_only: bool = False,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    stmt = (
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.images))
        .where(CMIGProduct.cmig_id == cmig_id)
    )
    if composite_only:
        stmt = stmt.where(CMIGProduct.is_composite == True)
    if simple_only:
        stmt = stmt.where(CMIGProduct.is_composite == False)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(CMIGProduct.title.ilike(like), CMIGProduct.sku_cmig.ilike(like))
        )

    result = await db.execute(stmt)
    return [_serialize_cmig_product(p) for p in result.scalars().all()]


@router.get("/{cmig_id}/pg-products")
async def list_pg_products_for_cmig(
    cmig_id: int,
    search: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Busca produtos do Catálogo PG para montar KIT (produto composto) de uma CMIG.

    Endpoint de LOOKUP no escopo da CMIG: a autorização é a mesma da aba "Produtos CMIG"
    (`_check_cmig_access`), e não a menu-key `pg` — o AC monta o KIT mas não administra o PG,
    então `GET /pg` (que exige a menu-key `pg`) devolvia 403 para ele.

    Escopo: PG ATIVO do galpão DA CMIG (é quem separa/expede o kit) e NÃO-composto
    (evita kit-dentro-de-kit).
    """
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    stmt = (
        select(CatalogProduct)
        .where(
            CatalogProduct.is_active == True,  # noqa: E712
            CatalogProduct.is_composite == False,  # noqa: E712
        )
        .order_by(CatalogProduct.title)
        .limit(limit)
    )
    # CMIG sem galpão definido → não filtra por galpão (senão o picker viria vazio).
    if cmig.warehouse_id:
        stmt = stmt.where(CatalogProduct.warehouse_id == cmig.warehouse_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(CatalogProduct.title.ilike(like), CatalogProduct.sku.ilike(like)))

    result = await db.execute(stmt)
    return [
        {
            "id": p.id,
            "sku": p.sku,
            "title": p.title,
            "stock_quantity": p.stock_quantity,
            "cost_price": float(p.cost_price) if p.cost_price is not None else 0.0,
            "is_composite": False,
            **_product_specs(p),
        }
        for p in result.scalars().all()
    ]


@router.get("/{cmig_id}/products/{product_id}")
async def get_cmig_product(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.images))
        .where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    return _serialize_cmig_product(product)


@router.post("/{cmig_id}/products/{product_id}/recalculate-stock")
async def recalculate_cmig_product_stock(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalcula `stock_quantity` deste produto a partir dos eventos canônicos
    (NFes finalizadas/autorizadas + pedidos shipped/delivered).
    `stock_quantity` é apenas cache — esta operação re-deriva do histórico.
    """
    from services.fiscal.stock_audit import log_adjustment
    from services.fiscal.stock_calculator import recompute_cmig_product_stock

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    product = (
        await db.execute(
            select(CMIGProduct).where(
                and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
            )
        )
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    old = int(product.stock_quantity or 0)
    new = await recompute_cmig_product_stock(product_id, db)
    await log_adjustment(
        db,
        product_type="cmig",
        product_id=product_id,
        old_value=old,
        new_value=new,
        kind="recompute",
        reason="Recálculo solicitado via POST /cmigs/{id}/products/{id}/recalculate-stock",
        user_id=current_user.id,
    )
    await db.commit()
    return {"old_stock": old, "new_stock": new, "delta": (new or 0) - old}


@router.post("/{cmig_id}/products", status_code=201)
async def create_cmig_product(
    cmig_id: int,
    body: CMIGProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    if current_user.role == "ugo":
        raise HTTPException(
            status_code=403, detail="UGO não pode criar Produtos CMIG. Use importação de PG."
        )

    dup = await db.execute(
        select(CMIGProduct).where(
            and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.sku_cmig == body.sku_cmig)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU CMIG já cadastrado nesta CMIG")

    payload = body.model_dump(exclude={"components"})
    product = CMIGProduct(cmig_id=cmig_id, **payload)
    db.add(product)
    await db.flush()

    if body.is_composite and body.components:
        for comp in body.components:
            if not comp.cmig_product_id and not comp.catalog_product_id:
                continue
            db.add(
                CMIGProductComponent(
                    composite_id=product.id,
                    cmig_product_id=comp.cmig_product_id,
                    catalog_product_id=comp.catalog_product_id,
                    quantity=max(comp.quantity, 1),
                )
            )

    await db.commit()
    await db.refresh(product)
    return _serialize_cmig_product(product)


@router.put("/{cmig_id}/products/{product_id}")
async def update_cmig_product(
    cmig_id: int,
    product_id: int,
    body: CMIGProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(
            and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    payload = body.model_dump(exclude_none=True)
    images = payload.pop("images", None)
    components = payload.pop("components", None)
    new_sku = payload.pop("sku_cmig", None)
    cascade_linked = payload.pop("cascade_sku_to_linked", False)

    # Validação + propagação de SKU
    cascade_summary = {"pg_updated": False, "listings_updated": 0}
    if new_sku is not None:
        new_sku = new_sku.strip()
        if not new_sku:
            raise HTTPException(status_code=422, detail="SKU não pode ser vazio")
        if new_sku != product.sku_cmig:
            # Checa unicidade dentro da CMIG
            dup = (
                await db.execute(
                    select(CMIGProduct).where(
                        and_(
                            CMIGProduct.cmig_id == cmig_id,
                            CMIGProduct.sku_cmig == new_sku,
                            CMIGProduct.id != product_id,
                        )
                    )
                )
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(
                    status_code=409, detail=f"SKU '{new_sku}' já está em uso nesta CMIG"
                )
            product.sku_cmig = new_sku

            if cascade_linked:
                # Propaga para PG vinculado (se houver)
                if product.pg_product_id:
                    pg = (
                        await db.execute(
                            select(CatalogProduct).where(CatalogProduct.id == product.pg_product_id)
                        )
                    ).scalar_one_or_none()
                    if pg and pg.sku != new_sku:
                        pg_dup = (
                            await db.execute(
                                select(CatalogProduct).where(
                                    and_(
                                        CatalogProduct.sku == new_sku,
                                        CatalogProduct.id != pg.id,
                                    )
                                )
                            )
                        ).scalar_one_or_none()
                        if pg_dup:
                            raise HTTPException(
                                status_code=409,
                                detail=f"Cascata abortada: SKU '{new_sku}' já em uso no PG #{pg_dup.id}",
                            )
                        pg.sku = new_sku
                        cascade_summary["pg_updated"] = True

                # Propaga para anúncios vinculados a este CMIGProduct
                lst_result = await db.execute(
                    _sa_update(ProductListing)
                    .where(ProductListing.cmig_product_id == product_id)
                    .values(sku=new_sku)
                )
                cascade_summary["listings_updated"] = lst_result.rowcount or 0

    for field, value in payload.items():
        setattr(product, field, value)

    # Sincronizar imagens se fornecidas (substitui o conteúdo da tabela)
    if images is not None:
        await db.execute(
            _sa_delete(CMIGProductImage).where(CMIGProductImage.cmig_product_id == product_id)
        )
        for i, img in enumerate(images):
            url = img.get("url") if isinstance(img, dict) else str(img)
            if url:
                db.add(
                    CMIGProductImage(
                        cmig_product_id=product_id,
                        url=url,
                        sort_order=i,
                        is_primary=(i == 0),
                    )
                )

    # Substituir componentes se fornecidos e produto é composto
    if components is not None and product.is_composite:
        await db.execute(
            _sa_delete(CMIGProductComponent).where(CMIGProductComponent.composite_id == product_id)
        )
        for comp in components:
            if not comp.get("cmig_product_id") and not comp.get("catalog_product_id"):
                continue
            db.add(
                CMIGProductComponent(
                    composite_id=product_id,
                    cmig_product_id=comp.get("cmig_product_id"),
                    catalog_product_id=comp.get("catalog_product_id"),
                    quantity=max(comp.get("quantity", 1), 1),
                )
            )

    await db.commit()
    await db.refresh(product)
    result = _serialize_cmig_product(product)
    if cascade_summary["pg_updated"] or cascade_summary["listings_updated"]:
        result["_cascade"] = cascade_summary
    return result


@router.post("/{cmig_id}/products/{product_id}/duplicate", status_code=201)
async def duplicate_cmig_product(
    cmig_id: int,
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Duplica um produto CMIG com o SKU informado pelo usuário."""
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct)
        .options(
            selectinload(CMIGProduct.images),
            selectinload(CMIGProduct.variants),
            selectinload(CMIGProduct.components),
        )
        .where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    src = result.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    new_sku = (body.get("sku_cmig") or "").strip()
    if not new_sku:
        raise HTTPException(status_code=422, detail="SKU é obrigatório para duplicar o produto")
    if (
        await db.execute(
            select(CMIGProduct).where(
                and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.sku_cmig == new_sku)
            )
        )
    ).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"SKU '{new_sku}' já está em uso nesta CMIG")

    copy = CMIGProduct(
        cmig_id=cmig_id,
        sku_cmig=new_sku,
        title=f"{src.title} (Cópia)",
        description=src.description,
        brand=src.brand,
        model=src.model,
        ean=src.ean,
        cost_price=src.cost_price,
        suggested_price=src.suggested_price,
        weight_kg=src.weight_kg,
        height_cm=src.height_cm,
        width_cm=src.width_cm,
        length_cm=src.length_cm,
        ncm=src.ncm,
        cest=src.cest,
        origin=src.origin,
        csosn=src.csosn,
        category_id=src.category_id,
        video_id=src.video_id,
        attributes_json=src.attributes_json,
        is_composite=src.is_composite,
        # pg_product_id intencionalmente omitido — cópia começa sem vínculo
    )
    db.add(copy)
    await db.flush()

    for i, img in enumerate(sorted(src.images, key=lambda x: x.sort_order)):
        db.add(
            CMIGProductImage(
                cmig_product_id=copy.id, url=img.url, sort_order=i, is_primary=(i == 0)
            )
        )

    for v in src.variants:
        v_sku = f"{v.sku}-copia"
        v_suffix = 2
        while (
            await db.execute(select(CMIGProductVariant).where(CMIGProductVariant.sku == v_sku))
        ).scalar_one_or_none():
            v_sku = f"{v.sku}-copia-{v_suffix}"
            v_suffix += 1
        db.add(
            CMIGProductVariant(
                cmig_product_id=copy.id,
                sku=v_sku,
                variant_name=v.variant_name,
                color=v.color,
                size_label=v.size_label,
                voltage=v.voltage,
                price_modifier=v.price_modifier,
                suggested_price=v.suggested_price,
                attributes_json=v.attributes_json,
            )
        )

    if src.is_composite:
        for comp in src.components:
            db.add(
                CMIGProductComponent(
                    composite_id=copy.id,
                    cmig_product_id=comp.cmig_product_id,
                    catalog_product_id=comp.catalog_product_id,
                    quantity=comp.quantity,
                )
            )

    await db.commit()
    await db.refresh(copy)
    return _serialize_cmig_product(copy)


@router.delete("/{cmig_id}/products/{product_id}")
async def delete_cmig_product(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(
            and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    # Espelho FULL: registro interno que segura o estoque FULL — não pode ser excluído
    # nem desativado (senão o FULL fica órfão). Gerencie o produto pelo PG vinculado.
    if getattr(product, "is_full_mirror", False):
        raise HTTPException(
            status_code=400,
            detail="Este é o registro de estoque FULL (espelho do produto PG) e não pode "
                   "ser excluído. Gerencie o produto pelo cadastro PG correspondente.",
        )

    # Verificar pedidos internos via PG vinculado
    has_sales = False
    if product.pg_product_id:
        r = await db.execute(
            select(func.count())
            .select_from(OrderItem)
            .where(OrderItem.catalog_product_id == product.pg_product_id)
        )
        has_sales = (r.scalar() or 0) > 0

    if has_sales:
        product.is_active = False
        await db.commit()
        return {
            "action": "deactivated",
            "message": "Produto desativado pois possui pedidos registrados.",
        }

    # Sem vendas — limpar FK em ProductListing antes de deletar
    await db.execute(
        _sa_update(ProductListing)
        .where(ProductListing.cmig_product_id == product_id)
        .values(cmig_product_id=None)
    )

    db.delete(product)
    await db.commit()
    return {"action": "deleted", "message": "Produto excluído com sucesso."}


@router.post("/{cmig_id}/products/{product_id}/photos")
async def upload_cmig_product_photo(
    cmig_id: int,
    product_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    await _get_cmig_product_or_404(product_id, cmig_id, db)

    ext = _os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(
            status_code=400, detail="Tipo de arquivo não permitido. Use JPG, PNG, WEBP ou GIF."
        )

    filename = f"{_uuid_mod.uuid4().hex}{ext}"
    dest_dir = "static/uploads/cmig-products"
    _os.makedirs(dest_dir, exist_ok=True)
    with open(f"{dest_dir}/{filename}", "wb") as out:
        _shutil.copyfileobj(file.file, out)

    return {"url": f"/static/uploads/cmig-products/{filename}"}


@router.post("/{cmig_id}/products/{product_id}/link-pg")
async def link_cmig_product_to_pg(
    cmig_id: int,
    product_id: int,
    body: CMIGProductLinkPG,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AC vincula um Produto CMIG a um PG existente (vínculo de similaridade)."""
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(
            and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    pg = await db.execute(select(CatalogProduct).where(CatalogProduct.id == body.pg_product_id))
    if not pg.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Produto PG não encontrado")

    product.pg_product_id = body.pg_product_id
    await db.commit()
    return {"detail": "Produto CMIG vinculado ao PG com sucesso"}


@router.post("/{cmig_id}/import-from-pg", status_code=201)
async def import_pg_to_cmig(
    cmig_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AC cria um CMIGProduct a partir de um produto PG (Catálogo Geral) buscado por SKU.

    Body: {"sku": "<SKU do PG>"}
    Cria um novo CMIGProduct copiando dados do PG e ja deixando o vínculo
    (`pg_product_id`) setado. Imagens são copiadas. Variantes são copiadas
    quando existem. Evita duplicar quando ja existe CMIGProduct nessa CMIG
    vinculado ao mesmo PG.
    """
    sku_raw = (body or {}).get("sku")
    if not sku_raw or not str(sku_raw).strip():
        raise HTTPException(status_code=400, detail="Informe o SKU do produto PG")
    sku = str(sku_raw).strip()

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    pg = (
        await db.execute(
            select(CatalogProduct)
            .options(
                selectinload(CatalogProduct.images),
                selectinload(CatalogProduct.variants),
                selectinload(CatalogProduct.marketplace_categories),
            )
            .where(CatalogProduct.sku == sku)
        )
    ).scalar_one_or_none()
    if not pg:
        raise HTTPException(status_code=404, detail=f"Produto PG com SKU '{sku}' não encontrado")

    # Evita duplicar vínculo na mesma CMIG
    already = (
        await db.execute(
            select(CMIGProduct).where(
                and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.pg_product_id == pg.id)
            )
        )
    ).scalar_one_or_none()
    if already:
        raise HTTPException(
            status_code=409,
            detail=f"PG '{pg.sku}' já está vinculado ao CMIGProduct #{already.id} ('{already.sku_cmig}') nesta CMIG",
        )

    # Resolve sku_cmig: preserva o sku do PG; se já existe nessa CMIG, adiciona sufixo
    base_sku = pg.sku
    sku_cmig = base_sku
    suffix = 2
    while (
        await db.execute(
            select(CMIGProduct).where(
                and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.sku_cmig == sku_cmig)
            )
        )
    ).scalar_one_or_none():
        sku_cmig = f"{base_sku}-{suffix}"
        suffix += 1

    cp = CMIGProduct(
        cmig_id=cmig_id,
        sku_cmig=sku_cmig,
        title=pg.title,
        description=pg.description,
        brand=pg.brand,
        model=pg.model,
        ean=pg.ean,
        cost_price=pg.cost_price,
        suggested_price=pg.suggested_price,
        weight_kg=pg.weight_kg,
        height_cm=pg.height_cm,
        width_cm=pg.width_cm,
        length_cm=pg.length_cm,
        ncm=pg.ncm,
        cest=pg.cest,
        origin=pg.origin or 0,
        csosn=pg.csosn,
        category_id=pg.category_id,
        video_id=pg.video_id,
        attributes_json=pg.attributes_json,
        is_composite=False,
        is_active=True,
        pg_product_id=pg.id,
    )
    db.add(cp)
    await db.flush()

    # Copia imagens do PG para o CMIG
    photos_imported = 0
    for i, img in enumerate(sorted(pg.images or [], key=lambda x: x.sort_order or 0)):
        db.add(
            CMIGProductImage(
                cmig_product_id=cp.id,
                url=img.url,
                sort_order=img.sort_order if img.sort_order is not None else i,
                is_primary=bool(img.is_primary) or (i == 0),
            )
        )
        photos_imported += 1

    # Copia variantes do PG → CMIG (mesmo padrão de import-to-pg)
    variants_imported = 0
    for v in pg.variants or []:
        db.add(
            CMIGProductVariant(
                cmig_product_id=cp.id,
                sku=f"{v.sku}-{cmig_id}",
                variant_name=v.variant_name,
                color=v.color,
                size_label=v.size_label,
                voltage=v.voltage,
                price_modifier=v.price_modifier,
                suggested_price=v.suggested_price,
                attributes_json=v.attributes_json,
            )
        )
        variants_imported += 1

    # Copia categorias de marketplace (ML/Shopee) do PG → CMIG
    # CHECK do banco exige exatamente um de (catalog_product_id, cmig_product_id);
    # passamos catalog_product_id=None pois agora o owner é o CMIGProduct.
    marketplace_categories_imported = 0
    for mc in pg.marketplace_categories or []:
        db.add(
            ProductMarketplaceCategory(
                catalog_product_id=None,
                cmig_product_id=cp.id,
                marketplace=mc.marketplace,
                category_id=mc.category_id,
                category_name=mc.category_name,
                category_path_json=mc.category_path_json,
                attributes_json=mc.attributes_json,
            )
        )
        marketplace_categories_imported += 1

    await db.commit()
    await db.refresh(cp)

    return {
        "id": cp.id,
        "sku_cmig": cp.sku_cmig,
        "title": cp.title,
        "pg_product_id": pg.id,
        "pg_sku": pg.sku,
        "photos_imported": photos_imported,
        "variants_imported": variants_imported,
        "marketplace_categories_imported": marketplace_categories_imported,
    }


@router.post("/{cmig_id}/products/{product_id}/import-to-pg", status_code=201)
async def import_cmig_product_to_pg(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """UGO importa um Produto CMIG para o PG do seu Galpão (um a um)."""
    import json as _json_imp

    if current_user.role not in ("ugo", "admin"):
        raise HTTPException(
            status_code=403, detail="Apenas UGO pode importar Produtos CMIG para o PG"
        )

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.variants), selectinload(CMIGProduct.images))
        .where(and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id))
    )
    cp = result.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    if cp.pg_product_id:
        raise HTTPException(status_code=409, detail="Produto CMIG já está vinculado a um PG")

    sku_pg = cp.sku_cmig

    existing_pg = (
        await db.execute(select(CatalogProduct).where(CatalogProduct.sku == sku_pg))
    ).scalar_one_or_none()
    if existing_pg:
        raise HTTPException(
            status_code=409,
            detail=f"SKU '{sku_pg}' já existe no catálogo PG (produto #{existing_pg.id})",
        )

    pg = CatalogProduct(
        warehouse_id=current_user.warehouse_id,
        sku=sku_pg,
        title=cp.title,
        description=cp.description or "",
        cost_price=cp.cost_price or 0,
        suggested_price=cp.suggested_price,
        model=cp.model,
        ean=cp.ean,
        weight_kg=cp.weight_kg,
        height_cm=cp.height_cm,
        width_cm=cp.width_cm,
        length_cm=cp.length_cm,
        ncm=cp.ncm,
        cest=cp.cest,
        brand=cp.brand,
        origin=cp.origin or 0,
        csosn=cp.csosn,
        category_id=cp.category_id,
        video_id=cp.video_id,
        attributes_json=cp.attributes_json,
        stock_quantity=cp.stock_quantity or 0,
        is_active=True,
    )
    db.add(pg)
    await db.flush()

    # Importar fotos: prefere a tabela cmig_product_images; fallback p/ pictures_json (legado)
    photos_imported = 0
    if cp.images:
        for i, img in enumerate(cp.images):
            db.add(
                CatalogProductImage(
                    product_id=pg.id,
                    url=img.url,
                    sort_order=img.sort_order if img.sort_order is not None else i,
                    is_primary=bool(img.is_primary) or (i == 0),
                )
            )
            photos_imported += 1
    elif cp.pictures_json:
        try:
            pics = _json_imp.loads(cp.pictures_json)
            for i, pic in enumerate(pics):
                url = pic.get("url") if isinstance(pic, dict) else str(pic)
                if url:
                    db.add(
                        CatalogProductImage(
                            product_id=pg.id,
                            url=url,
                            sort_order=i,
                            is_primary=(i == 0),
                        )
                    )
                    photos_imported += 1
        except Exception:
            pass

    # Importar variantes → CatalogProductVariant
    variants_imported = 0
    for _i, v in enumerate(cp.variants or []):
        var_sku = v.sku
        db.add(
            CatalogProductVariant(
                product_id=pg.id,
                sku=var_sku,
                variant_name=v.variant_name,
                color=v.color,
                size_label=v.size_label,
                voltage=v.voltage,
                stock_quantity=v.stock_quantity or 0,
                price_modifier=v.price_modifier or 0,
                attributes_json=v.attributes_json,
            )
        )
        variants_imported += 1

    cp.pg_product_id = pg.id
    await db.commit()
    await db.refresh(pg)
    return {
        "detail": "Produto importado para o PG com sucesso",
        "pg_product_id": pg.id,
        "sku": sku_pg,
        "photos_imported": photos_imported,
        "variants_imported": variants_imported,
        "brand": pg.brand,
        "model": pg.model,
        "ean": pg.ean,
    }


@router.post("/{cmig_id}/products/{product_id}/sync-pg")
async def sync_pg_from_cmig(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza os campos do PG vinculado com os dados atuais do Produto CMIG."""
    if current_user.role not in ("ugo", "admin"):
        raise HTTPException(
            status_code=403, detail="Apenas UGO pode sincronizar Produtos CMIG com PG"
        )

    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProduct).where(
            and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
        )
    )
    cp = result.scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    if not cp.pg_product_id:
        raise HTTPException(status_code=400, detail="Produto CMIG não está vinculado a um PG")

    pg_result = await db.execute(
        select(CatalogProduct).where(CatalogProduct.id == cp.pg_product_id)
    )
    pg = pg_result.scalar_one_or_none()
    if not pg:
        raise HTTPException(status_code=404, detail="Produto PG vinculado não encontrado")

    if cp.brand is not None:
        pg.brand = cp.brand
    if cp.model is not None:
        pg.model = cp.model
    if cp.ean is not None:
        pg.ean = cp.ean
    if cp.ncm is not None:
        pg.ncm = cp.ncm
    if cp.cest is not None:
        pg.cest = cp.cest
    if cp.weight_kg is not None:
        pg.weight_kg = cp.weight_kg
    if cp.height_cm is not None:
        pg.height_cm = cp.height_cm
    if cp.width_cm is not None:
        pg.width_cm = cp.width_cm
    if cp.length_cm is not None:
        pg.length_cm = cp.length_cm
    if cp.origin is not None:
        pg.origin = cp.origin
    if cp.csosn is not None:
        pg.csosn = cp.csosn
    if cp.category_id is not None:
        pg.category_id = cp.category_id
    if cp.video_id is not None:
        pg.video_id = cp.video_id
    if cp.attributes_json is not None:
        pg.attributes_json = cp.attributes_json

    await db.commit()
    return {
        "detail": "Produto PG atualizado com dados do CMIG",
        "pg_product_id": pg.id,
        "brand": cp.brand,
        "model": cp.model,
        "ean": cp.ean,
        "ncm": cp.ncm,
        "cest": cp.cest,
    }


# ── Variantes de Produtos CMIG ─────────────────────────────────────────────────


async def _get_cmig_product_or_404(product_id: int, cmig_id: int, db: AsyncSession) -> CMIGProduct:
    result = await db.execute(
        select(CMIGProduct).where(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
    return product


@router.get("/{cmig_id}/products/{product_id}/variants")
async def list_cmig_product_variants(
    cmig_id: int,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    await _get_cmig_product_or_404(product_id, cmig_id, db)

    result = await db.execute(
        select(CMIGProductVariant).where(CMIGProductVariant.cmig_product_id == product_id)
    )
    variants = result.scalars().all()
    return [_serialize_variant(v) for v in variants]


@router.post("/{cmig_id}/products/{product_id}/variants", status_code=201)
async def create_cmig_product_variant(
    cmig_id: int,
    product_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)
    await _get_cmig_product_or_404(product_id, cmig_id, db)

    sku = (body.get("sku") or "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="sku é obrigatório")

    dup = await db.execute(select(CMIGProductVariant).where(CMIGProductVariant.sku == sku))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU de variante já cadastrado")

    variant = CMIGProductVariant(
        cmig_product_id=product_id,
        sku=sku,
        variant_name=body.get("variant_name"),
        color=body.get("color"),
        size_label=body.get("size_label") or body.get("size"),
        voltage=body.get("voltage"),
        stock_quantity=int(body.get("stock_quantity", 0)),
        price_modifier=body.get("price_modifier", 0),
        suggested_price=body.get("suggested_price"),
        attributes_json=body.get("attributes_json"),
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.put("/{cmig_id}/products/{product_id}/variants/{variant_id}")
async def update_cmig_product_variant(
    cmig_id: int,
    product_id: int,
    variant_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProductVariant).where(
            CMIGProductVariant.id == variant_id,
            CMIGProductVariant.cmig_product_id == product_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada")

    for field in (
        "variant_name",
        "color",
        "size_label",
        "voltage",
        "stock_quantity",
        "price_modifier",
        "suggested_price",
        "attributes_json",
    ):
        if field in body:
            setattr(variant, field, body[field])

    await db.commit()
    await db.refresh(variant)
    return _serialize_variant(variant)


@router.delete("/{cmig_id}/products/{product_id}/variants/{variant_id}", status_code=204)
async def delete_cmig_product_variant(
    cmig_id: int,
    product_id: int,
    variant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(CMIGProductVariant).where(
            CMIGProductVariant.id == variant_id,
            CMIGProductVariant.cmig_product_id == product_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variante não encontrada")

    db.delete(variant)
    await db.commit()


def _serialize_variant(v: CMIGProductVariant) -> dict:
    return {
        "id": v.id,
        "cmig_product_id": v.cmig_product_id,
        "sku": v.sku,
        "variant_name": v.variant_name,
        "color": v.color,
        "size_label": v.size_label,
        "voltage": v.voltage,
        "stock_quantity": v.stock_quantity,
        "price_modifier": float(v.price_modifier) if v.price_modifier is not None else 0,
        "suggested_price": float(v.suggested_price) if v.suggested_price is not None else None,
        "attributes_json": v.attributes_json,
    }


# ── Histórico de movimentação de estoque ───────────────────────────────────────


@router.get("/{cmig_id}/products/{product_id}/stock-movements")
async def get_cmig_product_stock_movements(
    cmig_id: int,
    product_id: int,
    start_date: _date | None = Query(None, description="Início do período (inclusivo)"),
    end_date: _date | None = Query(None, description="Fim do período (inclusivo)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Histórico de movimentação de estoque do CMIGProduct.

    Agrega NFes finalizadas/autorizadas + pedidos de marketplace com
    `shipment_status IN ('shipped','delivered')`. Para cada pedido calcula
    o split CMIG↔PG conforme a regra: enquanto houver estoque CMIG projetado
    positivo, debita CMIG; overflow vai pra PG.

    Retorna saldos NFe-only (verdade do banco) + saldo disponível (NFe − reservado).
    """
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    product = (
        await db.execute(
            select(CMIGProduct).where(
                and_(CMIGProduct.id == product_id, CMIGProduct.cmig_id == cmig_id)
            )
        )
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")

    from services.stock_movements import build_movements_response
    return await build_movements_response(
        product=product,
        product_type="cmig",
        db=db,
        start_date=start_date,
        end_date=end_date,
    )


# ── Configuração NF-e ──────────────────────────────────────────────────────────


@router.get("/{cmig_id}/nfe-configs/{cm_id}", response_model=list[NFeConfigOut])
async def list_nfe_configs(
    cmig_id: int,
    cm_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(select(NFeConfig).where(NFeConfig.cm_id == cm_id))
    return result.scalars().all()


@router.post("/{cmig_id}/nfe-configs/{cm_id}", status_code=201, response_model=NFeConfigOut)
async def create_nfe_config(
    cmig_id: int,
    cm_id: int,
    body: NFeConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    if body.issuer not in ("marketplace", "system"):
        raise HTTPException(status_code=422, detail="issuer deve ser 'marketplace' ou 'system'")

    dup = await db.execute(
        select(NFeConfig).where(
            and_(NFeConfig.cm_id == cm_id, NFeConfig.shipping_method == body.shipping_method)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Regra NF-e já existe para este método de envio"
        )

    config = NFeConfig(cm_id=cm_id, **body.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/{cmig_id}/nfe-configs/{cm_id}/{config_id}", response_model=NFeConfigOut)
async def update_nfe_config(
    cmig_id: int,
    cm_id: int,
    config_id: int,
    body: NFeConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(NFeConfig).where(and_(NFeConfig.id == config_id, NFeConfig.cm_id == cm_id))
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração NF-e não encontrada")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(config, field, value)

    await db.commit()
    await db.refresh(config)
    return config


@router.delete("/{cmig_id}/nfe-configs/{cm_id}/{config_id}", status_code=204)
async def delete_nfe_config(
    cmig_id: int,
    cm_id: int,
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig = await _get_cmig_or_404(cmig_id, db)
    await _check_cmig_access(cmig, current_user, db)

    result = await db.execute(
        select(NFeConfig).where(and_(NFeConfig.id == config_id, NFeConfig.cm_id == cm_id))
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração NF-e não encontrada")

    db.delete(config)
    await db.commit()

"""Consistência do Gestor Operacional (GO) dono.

ATENÇÃO — após a unificação Galpão, o papel `go` é o papel do OPERADOR de galpão (papel unificado
que substituiu o antigo `ugo`). Ter papel `go` NÃO significa ser GO-dono. O GO-dono é definido pelo
registro em `goes` + permissões de perfil (menus `go_empresa`/`go_usuarios`), não pelo base_role.

Por isso `ensure_go_record` NÃO deve ser disparado por cadastro de operador
(auth.register_user/register_ugo não o chamam mais). Ele é usado apenas quando um admin PROMOVE
explicitamente um usuário a GO-dono (routers/users.py update, admin-gated) — mantém idempotência.
O bootstrap completo de um dono NOVO (User+GO+Warehouse) é `create_owner_with_warehouse` abaixo,
chamado pela tela Galpões (POST /warehouse com bloco `owner`).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.go import GO
from models.user import User
from models.warehouse import Warehouse


async def create_owner_with_warehouse(
    db: AsyncSession, *, owner: dict, warehouse: dict
) -> GO:
    """Bootstrap de um DONO de Galpão: cria User(role='go') + GO + Warehouse já linkados.

    Ponto ÚNICO desse bootstrap (ADR-0026) — antes vivia no antigo goes.py:create_go (removido);
    agora entra pela criação de galpão com "dono novo" na tela Galpões (POST /warehouse, bloco
    `owner`). NÃO commita (segue a transação do chamador). Falha alto (CLAUDE.md), nunca em silêncio:
      - responsável sem nome/e-mail/senha ou empresa sem razão social/CNPJ → 422
      - CNPJ já em `warehouses` → 409; e-mail já em `users` → 409
    Normaliza CEP e work_type pelas mesmas regras da tela Galpões.
    """
    # Import tardio: _norm_cep/_norm_work_type moram em routers.warehouse, que por sua vez importa
    # este módulo — import no topo fecharia um ciclo. hash_password/system_profile_id_for são de
    # services (sem ciclo), mas ficam aqui junto por coesão do caminho de criação.
    from routers.warehouse import _norm_cep, _norm_color, _norm_work_type
    from services.action_permissions import system_profile_id_for
    from services.auth_service import hash_password

    full_name = (owner.get("full_name") or "").strip()
    user_email = (owner.get("email") or owner.get("user_email") or "").strip()
    password = owner.get("password") or ""
    company_name = (warehouse.get("company_name") or "").strip()
    cnpj = (warehouse.get("cnpj") or "").strip()

    missing = [
        label
        for label, val in (
            ("nome do responsável", full_name),
            ("e-mail de login", user_email),
            ("senha", password),
            ("razão social", company_name),
            ("CNPJ", cnpj),
        )
        if not val
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Para cadastrar um dono novo, informe: " + ", ".join(missing) + ".",
        )

    if (await db.execute(select(Warehouse).where(Warehouse.cnpj == cnpj))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="CNPJ já cadastrado")
    if (await db.execute(select(User).where(User.email == user_email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    user = User(
        email=user_email,
        password_hash=hash_password(password),
        role="go",
        profile_id=await system_profile_id_for("go", db),
        full_name=full_name,
        whatsapp=owner.get("user_whatsapp") or owner.get("whatsapp"),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    go = GO(user_id=user.id, is_active=True)
    db.add(go)
    await db.flush()

    trade_name = warehouse.get("trade_name")
    wh = Warehouse(
        go_id=go.id,
        name=trade_name or company_name,
        work_type=_norm_work_type(warehouse.get("work_type")),
        cnpj=cnpj,
        company_name=company_name,
        trade_name=trade_name,
        phone=warehouse.get("phone"),
        whatsapp=warehouse.get("whatsapp"),
        email=warehouse.get("email"),
        zip_code=_norm_cep(warehouse.get("zip_code")),
        street=warehouse.get("street"),
        number=warehouse.get("number"),
        complement=warehouse.get("complement"),
        neighborhood=warehouse.get("neighborhood"),
        city=warehouse.get("city"),
        state=warehouse.get("state"),
        pix_key_type=warehouse.get("pix_key_type"),
        pix_key=warehouse.get("pix_key"),
        # Paridade com o ramo "dono existente" (routers/warehouse.create_warehouse): o form Galpões
        # mostra estes campos já no cadastro — persistir, não descartar em silêncio (CLAUDE.md).
        pg_requires_prepaid=bool(warehouse.get("pg_requires_prepaid", False)),
        manual_sale_requires_payment=bool(warehouse.get("manual_sale_requires_payment", False)),
        theme_sidebar=_norm_color(warehouse.get("theme_sidebar")),
        theme_accent=_norm_color(warehouse.get("theme_accent")),
        theme_topbar=_norm_color(warehouse.get("theme_topbar")),
        theme_sidebar_text=_norm_color(warehouse.get("theme_sidebar_text")),
        theme_link=_norm_color(warehouse.get("theme_link")),
        notes=warehouse.get("notes"),
    )
    db.add(wh)
    await db.flush()

    # Liga GO e User ao Warehouse (espelha o antigo create_go)
    go.warehouse_id = wh.id
    user.go_id = go.id
    user.warehouse_id = wh.id
    await db.flush()
    return go


async def ensure_go_record(user: User, db: AsyncSession) -> bool:
    """Garante um registro em `goes` para um usuário com papel GO.

    Idempotente: só cria quando `user.role == 'go'` e ainda não há GO para esse `user_id`.
    Não commita (segue a transação do chamador). Retorna True se criou um registro.
    """
    if not user or user.role != "go":
        return False
    existing = (
        await db.execute(select(GO).where(GO.user_id == user.id))
    ).scalar_one_or_none()
    if existing:
        return False
    db.add(GO(user_id=user.id, is_active=True))  # warehouse_id fica nulo até ser atribuído
    return True

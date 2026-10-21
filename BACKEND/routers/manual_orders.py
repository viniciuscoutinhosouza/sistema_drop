import json
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.order import Order, OrderItem
from models.payment import PaymentCharge
from models.person import Person
from models.product import CatalogProduct
from models.user import User
from services.file_naming import TIPO_ETIQUETA, order_download_filename
from services.product_mode import assert_product_group_allowed
from services.shipping_mode import MODE_COMBINADO

router = APIRouter()


@router.post("", status_code=201)
async def create_manual_order(
    body: dict,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Cria um Pedido Manual com carrinho (PG + CMIG) e cliente vindo de people.

    Body:
        {
          "cmig_id": int,
          "buyer_person_id": int | null,
          "shipping_address": dict | null,   # override opcional do endereco da Person
          "buyer_name": str | null,          # override opcional
          "buyer_email": str | null,
          "buyer_document": str | null,
          "shipping_cost": float | null,     # frete informado manualmente (default 0)
          "items": [{"kind": "pg"|"cmig", "id": int, "quantity": int, "unit_price": float | null}]
        }

    `unit_price` por item: opcional. Se enviado, usa esse valor como preco de venda
    (permite descontos no carrinho). Se omitido, usa `suggested_price` do produto.
    Produto sem `suggested_price` cadastrado e sem `unit_price` enviado -> 400.
    """
    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=400, detail="cmig_id e obrigatorio")

    items_in = body.get("items") or []
    if not items_in:
        raise HTTPException(status_code=400, detail="O carrinho esta vazio")

    # Acesso a CMIG: AC precisa ser administrador (proprietario ou colaborador).
    cmig_access = await db.execute(
        select(CMIGAdministrator).where(
            CMIGAdministrator.user_id == current_user.id,
            CMIGAdministrator.cmig_id == cmig_id,
        )
    )
    if not cmig_access.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")

    # Cliente (opcional)
    person: Person | None = None
    buyer_person_id = body.get("buyer_person_id")
    if buyer_person_id:
        person_res = await db.execute(select(Person).where(Person.id == buyer_person_id))
        person = person_res.scalar_one_or_none()
        if not person:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        if person.cmig_id != cmig_id:
            raise HTTPException(status_code=400, detail="Cliente nao pertence a esta CMIG")

    # Carrega produtos em batch
    pg_ids = [int(i["id"]) for i in items_in if i.get("kind") == "pg" and i.get("id")]
    cmig_ids = [int(i["id"]) for i in items_in if i.get("kind") == "cmig" and i.get("id")]

    # CMIG do pedido (+ galpão) — autoridade do grupo de produto permitido e do isolamento por galpão.
    cmig_obj = (
        await db.execute(
            select(CMIG).options(selectinload(CMIG.warehouse)).where(CMIG.id == cmig_id)
        )
    ).scalar_one_or_none()
    cmig_wh = cmig_obj.warehouse_id if cmig_obj else None

    pg_map: dict[int, CatalogProduct] = {}
    if pg_ids:
        res = await db.execute(select(CatalogProduct).where(CatalogProduct.id.in_(pg_ids)))
        pg_map = {p.id: p for p in res.scalars().all()}

        # Grupo de produto permitido — ponto único (ADR-0024 multilojas × product_mode migration 149):
        # item PG bloqueia se galpão multilojas OU CMIG em 'cmig_only'. FULL não se aplica (Pedido Manual).
        assert_product_group_allowed(
            cmig_obj, cmig_obj.warehouse if cmig_obj else None, is_pg=True
        )

        # Isolamento por galpão (ADR-0026): os itens PG do pedido TÊM de ser do galpão da CMIG do
        # pedido. Sem esta fronteira no servidor, um usuário de outro galpão conseguia vender PG
        # alheio por POST direto (o fix do /catalog só escondia da UI). O galpão da CMIG é a
        # autoridade (é quem separa/expede).
        for p in pg_map.values():
            if cmig_wh is not None and p.warehouse_id != cmig_wh:
                raise HTTPException(
                    status_code=403,
                    detail=f"Produto PG '{p.sku}' é de outro galpão e não pode entrar neste pedido.",
                )

    cmig_map: dict[int, CMIGProduct] = {}
    if cmig_ids:
        # Grupo de produto permitido — item CMIG bloqueia se a CMIG está em 'pg_only' (migration 149).
        assert_product_group_allowed(
            cmig_obj, cmig_obj.warehouse if cmig_obj else None, is_cmig=True
        )
        res = await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.id.in_(cmig_ids), CMIGProduct.cmig_id == cmig_id
            )
        )
        cmig_map = {p.id: p for p in res.scalars().all()}

    # Monta lista normalizada e valida quantidades/precos
    normalized: list[dict] = []
    sale_total = Decimal("0")
    cost_total = Decimal("0")

    def _resolve_unit_price(raw_price, suggested, sku: str) -> Decimal:
        # Override do usuario tem prioridade (descontos). Caso ausente, usa suggested.
        if raw_price is not None and raw_price != "":
            try:
                value = Decimal(str(raw_price))
            except Exception:
                raise HTTPException(
                    status_code=400, detail=f"Preco unitario invalido para {sku}"
                ) from None
            if value <= 0:
                raise HTTPException(
                    status_code=400, detail=f"Preco unitario deve ser maior que 0 para {sku}"
                )
            return value
        if suggested is None:
            raise HTTPException(
                status_code=400,
                detail=f"Produto {sku} sem preco de venda cadastrado",
            )
        return Decimal(str(suggested))

    for raw in items_in:
        kind = raw.get("kind")
        pid = int(raw.get("id") or 0)
        qty = int(raw.get("quantity") or 0)
        if qty <= 0 or qty > 100000:
            raise HTTPException(status_code=400, detail="Quantidade invalida no carrinho")
        if kind == "pg":
            prod = pg_map.get(pid)
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produto PG {pid} nao encontrado")
            sku = prod.sku
            sale_unit = _resolve_unit_price(raw.get("unit_price"), prod.suggested_price, sku)
            cost_unit = Decimal(str(prod.cost_price or 0))
            normalized.append({
                "kind": "pg",
                "product": prod,
                "sku": sku,
                "title": prod.title,
                "quantity": qty,
                "unit_price": sale_unit,
                "unit_cost": cost_unit,
                # Preço de referência (snapshot) p/ detectar desconto no checkout público (ADR-0033).
                "list_price": (
                    Decimal(str(prod.suggested_price)) if prod.suggested_price is not None else None
                ),
            })
        elif kind == "cmig":
            prod = cmig_map.get(pid)
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produto CMIG {pid} nao encontrado")
            sku = prod.sku_cmig
            sale_unit = _resolve_unit_price(raw.get("unit_price"), prod.suggested_price, sku)
            cost_unit = Decimal(str(prod.cost_price or 0))
            normalized.append({
                "kind": "cmig",
                "product": prod,
                "sku": sku,
                "title": prod.title,
                "quantity": qty,
                "unit_price": sale_unit,
                "unit_cost": cost_unit,
                "list_price": (
                    Decimal(str(prod.suggested_price)) if prod.suggested_price is not None else None
                ),
            })
        else:
            raise HTTPException(status_code=400, detail=f"Tipo de item invalido: {kind}")
        sale_total += sale_unit * qty
        cost_total += cost_unit * qty

    # Snapshot do comprador — body sobrescreve Person; Person serve de fallback.
    buyer_name = body.get("buyer_name") or (person.name if person else current_user.full_name)
    buyer_email = body.get("buyer_email") or (person.email if person else None)
    buyer_document = body.get("buyer_document") or (person.document if person else None)

    shipping_address = body.get("shipping_address")
    if not shipping_address and person:
        shipping_address = {
            "zip_code": person.zip_code,
            "street": person.street,
            "number": person.address_number,
            "complement": person.complement,
            "neighborhood": person.neighborhood,
            "city": person.city,
            "state": person.state,
        }
    shipping_address = shipping_address or {}

    # Frete informado pelo usuario (opcional, default 0)
    raw_shipping = body.get("shipping_cost")
    if raw_shipping is None or raw_shipping == "":
        shipping_cost = Decimal("0")
    else:
        try:
            shipping_cost = Decimal(str(raw_shipping))
        except Exception:
            raise HTTPException(status_code=400, detail="shipping_cost invalido") from None
        if shipping_cost < 0:
            raise HTTPException(status_code=400, detail="shipping_cost deve ser >= 0")

    # Itens CMIG ja sao propriedade da Conta CMIG do vendedor — nao geram debito.
    # Pedido 100% CMIG SEM frete a pagar entra direto como pago (nao tem o que cobrar).
    pg_cost_total = sum(
        n["unit_cost"] * n["quantity"] for n in normalized if n["kind"] == "pg"
    )
    is_fully_cmig = pg_cost_total == 0 and shipping_cost == 0

    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from uuid import uuid4
    order = Order(
        dropshipper_id=current_user.id,
        cmig_id=cmig_id,
        platform="manual",
        # platform_order_id NÃO pode ficar NULL: o índice único (platform, platform_order_id,
        # dropshipper) não aceita 2 linhas ('manual', NULL, dropshipper) — o 2º pedido manual do
        # mesmo vendedor batia ORA-00001. Placeholder único só p/ passar o INSERT; vira str(id)
        # logo após o flush (estável, único por pedido; o eShip já usava `... or str(id)`).
        platform_order_id=f"MANUAL-TMP-{uuid4().hex}",
        status="paid" if is_fully_cmig else "downloaded",
        payment_status="paid" if is_fully_cmig else "pending",
        paid_at=_datetime.now(_UTC) if is_fully_cmig else None,
        buyer_person_id=person.id if person else None,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        buyer_document=buyer_document,
        shipping_address=json.dumps(shipping_address, ensure_ascii=False),
        sale_amount=sale_total,
        product_cost=cost_total,
        shipping_cost=shipping_cost,
        shipping_mode=MODE_COMBINADO,
    )
    db.add(order)
    await db.flush()
    order.platform_order_id = str(order.id)

    for n in normalized:
        item_kwargs = {
            "order_id": order.id,
            "sku": n["sku"],
            "title": n["title"],
            "quantity": n["quantity"],
            "unit_price": n["unit_price"],
            "unit_cost": n["unit_cost"],
            "list_price": n.get("list_price"),
            "catalog_source": n["kind"],  # 'pg' | 'cmig'
        }
        if n["kind"] == "pg":
            item_kwargs["catalog_product_id"] = n["product"].id
        else:
            # CMIG: salva FK propria + espelha pg_product_id em catalog_product_id
            # (manter o espelhamento preserva o calculo de estoque em
            # _fetch_direct_pg_order_events; catalog_source='cmig' garante que
            # o item nao seja confundido com PG puro).
            item_kwargs["cmig_product_id"] = n["product"].id
            if n["product"].pg_product_id:
                item_kwargs["catalog_product_id"] = n["product"].pg_product_id
        db.add(OrderItem(**item_kwargs))

    await db.commit()

    # Trigger recalculo de estoque (cobre kits via explosao de componentes)
    try:
        from services.fiscal.stock_calculator import (
            trigger_stock_recompute_on_order_created,
        )
        await trigger_stock_recompute_on_order_created(order, db)
    except Exception:
        pass

    return {"id": order.id, "status": order.status}


async def _load_manual_label_data(order_id: int, current_user: User, db: AsyncSession):
    """Carrega (order, items, cmig, items_meta) de um pedido manual, validando acesso.

    Fonte única para as etiquetas PDF e ZPL — evita divergência entre os dois formatos.
    """
    order = (
        await db.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    if order.platform != "manual":
        raise HTTPException(
            status_code=400,
            detail="Etiqueta direta disponivel apenas para pedidos manuais",
        )

    # Permissao: dono direto OU admin da CMIG do pedido
    is_owner = order.dropshipper_id == current_user.id
    is_admin = False
    if not is_owner and order.cmig_id:
        admin_res = await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == order.cmig_id,
            )
        )
        is_admin = admin_res.scalar_one_or_none() is not None
    if not (is_owner or is_admin or current_user.role == "admin"):
        raise HTTPException(status_code=403, detail="Sem acesso a este pedido")

    items = (
        await db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)
        )
    ).scalars().all()

    cmig = None
    if order.cmig_id:
        cmig = (
            await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
        ).scalar_one_or_none()

    # Resolve EAN de cada item via PG ou CMIG (catalog_source)
    items_meta: list[dict] = []
    for it in items:
        ean = ""
        title = it.title or ""
        if it.cmig_product_id:
            cp = (
                await db.execute(
                    select(CMIGProduct).where(CMIGProduct.id == it.cmig_product_id)
                )
            ).scalar_one_or_none()
            if cp:
                ean = (cp.ean or "").strip()
                title = title or cp.title
        elif it.catalog_product_id:
            pg = (
                await db.execute(
                    select(CatalogProduct).where(CatalogProduct.id == it.catalog_product_id)
                )
            ).scalar_one_or_none()
            if pg:
                ean = (pg.ean or "").strip()
                title = title or pg.title
        items_meta.append({"ean": ean, "title": title})

    return order, items, cmig, items_meta


@router.get("/{order_id}/label.pdf")
async def manual_order_label(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera etiqueta PDF (100x150mm) para pedido direto/manual.

    Acessivel para o dropshipper dono do pedido ou colaborador da CMIG dele.
    Uma pagina por OrderItem (volume).
    """
    from services.label_service import render_manual_order_label

    order, items, cmig, items_meta = await _load_manual_label_data(order_id, current_user, db)
    pdf = render_manual_order_label(order=order, items=items, cmig=cmig, items_meta=items_meta)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="{order_download_filename(TIPO_ETIQUETA, "pdf", order=order)}"'
        },
    )


@router.get("/{order_id}/label.zpl")
async def manual_order_label_zpl(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera a etiqueta em ZPL (impressora térmica Zebra 10x15) do pedido direto/manual.

    Espelha `/label.pdf` — mesma carga de dados, saída ZPL (uma etiqueta por volume).
    """
    from services.label_service import render_manual_order_label_zpl

    order, items, cmig, items_meta = await _load_manual_label_data(order_id, current_user, db)
    zpl = render_manual_order_label_zpl(order=order, items=items, cmig=cmig, items_meta=items_meta)
    return Response(
        content=zpl,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="{order_download_filename(TIPO_ETIQUETA, "zpl", order=order)}"'
        },
    )


# ─── Cobrança ASAAS do pedido manual (Fase 2, ADR-0032) ─────────────────────────


def _serialize_charge(c: PaymentCharge) -> dict:
    return {
        "id": c.id,
        "order_id": c.order_id,
        "provider": c.provider,
        "status": c.status,
        "billing_type": c.billing_type,
        "value": float(c.value) if c.value is not None else 0,
        "invoice_url": c.invoice_url,
        "bank_slip_url": c.bank_slip_url,
        "pix_payload": c.pix_payload,
        "due_date": c.due_date.isoformat() if c.due_date else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _load_manual_order_checked(order_id: int, user: User, db: AsyncSession) -> Order:
    """Carrega o pedido MANUAL e aplica o acesso por CMIG (admin bypassa; senao CMIGAdministrator)."""
    order = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado")
    if order.platform != "manual":
        raise HTTPException(status_code=400, detail="Cobranca disponivel apenas para pedido manual")
    if not order.cmig_id:
        raise HTTPException(status_code=400, detail="Pedido sem CMIG vinculada")
    if user.role != "admin":
        acc = await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.user_id == user.id,
                CMIGAdministrator.cmig_id == order.cmig_id,
            )
        )
        if not acc.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")
    return order


@router.post("/{order_id}/create-charge")
async def create_charge(
    order_id: int,
    body: dict | None = None,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Gera uma cobranca no ASAAS (link/Pix/boleto) para o pedido manual, pela conta principal do
    Galpao da CMIG do pedido. Reentrante: se ja ha cobranca viva, retorna a existente.
    Ponto unico: services.charge_service (mesmo caminho do checkout publico)."""
    from services import charge_service

    body = body or {}
    order = await _load_manual_order_checked(order_id, current_user, db)
    if order.needs_price_review:
        raise HTTPException(
            status_code=409,
            detail="Pedido aguardando re-analise de preco (cliente alterou itens com desconto)",
        )
    due_date = None
    if body.get("due_date"):
        try:
            due_date = date.fromisoformat(str(body["due_date"])[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="due_date invalido (AAAA-MM-DD)") from None
    charge = await charge_service.get_or_create_charge(
        db, order, billing_type=body.get("billing_type") or "UNDEFINED", due_date=due_date
    )
    return _serialize_charge(charge)


@router.get("/{order_id}/charges")
async def list_charges(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    order = await _load_manual_order_checked(order_id, current_user, db)
    rows = (
        await db.execute(
            select(PaymentCharge)
            .where(PaymentCharge.order_id == order.id)
            .order_by(PaymentCharge.id.desc())
        )
    ).scalars().all()
    return [_serialize_charge(c) for c in rows]


@router.post("/{order_id}/charges/{charge_id}/refresh")
async def refresh_charge(
    order_id: int,
    charge_id: int,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Reconcilia o status da cobranca com o ASAAS (o webhook e at-least-once e pode se perder)."""
    from services import charge_service

    order = await _load_manual_order_checked(order_id, current_user, db)
    charge = (
        await db.execute(
            select(PaymentCharge).where(
                PaymentCharge.id == charge_id, PaymentCharge.order_id == order.id
            )
        )
    ).scalar_one_or_none()
    if not charge:
        raise HTTPException(status_code=404, detail="Cobranca nao encontrada neste pedido")
    charge = await charge_service.reconcile_charge(db, order, charge)
    return _serialize_charge(charge)


@router.post("/{order_id}/charges/{charge_id}/cancel")
async def cancel_charge(
    order_id: int,
    charge_id: int,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Cancela a cobranca no ASAAS (operador gerou com valor/forma errados). Bloqueia se ja paga."""
    from services import asaas_service, charge_service

    order = await _load_manual_order_checked(order_id, current_user, db)
    charge = (
        await db.execute(
            select(PaymentCharge).where(
                PaymentCharge.id == charge_id, PaymentCharge.order_id == order.id
            )
        )
    ).scalar_one_or_none()
    if not charge:
        raise HTTPException(status_code=404, detail="Cobranca nao encontrada neste pedido")
    if (charge.status or "").upper() in charge_service.PAID_CHARGE:
        raise HTTPException(status_code=409, detail="Cobranca ja paga - nao pode ser cancelada")
    bank = await charge_service.load_bank_for_charge(db, charge)
    try:
        await asaas_service.cancel_payment(bank, charge.asaas_payment_id)
    except asaas_service.AsaasError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    charge.status = "CANCELLED"
    await db.commit()
    await db.refresh(charge)
    return _serialize_charge(charge)


# ─── Checkout público (Fase 3, ADR-0033) — lado do operador ─────────────────────


def _checkout_stage(order: Order, has_live_charge: bool) -> str:
    """Estágio derivado (sem coluna redundante). pedido → pagamento → pago.
    Separação/Enviado/Entregue (status separated/shipped) ficam adiados pelo dono."""
    if order.payment_status == "paid":
        return "pago"
    if order.public_token or has_live_charge:
        return "pagamento"
    return "pedido"


def _public_checkout_url(token: str) -> str:
    from config import get_settings

    base = (get_settings().FRONTEND_URL or "").rstrip("/")
    return f"{base}/checkout/{token}"


@router.get("/{order_id}/checkout-info")
async def checkout_info(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Info do checkout do pedido manual (estágio, re-análise, link público) para a tela do operador."""
    from services import charge_service

    order = await _load_manual_order_checked(order_id, current_user, db)
    live = await charge_service.get_live_charge(db, order.id)
    return {
        "stage": _checkout_stage(order, live is not None),
        "needs_price_review": bool(order.needs_price_review),
        "has_public_link": bool(order.public_token),
        "public_url": _public_checkout_url(order.public_token) if order.public_token else None,
        "payment_status": order.payment_status,
    }


@router.post("/{order_id}/public-link")
async def public_link(
    order_id: int,
    body: dict | None = None,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Gera (ou regenera, com body {regenerate:true}) o token de checkout público do pedido.
    Regenerar invalida o link anterior."""
    body = body or {}
    order = await _load_manual_order_checked(order_id, current_user, db)
    if not order.public_token or body.get("regenerate"):
        order.public_token = secrets.token_urlsafe(32)
        order.public_token_created_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(order)
    return {"public_url": _public_checkout_url(order.public_token), "token": order.public_token}


@router.delete("/{order_id}/public-link", status_code=204)
async def revoke_public_link(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Revoga o link público do pedido (ex.: vazou ou o pedido foi cancelado). Desliga o checkout."""
    order = await _load_manual_order_checked(order_id, current_user, db)
    order.public_token = None
    order.public_token_created_at = None
    await db.commit()


@router.post("/{order_id}/price-review/approve")
async def approve_price_review(
    order_id: int,
    current_user: User = Depends(require_menu_permission("pedido_manual")),
    db: AsyncSession = Depends(get_db),
):
    """Operador re-analisou o preço após o cliente alterar itens com desconto: libera o pagamento."""
    order = await _load_manual_order_checked(order_id, current_user, db)
    order.needs_price_review = False
    await db.commit()
    return {"ok": True, "needs_price_review": False}

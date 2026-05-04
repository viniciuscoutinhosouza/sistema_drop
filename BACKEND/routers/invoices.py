from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from datetime import datetime, date
from decimal import Decimal

from database import get_db
from dependencies import get_current_user
from models.user import User
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.person import Person
from models.order import Order, OrderItem
from models.fiscal import Invoice, InvoiceItem, InvoiceEvent, CMIGFiscalConfig
import json as _json
from services.fiscal.nfe_xml_parser import parse_nfe_xml
from services.fiscal import focus_service, dfe_service
from services.fiscal.tax_calculator import calculate_item_taxes, suggest_cfop
import uuid as _uuid

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession) -> CMIG:
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    if user.role == "admin":
        return cmig
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        return cmig
    if user.role == "ac":
        admin = (
            await db.execute(
                select(CMIGAdministrator).where(
                    and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig_id)
                )
            )
        ).scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        return cmig
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


async def _accessible_cmig_ids(user: User, db: AsyncSession) -> list[int]:
    if user.role == "admin":
        rows = await db.execute(select(CMIG.id))
    elif user.role == "ugo":
        rows = await db.execute(select(CMIG.id).where(CMIG.warehouse_id == user.warehouse_id))
    elif user.role == "ac":
        rows = await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
    else:
        return []
    return [r[0] for r in rows.all()]


def _f(v) -> float | None:
    if v is None:
        return None
    return float(v)


def _serialize_item(it: InvoiceItem) -> dict:
    return {
        "id": it.id,
        "invoice_id": it.invoice_id,
        "item_number": it.item_number,
        "cmig_product_id": it.cmig_product_id,
        "cfop": it.cfop,
        "ncm": it.ncm,
        "cest": it.cest,
        "description": it.description,
        "ean": it.ean,
        "unit": it.unit,
        "quantity": _f(it.quantity),
        "unit_value": _f(it.unit_value),
        "total_value": _f(it.total_value),
        "discount": _f(it.discount),
        "freight_value": _f(it.freight_value),
        "insurance_value": _f(it.insurance_value),
        "other_value": _f(it.other_value),
        "origin": it.origin,
        "icms_cst": it.icms_cst,
        "icms_csosn": it.icms_csosn,
        "icms_base": _f(it.icms_base),
        "icms_aliquota": _f(it.icms_aliquota),
        "icms_value": _f(it.icms_value),
        "icms_st_base": _f(it.icms_st_base),
        "icms_st_aliquota": _f(it.icms_st_aliquota),
        "icms_st_value": _f(it.icms_st_value),
        "ipi_cst": it.ipi_cst,
        "ipi_aliquota": _f(it.ipi_aliquota),
        "ipi_value": _f(it.ipi_value),
        "pis_cst": it.pis_cst,
        "pis_aliquota": _f(it.pis_aliquota),
        "pis_value": _f(it.pis_value),
        "cofins_cst": it.cofins_cst,
        "cofins_aliquota": _f(it.cofins_aliquota),
        "cofins_value": _f(it.cofins_value),
        "additional_info": it.additional_info,
    }


def _serialize_event(ev: InvoiceEvent) -> dict:
    return {
        "id": ev.id,
        "invoice_id": ev.invoice_id,
        "event_type": ev.event_type,
        "sequence_number": ev.sequence_number,
        "reason": ev.reason,
        "focus_ref": ev.focus_ref,
        "sefaz_protocol": ev.sefaz_protocol,
        "sefaz_status_code": ev.sefaz_status_code,
        "sefaz_message": ev.sefaz_message,
        "xml_url": ev.xml_url,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
        "created_by_user_id": ev.created_by_user_id,
    }


def _serialize(inv: Invoice, with_items: bool = False, with_events: bool = False,
               person: Person | None = None) -> dict:
    out = {
        "id": inv.id,
        "cmig_id": inv.cmig_id,
        "direction": inv.direction,
        "purpose": inv.purpose,
        "model": inv.model,
        "serie": inv.serie,
        "nfe_number": inv.nfe_number,
        "access_key": inv.access_key,
        "person_id": inv.person_id,
        "order_id": inv.order_id,
        "inbound_invoice_id": inv.inbound_invoice_id,
        "natureza_operacao": inv.natureza_operacao,
        "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
        "exit_date": inv.exit_date.isoformat() if inv.exit_date else None,
        "status": inv.status,
        "inbound_source": inv.inbound_source,
        "manifestation": inv.manifestation,
        "manifestation_at": inv.manifestation_at.isoformat() if inv.manifestation_at else None,
        "manifestation_protocol": inv.manifestation_protocol,
        "stock_updated": bool(inv.stock_updated),
        "focus_ref": inv.focus_ref,
        "focus_status": inv.focus_status,
        "focus_message": inv.focus_message,
        "xml_url": inv.xml_url,
        "danfe_url": inv.danfe_url,
        "total_products": _f(inv.total_products),
        "total_freight": _f(inv.total_freight),
        "total_insurance": _f(inv.total_insurance),
        "total_discount": _f(inv.total_discount),
        "total_other": _f(inv.total_other),
        "total_icms": _f(inv.total_icms),
        "total_icms_st": _f(inv.total_icms_st),
        "total_pis": _f(inv.total_pis),
        "total_cofins": _f(inv.total_cofins),
        "total_ipi": _f(inv.total_ipi),
        "total_invoice": _f(inv.total_invoice),
        "freight_modality": inv.freight_modality,
        "carrier_person_id": inv.carrier_person_id,
        "payment_method": inv.payment_method,
        "payment_terms_json": inv.payment_terms_json,
        "additional_info": inv.additional_info,
        "fiscal_info": inv.fiscal_info,
        "cancelled_at": inv.cancelled_at.isoformat() if inv.cancelled_at else None,
        "cancel_reason": inv.cancel_reason,
        "cancel_protocol": inv.cancel_protocol,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        "created_by_user_id": inv.created_by_user_id,
    }
    if person is not None:
        out["person"] = {
            "id": person.id,
            "name": person.name,
            "trade_name": person.trade_name,
            "document": person.document,
            "person_type": person.person_type,
            "city": person.city,
            "state": person.state,
        }
    if with_items:
        out["items"] = [_serialize_item(it) for it in (inv.items or [])]
    if with_events:
        out["events"] = [_serialize_event(ev) for ev in (inv.events or [])]
    return out


def _recompute_totals(inv: Invoice):
    """Soma totais dos itens em memória e grava no Invoice."""
    items = inv.items or []
    inv.total_products = sum((it.total_value or Decimal(0)) for it in items)
    inv.total_freight = sum((it.freight_value or Decimal(0)) for it in items)
    inv.total_insurance = sum((it.insurance_value or Decimal(0)) for it in items)
    inv.total_discount = sum((it.discount or Decimal(0)) for it in items)
    inv.total_other = sum((it.other_value or Decimal(0)) for it in items)
    inv.total_icms = sum((it.icms_value or Decimal(0)) for it in items)
    inv.total_icms_st = sum((it.icms_st_value or Decimal(0)) for it in items)
    inv.total_pis = sum((it.pis_value or Decimal(0)) for it in items)
    inv.total_cofins = sum((it.cofins_value or Decimal(0)) for it in items)
    inv.total_ipi = sum((it.ipi_value or Decimal(0)) for it in items)
    inv.total_invoice = (
        (inv.total_products or Decimal(0))
        + (inv.total_freight or Decimal(0))
        + (inv.total_insurance or Decimal(0))
        + (inv.total_other or Decimal(0))
        + (inv.total_icms_st or Decimal(0))
        + (inv.total_ipi or Decimal(0))
        - (inv.total_discount or Decimal(0))
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_invoices(
    cmig_id: int | None = Query(None),
    direction: str | None = Query(None, regex="^(in|out)$"),
    status: str | None = Query(None),
    purpose: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    person_id: int | None = Query(None),
    manifestation: str | None = Query(None),
    inbound_source: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    stmt = select(Invoice)
    if cmig_id is not None:
        if cmig_id not in accessible:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        stmt = stmt.where(Invoice.cmig_id == cmig_id)
    else:
        stmt = stmt.where(Invoice.cmig_id.in_(accessible))

    if direction:
        stmt = stmt.where(Invoice.direction == direction)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if purpose:
        stmt = stmt.where(Invoice.purpose == purpose)
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    if person_id is not None:
        stmt = stmt.where(Invoice.person_id == person_id)
    if manifestation:
        stmt = stmt.where(Invoice.manifestation == manifestation)
    if inbound_source:
        stmt = stmt.where(Invoice.inbound_source == inbound_source)
    if search:
        s = f"%{search.strip()}%"
        digits = "".join(c for c in search if c.isdigit())
        conds = [Invoice.access_key.like(s), Invoice.focus_ref.like(s)]
        if digits:
            try:
                conds.append(Invoice.nfe_number == int(digits))
            except ValueError:
                pass
        stmt = stmt.where(or_(*conds))

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = stmt.order_by(Invoice.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    # Carregar Persons em batch
    person_ids = {r.person_id for r in rows if r.person_id}
    persons = {}
    if person_ids:
        ps = (await db.execute(select(Person).where(Person.id.in_(person_ids)))).scalars().all()
        persons = {p.id: p for p in ps}

    return {
        "items": [_serialize(r, person=persons.get(r.person_id)) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = (
        await db.execute(
            select(Invoice)
            .options(selectinload(Invoice.items), selectinload(Invoice.events))
            .where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    person = None
    if inv.person_id:
        person = (await db.execute(select(Person).where(Person.id == inv.person_id))).scalar_one_or_none()

    return _serialize(inv, with_items=True, with_events=True, person=person)


@router.post("", status_code=201)
async def create_invoice(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=422, detail="cmig_id é obrigatório")
    await _check_cmig_access(cmig_id, current_user, db)

    direction = body.get("direction") or "out"
    if direction not in ("in", "out"):
        raise HTTPException(status_code=422, detail="direction deve ser 'in' ou 'out'")

    purpose = body.get("purpose") or "venda"
    valid_purposes = ("venda", "devolucao", "remessa", "retorno",
                       "transferencia", "complementar", "ajuste", "outros")
    if purpose not in valid_purposes:
        raise HTTPException(status_code=422, detail=f"purpose deve ser um de: {valid_purposes}")

    person_id = body.get("person_id")
    if person_id:
        p = (await db.execute(
            select(Person).where(and_(Person.id == person_id, Person.cmig_id == cmig_id))
        )).scalar_one_or_none()
        if not p:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada nesta CMIG")

    issue_date = body.get("issue_date")
    if issue_date and isinstance(issue_date, str):
        try:
            issue_date = datetime.fromisoformat(issue_date.replace("Z", "+00:00"))
        except ValueError:
            issue_date = None

    inv = Invoice(
        cmig_id=cmig_id,
        direction=direction,
        purpose=purpose,
        model=body.get("model") or "55",
        person_id=person_id,
        natureza_operacao=body.get("natureza_operacao") or "Venda de mercadoria",
        issue_date=issue_date or datetime.utcnow(),
        status="draft",
        freight_modality=body.get("freight_modality"),
        carrier_person_id=body.get("carrier_person_id"),
        payment_method=body.get("payment_method"),
        additional_info=body.get("additional_info"),
        fiscal_info=body.get("fiscal_info"),
        created_by_user_id=current_user.id,
        # Para entradas manuais, marcar manifestation como 'not_required'
        manifestation="not_required" if direction == "in" else None,
        inbound_source="manual" if direction == "in" else None,
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    return _serialize(inv, with_items=True, with_events=True)


@router.patch("/{invoice_id}")
async def update_invoice(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    if inv.status not in ("draft",):
        raise HTTPException(status_code=400, detail=f"Não é possível editar NFe com status '{inv.status}'")

    editable = {
        "purpose", "natureza_operacao", "person_id", "freight_modality",
        "carrier_person_id", "payment_method", "payment_terms_json",
        "additional_info", "fiscal_info", "exit_date", "issue_date",
        "inbound_invoice_id",
    }
    for k, v in body.items():
        if k in editable:
            if k in ("issue_date", "exit_date") and isinstance(v, str):
                try:
                    v = datetime.fromisoformat(v.replace("Z", "+00:00"))
                except ValueError:
                    continue
            setattr(inv, k, v)

    await db.commit()
    await db.refresh(inv)
    return _serialize(inv)


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status not in ("draft",):
        raise HTTPException(status_code=400, detail=f"Não é possível excluir NFe com status '{inv.status}'")
    db.delete(inv)
    await db.commit()


# ── Itens ─────────────────────────────────────────────────────────────────────

async def _get_invoice_for_edit(invoice_id: int, user: User, db: AsyncSession) -> Invoice:
    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, user, db)
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail=f"NFe em status '{inv.status}' não pode ser editada")
    return inv


@router.post("/{invoice_id}/items", status_code=201)
async def add_item(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)

    description = (body.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=422, detail="description é obrigatório")

    next_seq = (max([it.item_number for it in (inv.items or [])], default=0) or 0) + 1

    quantity = Decimal(str(body.get("quantity") or 1))
    unit_value = Decimal(str(body.get("unit_value") or 0))
    total_value = body.get("total_value")
    if total_value is None:
        total_value = quantity * unit_value
    else:
        total_value = Decimal(str(total_value))

    item = InvoiceItem(
        invoice_id=invoice_id,
        item_number=next_seq,
        cmig_product_id=body.get("cmig_product_id"),
        cfop=body.get("cfop"),
        ncm=body.get("ncm"),
        cest=body.get("cest"),
        description=description,
        ean=body.get("ean"),
        unit=body.get("unit") or "UN",
        quantity=quantity,
        unit_value=unit_value,
        total_value=total_value,
        discount=Decimal(str(body.get("discount") or 0)),
        freight_value=Decimal(str(body.get("freight_value") or 0)),
        insurance_value=Decimal(str(body.get("insurance_value") or 0)),
        other_value=Decimal(str(body.get("other_value") or 0)),
        origin=body.get("origin", 0),
        icms_cst=body.get("icms_cst"),
        icms_csosn=body.get("icms_csosn"),
        icms_base=Decimal(str(body.get("icms_base") or 0)),
        icms_aliquota=Decimal(str(body.get("icms_aliquota") or 0)),
        icms_value=Decimal(str(body.get("icms_value") or 0)),
        ipi_cst=body.get("ipi_cst"),
        ipi_aliquota=Decimal(str(body.get("ipi_aliquota") or 0)),
        ipi_value=Decimal(str(body.get("ipi_value") or 0)),
        pis_cst=body.get("pis_cst"),
        pis_aliquota=Decimal(str(body.get("pis_aliquota") or 0)),
        pis_value=Decimal(str(body.get("pis_value") or 0)),
        cofins_cst=body.get("cofins_cst"),
        cofins_aliquota=Decimal(str(body.get("cofins_aliquota") or 0)),
        cofins_value=Decimal(str(body.get("cofins_value") or 0)),
        additional_info=body.get("additional_info"),
    )
    db.add(item)
    await db.flush()
    # Recarregar items e recomputar totais
    await db.refresh(inv, attribute_names=["items"])
    _recompute_totals(inv)
    await db.commit()
    await db.refresh(item)
    return _serialize_item(item)


@router.patch("/{invoice_id}/items/{item_id}")
async def update_item(
    invoice_id: int,
    item_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)
    item = next((it for it in (inv.items or []) if it.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    decimal_fields = {
        "quantity", "unit_value", "total_value", "discount", "freight_value",
        "insurance_value", "other_value", "icms_base", "icms_aliquota", "icms_value",
        "icms_st_base", "icms_st_aliquota", "icms_st_value",
        "ipi_aliquota", "ipi_value", "pis_aliquota", "pis_value",
        "cofins_aliquota", "cofins_value",
    }
    str_fields = {
        "cfop", "ncm", "cest", "description", "ean", "unit",
        "icms_cst", "icms_csosn", "ipi_cst", "pis_cst", "cofins_cst", "additional_info",
    }
    int_fields = {"origin", "cmig_product_id"}

    for k, v in body.items():
        if k in decimal_fields and v is not None:
            setattr(item, k, Decimal(str(v)))
        elif k in str_fields:
            setattr(item, k, v)
        elif k in int_fields:
            setattr(item, k, v)

    # Recalcular total se quantity ou unit_value mudaram e total_value não foi enviado
    if ("quantity" in body or "unit_value" in body) and "total_value" not in body:
        item.total_value = (item.quantity or Decimal(0)) * (item.unit_value or Decimal(0))

    _recompute_totals(inv)
    await db.commit()
    await db.refresh(item)
    return _serialize_item(item)


@router.delete("/{invoice_id}/items/{item_id}", status_code=204)
async def delete_item(
    invoice_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)
    item = next((it for it in (inv.items or []) if it.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    db.delete(item)
    await db.flush()
    await db.refresh(inv, attribute_names=["items"])
    _recompute_totals(inv)
    await db.commit()


# ── Cálculo de impostos / Transmissão Focus NFe ──────────────────────────────

async def _get_fiscal_config(cmig_id: int, db: AsyncSession) -> CMIGFiscalConfig:
    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
    ).scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=400, detail="CMIG sem configuração fiscal cadastrada")
    return cfg


@router.post("/{invoice_id}/calculate-taxes")
async def calculate_taxes(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalcula impostos de todos os itens com base no CRT da CMIG e CFOP do item."""
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)
    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()
    person = None
    if inv.person_id:
        person = (await db.execute(select(Person).where(Person.id == inv.person_id))).scalar_one_or_none()

    # Sugerir CFOP se ainda não tiver
    suggested_cfop = suggest_cfop(
        purpose=inv.purpose,
        uf_emit=cmig.state,
        uf_dest=person.state if person else cmig.state,
    )

    for item in (inv.items or []):
        if not item.cfop:
            item.cfop = suggested_cfop
        result = calculate_item_taxes(
            crt=cfg.crt or 1,
            cfop=item.cfop,
            base_value=item.total_value,
            icms_aliquota=item.icms_aliquota,
            pis_aliquota=item.pis_aliquota,
            cofins_aliquota=item.cofins_aliquota,
            origin=item.origin or 0,
        )
        for k, v in result.items():
            setattr(item, k, v)

    _recompute_totals(inv)
    await db.commit()
    await db.refresh(inv, attribute_names=["items"])
    return _serialize(inv, with_items=True)


def _validate_ready_to_transmit(inv: Invoice, cfg: CMIGFiscalConfig, person: Person | None):
    if inv.status != "draft":
        raise HTTPException(status_code=400, detail=f"NFe em status '{inv.status}' não pode ser transmitida")
    if not cfg.focus_company_token:
        raise HTTPException(status_code=400, detail="CMIG não está registrada no Focus NFe")
    if not cfg.certificate_uploaded_at:
        raise HTTPException(status_code=400, detail="Certificado A1 não enviado")
    if not person:
        raise HTTPException(status_code=400, detail="Selecione o destinatário antes de transmitir")
    if not inv.items:
        raise HTTPException(status_code=400, detail="NFe sem itens")
    for it in inv.items:
        if not it.cfop:
            raise HTTPException(status_code=400, detail=f"Item {it.item_number} sem CFOP — clique em 'Calcular Impostos'")
        if not it.ncm:
            raise HTTPException(status_code=400, detail=f"Item {it.item_number} sem NCM")


@router.post("/{invoice_id}/transmit")
async def transmit_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transmite NFe para o Focus NFe (que envia à SEFAZ)."""
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)
    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()
    person = None
    if inv.person_id:
        person = (await db.execute(select(Person).where(Person.id == inv.person_id))).scalar_one_or_none()
    carrier = None
    if inv.carrier_person_id:
        carrier = (await db.execute(select(Person).where(Person.id == inv.carrier_person_id))).scalar_one_or_none()

    _validate_ready_to_transmit(inv, cfg, person)

    # Gerar referência única (Focus exige)
    ref = inv.focus_ref or f"inv-{inv.id}-{_uuid.uuid4().hex[:8]}"
    inv.focus_ref = ref
    inv.status = "queued"
    await db.commit()

    payload = focus_service._build_nfe_payload(inv, cmig, cfg, person, inv.items, carrier)

    try:
        result = await focus_service.emit_nfe(cfg, payload, ref)
    except focus_service.FocusError as e:
        inv.status = "rejected"
        inv.focus_status = "erro_envio"
        inv.focus_message = e.message[:2000] if e.message else None
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    # Focus retorna {status, ref} ou {status, ref, ...} sincronamente.
    # Status possíveis: "processando_autorizacao", "autorizado", "denegado", "cancelado", "erro_autorizacao"
    inv.focus_status = result.get("status") or "enviado"
    inv.focus_message = result.get("mensagem_sefaz") or result.get("mensagem")

    if inv.focus_status == "autorizado":
        await _apply_authorized(inv, cfg, result)
    elif inv.focus_status in ("erro_autorizacao", "denegado"):
        inv.status = "denied" if inv.focus_status == "denegado" else "rejected"
    else:
        inv.status = "processing"

    await db.commit()
    await db.refresh(inv, attribute_names=["items"])
    return _serialize(inv, with_items=True)


async def _apply_authorized(inv: Invoice, cfg: CMIGFiscalConfig, focus_payload: dict):
    """Atualiza Invoice com dados retornados pelo Focus quando NFe é autorizada."""
    inv.status = "authorized"
    inv.access_key = focus_payload.get("chave_nfe") or inv.access_key
    inv.nfe_number = (
        int(focus_payload.get("numero")) if focus_payload.get("numero") else inv.nfe_number
    )
    inv.serie = (
        int(focus_payload.get("serie")) if focus_payload.get("serie") else inv.serie
    )
    inv.xml_url = focus_service.absolutize_focus_url(cfg, focus_payload.get("caminho_xml_nota_fiscal") or "")
    inv.danfe_url = focus_service.absolutize_focus_url(cfg, focus_payload.get("caminho_danfe") or "")


@router.post("/{invoice_id}/refresh-status")
async def refresh_status(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reconsulta o status da NFe no Focus (útil para invoices em 'processing')."""
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if not inv.focus_ref:
        raise HTTPException(status_code=400, detail="NFe ainda não foi transmitida")
    cfg = await _get_fiscal_config(inv.cmig_id, db)

    try:
        result = await focus_service.consult_nfe(cfg, inv.focus_ref)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    inv.focus_status = result.get("status") or inv.focus_status
    inv.focus_message = result.get("mensagem_sefaz") or result.get("mensagem")
    if inv.focus_status == "autorizado":
        await _apply_authorized(inv, cfg, result)
    elif inv.focus_status == "cancelado":
        inv.status = "cancelled"
    elif inv.focus_status == "denegado":
        inv.status = "denied"
    elif inv.focus_status in ("erro_autorizacao",):
        inv.status = "rejected"
    await db.commit()
    return {"status": inv.status, "focus_status": inv.focus_status, "focus_message": inv.focus_message}


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancela NFe autorizada (até 24h após autorização)."""
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status != "authorized":
        raise HTTPException(status_code=400, detail="Apenas NFes autorizadas podem ser canceladas")
    if not inv.focus_ref:
        raise HTTPException(status_code=400, detail="NFe sem referência Focus")

    reason = (body.get("reason") or "").strip()
    if len(reason) < 15:
        raise HTTPException(status_code=422, detail="Justificativa deve ter no mínimo 15 caracteres")

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    try:
        result = await focus_service.cancel_nfe(cfg, inv.focus_ref, reason)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    inv.status = "cancelled"
    inv.cancelled_at = datetime.utcnow()
    inv.cancel_reason = reason
    inv.cancel_protocol = result.get("numero_protocolo") or result.get("protocolo")
    db.add(InvoiceEvent(
        invoice_id=inv.id,
        event_type="cancellation",
        reason=reason,
        focus_ref=inv.focus_ref,
        sefaz_protocol=inv.cancel_protocol,
        sefaz_status_code=str(result.get("status_sefaz") or ""),
        sefaz_message=result.get("mensagem_sefaz") or result.get("mensagem"),
        created_by_user_id=current_user.id,
    ))
    await db.commit()
    return {"detail": "NFe cancelada", "protocol": inv.cancel_protocol}


@router.post("/{invoice_id}/correction-letter")
async def send_correction_letter(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia Carta de Correção Eletrônica (CCe). Texto entre 15 e 1000 caracteres."""
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status != "authorized":
        raise HTTPException(status_code=400, detail="CCe só pode ser emitida para NFe autorizada")
    if not inv.focus_ref:
        raise HTTPException(status_code=400, detail="NFe sem referência Focus")

    text = (body.get("text") or "").strip()
    if len(text) < 15 or len(text) > 1000:
        raise HTTPException(status_code=422, detail="Texto deve ter entre 15 e 1000 caracteres")

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    try:
        result = await focus_service.correction_letter(cfg, inv.focus_ref, text)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    # Próximo número da CCe (sequência)
    cce_count = sum(1 for ev in (inv.events or []) if ev.event_type == "correction_letter")
    db.add(InvoiceEvent(
        invoice_id=inv.id,
        event_type="correction_letter",
        sequence_number=cce_count + 1,
        reason=text,
        focus_ref=inv.focus_ref,
        sefaz_protocol=result.get("numero_protocolo") or result.get("protocolo"),
        sefaz_message=result.get("mensagem_sefaz") or result.get("mensagem"),
        created_by_user_id=current_user.id,
    ))
    await db.commit()
    return {"detail": "Carta de correção enviada"}


@router.post("/{invoice_id}/email")
async def email_invoice(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia XML+DANFE por e-mail. Body: {emails: ['a@b.com', ...]}"""
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status != "authorized":
        raise HTTPException(status_code=400, detail="Só é possível enviar e-mail de NFe autorizada")
    if not inv.focus_ref:
        raise HTTPException(status_code=400, detail="NFe sem referência Focus")

    emails = body.get("emails") or []
    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(",") if e.strip()]
    if not emails:
        # fallback: e-mail do destinatário
        if inv.person_id:
            person = (await db.execute(select(Person).where(Person.id == inv.person_id))).scalar_one_or_none()
            if person and person.email:
                emails = [person.email]
    if not emails:
        raise HTTPException(status_code=422, detail="Informe ao menos um e-mail")

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    try:
        await focus_service.send_email(cfg, inv.focus_ref, emails)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    return {"detail": f"E-mail enviado para {len(emails)} destinatário(s)"}


# ── DFe — coleta de NFes recebidas e manifestação ────────────────────────────

@router.post("/sync-received/{cmig_id}")
async def sync_received(
    cmig_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dispara sincronização manual de NFes recebidas via DFe Focus para a CMIG."""
    await _check_cmig_access(cmig_id, current_user, db)
    try:
        result = await dfe_service.sync_received_for_cmig(cmig_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"detail": "Sincronização concluída", **result}


@router.post("/{invoice_id}/manifest")
async def manifest_invoice(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manifesta NFe de entrada.

    Body: {type: 'ciencia'|'confirmacao'|'desconhecimento'|'nao_realizada',
           justificativa?: str, update_stock?: bool}
    """
    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    if inv.direction != "in":
        raise HTTPException(status_code=400, detail="Manifestação só se aplica a NFes de entrada")
    if not inv.access_key:
        raise HTTPException(status_code=400, detail="NFe sem chave de acesso")
    if inv.manifestation and inv.manifestation not in ("pending", "ciencia"):
        # Pode evoluir de Ciência para Confirmação, mas não regredir
        raise HTTPException(
            status_code=400,
            detail=f"NFe já manifestada como '{inv.manifestation}'",
        )

    tipo = body.get("type")
    if tipo not in ("ciencia", "confirmacao", "desconhecimento", "nao_realizada"):
        raise HTTPException(status_code=422, detail="type inválido")

    justificativa = (body.get("justificativa") or "").strip() or None
    if tipo in ("desconhecimento", "nao_realizada"):
        if not justificativa or len(justificativa) < 15:
            raise HTTPException(status_code=422, detail="Justificativa obrigatória (15+ caracteres)")

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    if not cfg.focus_company_token:
        raise HTTPException(status_code=400, detail="CMIG sem token Focus NFe")

    try:
        result = await focus_service.manifest(cfg, inv.access_key, tipo, justificativa)
    except focus_service.FocusError as e:
        raise HTTPException(status_code=502, detail=f"Focus NFe: {e.message}")

    inv.manifestation = tipo
    inv.manifestation_at = datetime.utcnow()
    inv.manifestation_protocol = result.get("numero_protocolo") or result.get("protocolo")

    db.add(InvoiceEvent(
        invoice_id=inv.id,
        event_type="manifestation",
        reason=justificativa,
        focus_ref=inv.focus_ref,
        sefaz_protocol=inv.manifestation_protocol,
        sefaz_message=result.get("mensagem_sefaz") or result.get("mensagem") or tipo,
        created_by_user_id=current_user.id,
    ))
    await db.commit()

    # Atualizar estoque opcionalmente (apenas em Confirmação)
    stock = None
    if tipo == "confirmacao" and body.get("update_stock") and not inv.stock_updated:
        try:
            stock = await dfe_service.update_stock_from_invoice(inv.id)
        except ValueError as e:
            stock = {"error": str(e)}

    return {
        "detail": f"Manifestação '{tipo}' registrada",
        "manifestation": tipo,
        "protocol": inv.manifestation_protocol,
        "stock_update": stock,
    }


@router.post("/{invoice_id}/update-stock")
async def update_stock(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replica itens da entrada para `cmig_products.stock_quantity` por EAN.
    Idempotente — flag `stock_updated` evita reaplicação."""
    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    try:
        result = await dfe_service.update_stock_from_invoice(inv.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"detail": "Estoque atualizado", **result}


# ── Importação de XML (entrada) ───────────────────────────────────────────────

def _normalize_cnpj(s: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", s or "")


async def _upsert_supplier(parsed_emit: dict, cmig_id: int, db: AsyncSession) -> Person:
    """Cria ou atualiza Person (fornecedor) a partir do bloco emit do XML."""
    document = parsed_emit.get("document") or ""
    if not document:
        raise HTTPException(status_code=422, detail="XML não contém documento (CNPJ/CPF) do emitente")

    existing = (
        await db.execute(
            select(Person).where(and_(Person.cmig_id == cmig_id, Person.document == document))
        )
    ).scalar_one_or_none()

    if existing:
        # Marca como fornecedor se ainda não estiver
        if not existing.is_supplier:
            existing.is_supplier = True
        # Atualiza dados se vazios
        if not existing.ie and parsed_emit.get("ie"):
            existing.ie = parsed_emit["ie"]
        if not existing.trade_name and parsed_emit.get("trade_name"):
            existing.trade_name = parsed_emit["trade_name"]
        if not existing.zip_code and parsed_emit.get("zip_code"):
            existing.zip_code = parsed_emit["zip_code"]
            existing.street = parsed_emit.get("street") or existing.street
            existing.address_number = parsed_emit.get("address_number") or existing.address_number
            existing.neighborhood = parsed_emit.get("neighborhood") or existing.neighborhood
            existing.city = parsed_emit.get("city") or existing.city
            existing.state = parsed_emit.get("state") or existing.state
            existing.ibge_code = parsed_emit.get("ibge_code") or existing.ibge_code
        return existing

    p = Person(
        cmig_id=cmig_id,
        person_type=parsed_emit.get("person_type") or "PJ",
        document=document,
        ie=parsed_emit.get("ie") or None,
        ie_isento=False,
        im=parsed_emit.get("im") or None,
        name=parsed_emit.get("name") or "(Sem nome)",
        trade_name=parsed_emit.get("trade_name") or None,
        phone=parsed_emit.get("phone") or None,
        zip_code=parsed_emit.get("zip_code") or None,
        street=parsed_emit.get("street") or None,
        address_number=parsed_emit.get("address_number") or None,
        complement=parsed_emit.get("complement") or None,
        neighborhood=parsed_emit.get("neighborhood") or None,
        city=parsed_emit.get("city") or None,
        state=parsed_emit.get("state") or None,
        ibge_code=parsed_emit.get("ibge_code") or None,
        country_code=parsed_emit.get("country_code") or "1058",
        is_customer=False,
        is_supplier=True,
        is_carrier=False,
        is_active=True,
    )
    db.add(p)
    await db.flush()
    return p


async def _update_stock_from_items(items_data: list[dict], cmig_id: int, db: AsyncSession) -> dict:
    """Para cada item, tenta achar produto CMIG por EAN e incrementar estoque.
    Retorna {matched: int, unmatched: int}."""
    matched = 0
    unmatched = 0
    for it in items_data:
        ean = (it.get("ean") or "").strip()
        if not ean:
            unmatched += 1
            continue
        prod = (
            await db.execute(
                select(CMIGProduct).where(
                    and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.ean == ean)
                )
            )
        ).scalar_one_or_none()
        if not prod:
            unmatched += 1
            continue
        qty = int(it.get("quantity") or 0)
        prod.stock_quantity = (prod.stock_quantity or 0) + qty
        matched += 1
    return {"matched": matched, "unmatched": unmatched}


@router.post("/import-xml", status_code=201)
async def import_xml(
    cmig_id: int = Form(...),
    update_stock: bool = Form(False),
    xml_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Importa um XML de NFe (recebida de fornecedor) como Invoice de entrada."""
    cmig = await _check_cmig_access(cmig_id, current_user, db)

    # Ler conteúdo
    content = await xml_file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo XML vazio")

    # Parsear
    try:
        parsed = parse_nfe_xml(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    access_key = parsed.get("access_key") or ""
    if not access_key or len(access_key) != 44:
        raise HTTPException(status_code=422, detail="Chave de acesso inválida ou ausente no XML")

    # Validar destinatário == CMIG
    dest_cnpj = _normalize_cnpj(parsed.get("dest", {}).get("document", ""))
    cmig_cnpj = _normalize_cnpj(cmig.cnpj)
    if dest_cnpj and cmig_cnpj and dest_cnpj != cmig_cnpj:
        raise HTTPException(
            status_code=422,
            detail=f"XML destinado ao CNPJ {dest_cnpj}, mas a CMIG selecionada é {cmig_cnpj}",
        )

    # Deduplicar por chave
    existing = (
        await db.execute(select(Invoice).where(Invoice.access_key == access_key))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"NFe já importada (Invoice #{existing.id})",
        )

    # Criar/atualizar fornecedor
    supplier = await _upsert_supplier(parsed["emit"], cmig_id, db)

    totals = parsed.get("totals", {})
    transport = parsed.get("transport", {})

    inv = Invoice(
        cmig_id=cmig_id,
        direction="in",
        purpose="venda",  # entrada de venda do fornecedor (compra para nós)
        model=parsed.get("model") or "55",
        serie=parsed.get("serie"),
        nfe_number=parsed.get("nfe_number"),
        access_key=access_key,
        person_id=supplier.id,
        natureza_operacao=parsed.get("natureza_operacao") or "Compra para revenda",
        issue_date=parsed.get("issue_date"),
        exit_date=parsed.get("exit_date"),
        status="authorized",  # XML já vem autorizado pelo emitente
        inbound_source="xml_upload",
        manifestation="not_required",
        freight_modality=transport.get("freight_modality"),
        additional_info=parsed.get("additional_info") or None,
        total_products=totals.get("total_products") or Decimal("0"),
        total_freight=totals.get("total_freight") or Decimal("0"),
        total_insurance=totals.get("total_insurance") or Decimal("0"),
        total_discount=totals.get("total_discount") or Decimal("0"),
        total_other=totals.get("total_other") or Decimal("0"),
        total_icms=totals.get("total_icms") or Decimal("0"),
        total_icms_st=totals.get("total_icms_st") or Decimal("0"),
        total_pis=totals.get("total_pis") or Decimal("0"),
        total_cofins=totals.get("total_cofins") or Decimal("0"),
        total_ipi=totals.get("total_ipi") or Decimal("0"),
        total_invoice=totals.get("total_invoice") or Decimal("0"),
        created_by_user_id=current_user.id,
    )
    db.add(inv)
    await db.flush()

    # Itens
    items_data = parsed.get("items", [])
    for it_data in items_data:
        item = InvoiceItem(
            invoice_id=inv.id,
            item_number=it_data.get("item_number") or 1,
            cfop=it_data.get("cfop") or None,
            ncm=it_data.get("ncm") or None,
            cest=it_data.get("cest") or None,
            description=it_data.get("description") or "(sem descrição)",
            ean=it_data.get("ean") or None,
            unit=it_data.get("unit") or "UN",
            quantity=it_data.get("quantity") or Decimal("0"),
            unit_value=it_data.get("unit_value") or Decimal("0"),
            total_value=it_data.get("total_value") or Decimal("0"),
            discount=it_data.get("discount") or Decimal("0"),
            freight_value=it_data.get("freight_value") or Decimal("0"),
            insurance_value=it_data.get("insurance_value") or Decimal("0"),
            other_value=it_data.get("other_value") or Decimal("0"),
            origin=it_data.get("origin") or 0,
            icms_cst=it_data.get("icms_cst") or None,
            icms_csosn=it_data.get("icms_csosn") or None,
            icms_base=it_data.get("icms_base") or Decimal("0"),
            icms_aliquota=it_data.get("icms_aliquota") or Decimal("0"),
            icms_value=it_data.get("icms_value") or Decimal("0"),
            icms_st_base=it_data.get("icms_st_base") or Decimal("0"),
            icms_st_aliquota=it_data.get("icms_st_aliquota") or Decimal("0"),
            icms_st_value=it_data.get("icms_st_value") or Decimal("0"),
            ipi_cst=it_data.get("ipi_cst") or None,
            ipi_aliquota=it_data.get("ipi_aliquota") or Decimal("0"),
            ipi_value=it_data.get("ipi_value") or Decimal("0"),
            pis_cst=it_data.get("pis_cst") or None,
            pis_aliquota=it_data.get("pis_aliquota") or Decimal("0"),
            pis_value=it_data.get("pis_value") or Decimal("0"),
            cofins_cst=it_data.get("cofins_cst") or None,
            cofins_aliquota=it_data.get("cofins_aliquota") or Decimal("0"),
            cofins_value=it_data.get("cofins_value") or Decimal("0"),
            additional_info=it_data.get("additional_info") or None,
        )
        db.add(item)

    # Atualizar estoque (opcional)
    stock_result = {"matched": 0, "unmatched": 0}
    if update_stock:
        stock_result = await _update_stock_from_items(items_data, cmig_id, db)
        inv.stock_updated = True

    await db.commit()
    await db.refresh(inv, attribute_names=["items"])

    return {
        "invoice_id": inv.id,
        "access_key": access_key,
        "supplier": {"id": supplier.id, "name": supplier.name, "document": supplier.document},
        "items_count": len(items_data),
        "total_invoice": float(inv.total_invoice or 0),
        "stock_update": stock_result if update_stock else None,
    }


# ── Geração de NFe a partir de Pedido (saída automática) ─────────────────────

def _parse_shipping_address(raw: str | None) -> dict:
    """O campo orders.shipping_address é JSON-string (CLOB). Parseia tolerante."""
    if not raw:
        return {}
    try:
        if isinstance(raw, dict):
            return raw
        return _json.loads(raw)
    except (ValueError, TypeError):
        return {}


def _detect_person_type(document: str) -> str:
    digits = "".join(c for c in (document or "") if c.isdigit())
    return "PJ" if len(digits) == 14 else "PF"


async def _upsert_customer_from_order(db: AsyncSession, order: Order, cmig_id: int) -> Person | None:
    """Cria ou encontra Person (cliente) a partir do buyer do Order."""
    document = "".join(c for c in (order.buyer_document or "") if c.isdigit())
    if not document or len(document) not in (11, 14):
        return None

    existing = (
        await db.execute(
            select(Person).where(and_(Person.cmig_id == cmig_id, Person.document == document))
        )
    ).scalar_one_or_none()

    addr = _parse_shipping_address(order.shipping_address)
    # Mapeamento tolerante (formato do ML pode variar)
    street = addr.get("street_name") or addr.get("street") or addr.get("logradouro") or ""
    number = str(addr.get("street_number") or addr.get("number") or "") or ""
    neighborhood = addr.get("neighborhood") or addr.get("bairro") or ""
    city = (
        (addr.get("city") or {}).get("name") if isinstance(addr.get("city"), dict)
        else addr.get("city") or addr.get("municipio") or ""
    )
    state = (
        (addr.get("state") or {}).get("id") if isinstance(addr.get("state"), dict)
        else addr.get("state") or addr.get("uf") or ""
    )
    if isinstance(state, str) and len(state) > 2:
        # ML às vezes manda "BR-SP" — pegar últimos 2 chars
        state = state[-2:]
    zip_code = addr.get("zip_code") or addr.get("cep") or ""
    complement = addr.get("comment") or addr.get("complement") or addr.get("complemento") or ""

    if existing:
        # Atualiza endereço se vazio
        if not existing.street and street:
            existing.street = street
            existing.address_number = number or existing.address_number
            existing.complement = complement or existing.complement
            existing.neighborhood = neighborhood or existing.neighborhood
            existing.city = city or existing.city
            existing.state = state or existing.state
            existing.zip_code = zip_code or existing.zip_code
        if not existing.email and order.buyer_email:
            existing.email = order.buyer_email
        return existing

    p = Person(
        cmig_id=cmig_id,
        person_type=_detect_person_type(document),
        document=document,
        ie_isento=True,  # consumidor final via marketplace é normalmente isento
        name=order.buyer_name or "(Sem nome)",
        email=order.buyer_email,
        zip_code=zip_code,
        street=street,
        address_number=number,
        complement=complement,
        neighborhood=neighborhood,
        city=city,
        state=state,
        country_code="1058",
        is_customer=True,
        is_supplier=False,
        is_active=True,
    )
    db.add(p)
    await db.flush()
    return p


@router.post("/from-order/{order_id}")
async def create_invoice_from_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria invoice draft de saída a partir de um pedido de marketplace."""
    order = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if not order.cmig_id:
        raise HTTPException(status_code=400, detail="Pedido sem CMIG vinculada")
    cmig = await _check_cmig_access(order.cmig_id, current_user, db)

    if order.invoice_id:
        existing = (
            await db.execute(select(Invoice).where(Invoice.id == order.invoice_id))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Pedido já possui NFe vinculada (Invoice #{existing.id})",
            )

    if not order.items:
        raise HTTPException(status_code=400, detail="Pedido sem itens")

    # Upsert cliente
    customer = await _upsert_customer_from_order(db, order, order.cmig_id)
    if not customer:
        raise HTTPException(
            status_code=400,
            detail="Pedido sem CPF/CNPJ do comprador (necessário para emitir NFe)",
        )

    # CFOP automático
    cfop = suggest_cfop(
        purpose="venda",
        uf_emit=cmig.state,
        uf_dest=customer.state,
    )

    # Buscar configuração fiscal (opcional — só usaremos para natureza_operacao default)
    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == order.cmig_id))
    ).scalar_one_or_none()
    natureza = (cfg.default_natureza_operacao if cfg else None) or "Venda de mercadoria"

    # Criar invoice draft
    inv = Invoice(
        cmig_id=order.cmig_id,
        direction="out",
        purpose="venda",
        model="55",
        person_id=customer.id,
        order_id=order.id,
        natureza_operacao=natureza,
        issue_date=datetime.utcnow(),
        status="draft",
        freight_modality=0 if order.shipping_method else None,
        payment_method="99",  # 99 = outros (já pago no marketplace)
        additional_info=f"Pedido marketplace #{order.platform_order_id or order.id}",
        created_by_user_id=current_user.id,
    )
    db.add(inv)
    await db.flush()

    # Mapear OrderItem → InvoiceItem
    items_unmapped: list[str] = []
    seq = 0
    for oi in order.items:
        seq += 1
        cmig_product = None
        # Tenta achar CMIGProduct vinculado ao mesmo PG (catalog_product_id)
        if oi.catalog_product_id:
            cmig_product = (
                await db.execute(
                    select(CMIGProduct).where(
                        and_(
                            CMIGProduct.cmig_id == order.cmig_id,
                            CMIGProduct.pg_product_id == oi.catalog_product_id,
                        )
                    )
                )
            ).scalar_one_or_none()
        # Fallback: por SKU CMIG
        if not cmig_product and oi.sku:
            cmig_product = (
                await db.execute(
                    select(CMIGProduct).where(
                        and_(CMIGProduct.cmig_id == order.cmig_id, CMIGProduct.sku_cmig == oi.sku)
                    )
                )
            ).scalar_one_or_none()

        if not cmig_product:
            items_unmapped.append(oi.sku or oi.title or f"item #{seq}")

        unit_price = Decimal(str(oi.unit_price or 0))
        quantity = Decimal(str(oi.quantity or 1))

        item = InvoiceItem(
            invoice_id=inv.id,
            item_number=seq,
            cmig_product_id=cmig_product.id if cmig_product else None,
            cfop=cfop,
            ncm=cmig_product.ncm if cmig_product else None,
            cest=cmig_product.cest if cmig_product else None,
            description=(oi.title or (cmig_product.title if cmig_product else "(sem descrição)"))[:500],
            ean=cmig_product.ean if cmig_product else None,
            unit="UN",
            quantity=quantity,
            unit_value=unit_price,
            total_value=(quantity * unit_price).quantize(Decimal("0.01")),
            origin=cmig_product.origin if cmig_product else 0,
        )
        db.add(item)

    # Vincular order ↔ invoice
    order.invoice_id = inv.id

    await db.commit()
    await db.refresh(inv, attribute_names=["items"])
    _recompute_totals(inv)
    await db.commit()
    await db.refresh(inv)

    return {
        "invoice_id": inv.id,
        "order_id": order.id,
        "customer": {"id": customer.id, "name": customer.name, "document": customer.document},
        "items_count": len(order.items),
        "items_without_cmig_product": items_unmapped,
        "cfop": cfop,
        "total_invoice": float(inv.total_invoice or 0),
        "warnings": (
            [f"Sem produto CMIG vinculado: {', '.join(items_unmapped[:5])}"]
            if items_unmapped else []
        ),
    }

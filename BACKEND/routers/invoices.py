import asyncio
import io as _io
import json as _json
import logging
import re as _re
import zipfile as _zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path as _Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db, task_db
from dependencies import get_current_user, require_menu_permission, require_role
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct
from models.fiscal import CMIGFiscalConfig, Invoice, InvoiceEvent, InvoiceItem, NfeInutilizacao
from models.integration import MarketplaceAccount
from models.order import Order
from models.person import Person
from models.product import CatalogProduct
from models.user import User
from services import audit_service
from services import ml_service as _ml
from services.file_naming import TIPO_DANFE, TIPO_NFE, order_download_filename
from services.fiscal import dfe_service, sefaz_service
from services.fiscal.icms_table import compute_difal, get_icms_rate
from services.fiscal.nfe_xml_parser import parse_nfe_xml
from services.fiscal.sefaz.exceptions import FiscalError as _SefazFiscalError
from services.fiscal.sefaz.exceptions import SefazError as _SefazNetError
from services.fiscal.tax_calculator import calculate_item_taxes, suggest_cfop

logger = logging.getLogger(__name__)

_BG_TASKS: set = set()  # retém tasks de background (evita coleta prematura pelo GC)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _norm_ncm(v):
    if not v:
        return v
    return v.replace(".", "").replace("-", "")[:8] or None


def _norm_cest(v):
    if not v:
        return v
    return v.replace(".", "").replace("-", "")[:7] or None


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
    # Fallback: itens antigos (criados antes da migration 61) podem ter sku NULL.
    # Se o item está vinculado a um CMIGProduct, usa o sku_cmig do produto.
    effective_sku = it.sku
    if not effective_sku and it.cmig_product_id:
        try:
            cmig_prod = it.cmig_product  # relacionamento; eager-loaded em get_invoice
        except Exception:
            cmig_prod = None
        if cmig_prod and getattr(cmig_prod, "sku_cmig", None):
            effective_sku = cmig_prod.sku_cmig
    return {
        "id": it.id,
        "invoice_id": it.invoice_id,
        "item_number": it.item_number,
        "cmig_product_id": it.cmig_product_id,
        "catalog_product_id": it.catalog_product_id,
        "sku": effective_sku,
        "source_type": it.source_type,
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


def _serialize(
    inv: Invoice, with_items: bool = False, with_events: bool = False, person: Person | None = None
) -> dict:
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
    sort_by: str | None = Query(None),  # cmig | numero | tipo | emissao
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
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

    _SORT_COLS = {
        "cmig": Invoice.cmig_id,
        "numero": Invoice.nfe_number,
        "tipo": Invoice.inbound_source,
        "emissao": Invoice.issue_date,
    }
    sort_col = _SORT_COLS.get(sort_by)
    if sort_col is not None:
        ordering = sort_col.asc() if sort_dir == "asc" else sort_col.desc()
        stmt = stmt.order_by(ordering.nullslast(), Invoice.created_at.desc())
    else:
        stmt = stmt.order_by(Invoice.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
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


async def _notas_query(
    db: AsyncSession, cmig_ids: list[int], direction: str, status, date_from, date_to, search,
):
    """SELECT base da tela unificada de Notas (Invoice, ambas direções)."""
    stmt = select(Invoice).where(Invoice.cmig_id.in_(cmig_ids))
    if direction in ("in", "out"):
        stmt = stmt.where(Invoice.direction == direction)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Invoice.issue_date <= datetime.combine(date_to, datetime.max.time()))
    if search:
        s = search.strip()
        conds = [Invoice.access_key.like(f"%{s}%"), Invoice.natureza_operacao.ilike(f"%{s}%")]
        if s.isdigit():
            conds.append(Invoice.nfe_number == int(s))
        stmt = stmt.where(or_(*conds))
    return stmt


async def _build_notas_rows(db: AsyncSession, invs: list[Invoice], cmig_names: dict) -> list[dict]:
    """Linhas ricas p/ a tela de Notas: contraparte, CMIG, natureza, CFOP, valor, pedido/plataforma
    (link ao marketplace) e disponibilidade de XML/DANFE. Uniforme p/ entrada e saída."""
    person_ids = {i.person_id for i in invs if i.person_id}
    persons = {}
    if person_ids:
        persons = {
            p.id: p
            for p in (await db.execute(select(Person).where(Person.id.in_(person_ids)))).scalars().all()
        }
    order_ids = {i.order_id for i in invs if i.order_id}
    orders: dict[int, Order] = {}
    if order_ids:
        orders = {
            o.id: o
            for o in (await db.execute(select(Order).where(Order.id.in_(order_ids)))).scalars().all()
        }
    inv_ids = [i.id for i in invs]
    cfop_by_inv: dict[int, str] = {}
    if inv_ids:
        for iid, cfop in (
            await db.execute(
                select(InvoiceItem.invoice_id, InvoiceItem.cfop)
                .where(InvoiceItem.invoice_id.in_(inv_ids), InvoiceItem.cfop.isnot(None))
                .order_by(InvoiceItem.invoice_id, InvoiceItem.item_number)
            )
        ).all():
            cfop_by_inv.setdefault(iid, cfop)

    rows: list[dict] = []
    for inv in invs:
        p = persons.get(inv.person_id)
        o = orders.get(inv.order_id)
        platform = o.platform if o else None
        platform_order_id = o.platform_order_id if o else None
        xml_avail = bool(inv.xml_url) or (inv.status == "authorized" and bool(inv.xml_local_path))
        danfe_avail = bool(inv.danfe_url) or (inv.status == "authorized" and bool(inv.xml_local_path))
        # Faturador ML: sem XML local — baixa via pedido (/orders/{id}/invoices/{ml_invoice_id}/…).
        ml_inv_id = None
        if inv.source == "ml_faturador" and o is not None:
            ml_inv_id = _ml_invoice_id_from_order(o)
            _ok = o.nfe_status == "authorized" and bool(ml_inv_id)
            xml_avail = _ok
            danfe_avail = _ok
        rows.append({
            "ml_invoice_id": ml_inv_id,
            "id": inv.id,
            "source": inv.source,
            "direction": inv.direction,
            "cmig_id": inv.cmig_id,
            "cmig_name": cmig_names.get(inv.cmig_id),
            "nfe_number": inv.nfe_number,
            "serie": inv.serie,
            "access_key": inv.access_key,
            "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
            "counterparty": p.name if p else None,
            "counterparty_document": p.document if p else None,
            "natureza_operacao": inv.natureza_operacao,
            "cfop": cfop_by_inv.get(inv.id),
            "total": _f(inv.total_invoice),
            "status": inv.status,
            "nfe_type_label": _PURPOSE_LABELS.get(inv.purpose, inv.purpose or "—"),
            "order_id": inv.order_id,
            "platform": platform,
            "platform_order_id": platform_order_id,
            "marketplace_url": _marketplace_order_url(platform, platform_order_id),
            "xml_available": xml_avail,
            "danfe_available": danfe_avail,
            "danfe_preview": inv.status in ("draft", "finalized"),
        })
    return rows


def _marketplace_order_url(platform: str | None, platform_order_id: str | None) -> str | None:
    if not platform_order_id:
        return None
    if platform == "mercadolivre":
        return f"https://www.mercadolivre.com.br/vendas/{platform_order_id}/detalhe"
    return None


_NOTAS_SORT_COLS = {
    "emissao": Invoice.issue_date,
    "numero": Invoice.nfe_number,
    "cmig": Invoice.cmig_id,
    "direcao": Invoice.direction,
    "valor": Invoice.total_invoice,
    "status": Invoice.status,
}


@router.get("/notas")
async def list_notas(
    direction: str = Query("all", regex="^(all|in|out)$"),
    cmig_id: int | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    sort_by: str = Query("emissao"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista unificada de NF-e (entrada + saída) com linhas ricas e ordenação por coluna."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
    cmig_ids = [cmig_id] if cmig_id is not None else accessible
    stmt = await _notas_query(db, cmig_ids, direction, status, date_from, date_to, search)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    col = _NOTAS_SORT_COLS.get(sort_by, Invoice.issue_date)
    order = col.asc().nullslast() if sort_dir == "asc" else col.desc().nullslast()
    stmt = stmt.order_by(
        order, Invoice.serie.desc().nullslast(), Invoice.nfe_number.desc().nullslast()
    ).offset((page - 1) * page_size).limit(page_size)
    invs = (await db.execute(stmt)).scalars().all()
    cmig_names = dict(
        (await db.execute(select(CMIG.id, CMIG.company_name).where(CMIG.id.in_(cmig_ids)))).all()
    )
    return {
        "items": await _build_notas_rows(db, invs, cmig_names),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/notas/export")
async def export_notas(
    kind: str = Query(..., regex="^(xml|danfe)$"),
    direction: str = Query("all", regex="^(all|in|out)$"),
    cmig_id: int | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta um .zip com XMLs (ou DANFEs) das NF-e filtradas (entrada + saída), **agrupadas por
    CMIG** (uma pasta por CMIG). Own SEFAZ lê o XML local; Faturador ML baixa do ML."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        raise HTTPException(status_code=404, detail="Nenhuma CMIG acessível")
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
    cmig_ids = [cmig_id] if cmig_id is not None else accessible
    MAX = 400
    stmt = (await _notas_query(db, cmig_ids, direction, status, date_from, date_to, search)).order_by(
        Invoice.serie.desc().nullslast(), Invoice.nfe_number.desc().nullslast()
    ).limit(MAX * 5)
    invs = (await db.execute(stmt)).scalars().all()
    cmig_names = dict(
        (await db.execute(select(CMIG.id, CMIG.company_name).where(CMIG.id.in_(cmig_ids)))).all()
    )
    rows = await _build_notas_rows(db, invs, cmig_names)
    # `danfe_available`/`xml_available` só marca doc COM valor fiscal (autorizado ou XML local).
    # Prévia de rascunho ("SEM VALOR FISCAL") é baixável individualmente, mas de propósito NÃO
    # entra no lote — o zip é o que vai ao contador, não pode conter documento sem valor.
    avail_key = "xml_available" if kind == "xml" else "danfe_available"
    rows = [r for r in rows if r.get(avail_key)]
    capped = len(rows) > MAX
    rows = rows[:MAX]
    if not rows:
        raise HTTPException(status_code=404, detail="Nenhuma NF-e com documento disponível no filtro")

    ml_order_ids = [r["order_id"] for r in rows if r.get("ml_invoice_id") and r.get("order_id")]
    accounts_by_order: dict[int, MarketplaceAccount] = {}
    if ml_order_ids:
        o_rows = (
            await db.execute(select(Order.id, Order.account_id).where(Order.id.in_(ml_order_ids)))
        ).all()
        acc_ids = {aid for _, aid in o_rows if aid}
        accs = {}
        if acc_ids:
            accs = {
                a.id: a
                for a in (
                    await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id.in_(acc_ids)))
                ).scalars().all()
            }
        accounts_by_order = {oid: accs.get(aid) for oid, aid in o_rows}

    ext = "xml" if kind == "xml" else "pdf"
    errors: list[str] = []
    used_names: set[str] = set()
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            label = f"NFe {r['nfe_number'] or r['access_key'] or r['id']}"
            try:
                # NF-e servida pelo backend (sefaz_own / manual-upload): sem ml_invoice_id.
                # Faturador ML: ml_invoice_id preenchido → baixa do ML pelo pedido.
                if not r.get("ml_invoice_id"):
                    finv = (await db.execute(select(Invoice).where(Invoice.id == r["id"]))).scalar_one_or_none()
                    if not finv or not finv.xml_local_path:
                        errors.append(f"{label}: XML autorizado indisponível")
                        continue
                    try:
                        xml_text = _read_authorized_xml(finv)
                    except HTTPException:
                        errors.append(f"{label}: arquivo XML não encontrado")
                        continue
                    if kind == "xml":
                        content = xml_text.encode("utf-8")
                    else:
                        from services.fiscal.sefaz.danfe import DanfeError, gerar_danfe
                        try:
                            content = await asyncio.to_thread(gerar_danfe, xml_text)
                        except DanfeError as e:
                            errors.append(f"{label}: falha ao gerar DANFE ({e})")
                            continue
                else:
                    acc = accounts_by_order.get(r["order_id"])
                    inv_id = r["ml_invoice_id"]
                    if not acc or not acc.access_token or not inv_id:
                        errors.append(f"{label}: pedido ML sem conta válida ou invoice_id")
                        continue
                    if kind == "xml":
                        path = f"/users/{acc.platform_user_id}/invoices/documents/xml/{inv_id}/authorized"
                    else:
                        path = f"/users/{acc.platform_user_id}/invoices/sites/MLB/documents/danfe/{inv_id}"
                    content, _ = await _ml.fetch_invoice_file(acc.access_token, path)

                folder = _re.sub(r"[^\w\- ]", "_", (r["cmig_name"] or f"CMIG_{r['cmig_id']}")).strip() or f"CMIG_{r['cmig_id']}"
                base = _re.sub(r"[^\w\-.]", "_", str(r["access_key"] or f"{r['source']}_{r['id']}"))
                name = f"{folder}/{base}.{ext}"
                n = 1
                while name in used_names:
                    name = f"{folder}/{base}_{n}.{ext}"
                    n += 1
                used_names.add(name)
                zf.writestr(name, content)
            except HTTPException as e:
                errors.append(f"{label}: {e.detail}")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{label}: {e}")

        notes = []
        if capped:
            notes.append(f"Exportação limitada a {MAX} NF-e. Refine os filtros para exportar o restante.")
        if errors:
            notes.append(f"{len(errors)} NF-e não puderam ser baixadas:\n" + "\n".join(errors))
        if notes:
            zf.writestr("_avisos.txt", "\n\n".join(notes))

    buf.seek(0)
    fname = f"notas_{kind}_{date.today().isoformat()}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Saídas unificadas (NF-e do módulo fiscal + Faturador ML) ──────────────────

# Status da order (Faturador ML) -> status normalizado usado na UI unificada
_ML_STATUS_MAP = {"in_process": "processing", "pending": "pending", "authorized": "authorized"}

# Rótulos de finalidade do módulo fiscal (Invoice.purpose)
_PURPOSE_LABELS = {
    "venda": "Venda",
    "devolucao": "Devolução",
    "remessa": "Simples Remessa",
    "retorno": "Retorno",
    "transferencia": "Transferência",
    "complementar": "Complementar",
    "ajuste": "Ajuste",
    "outros": "Outros",
}

# Rótulos de tipo de transação das NF-e do Faturador ML (transaction_type)
_ML_TYPE_LABELS = {
    "sale": "Venda",
    "devolution": "Devolução",
    "sale_return": "Retorno de Venda",
    "inbound": "Remessa",
    "inbound_return": "Retorno de Remessa",
    "symbolic_inbound": "Remessa Simbólica",
    "symbolic_inbound_return": "Retorno Simbólico",
    "removal": "Retirada",
    "input": "Alta de Estoque",
    "output": "Baixa de Estoque",
    "correction_letter": "Carta de Correção",
    "cte": "CT-e",
}


def _parse_access_key(key: str | None) -> dict:
    """Extrai número e série de uma chave de acesso de NF-e (44 dígitos).

    Layout: cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1).
    """
    k = "".join(c for c in (key or "") if c.isdigit())
    if len(k) != 44:
        return {}
    try:
        return {"serie": int(k[22:25]), "nfe_number": int(k[25:34])}
    except (ValueError, IndexError):
        return {}


def _ml_invoice_id_from_order(order: Order) -> str | None:
    """O invoice_id do Faturador ML é salvo em order.nfe_url como string de dígitos."""
    stored = str(order.nfe_url or "").strip()
    if stored.isdigit():
        return stored
    if "/danfe/" in stored:
        tail = stored.rstrip("/").split("/danfe/")[-1]
        return tail if tail.isdigit() else None
    return None


def _invoice_outbound_filters(stmt, cmig_ids, status, date_from, date_to, search):
    """Aplica os filtros comuns da fonte fiscal (Invoice direction='out') a um SELECT.
    Compartilhado entre a listagem paginada, o COUNT e o resumo por CMIG (Fase 3b)."""
    stmt = stmt.where(and_(Invoice.direction == "out", Invoice.cmig_id.in_(cmig_ids)))
    if status:
        stmt = stmt.where(Invoice.status == status)
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to:
        # Fim do dia (23:59:59) — senão nota emitida após 00:00 de date_to é excluída
        # (bind de `date` = meia-noite). Espelha a fonte ML, que já inclui o dia inteiro.
        stmt = stmt.where(
            Invoice.issue_date <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59)
        )
    if search:
        s = f"%{search.strip()}%"
        digits = "".join(c for c in search if c.isdigit())
        conds = [Invoice.access_key.like(s)]
        if digits:
            try:
                conds.append(Invoice.nfe_number == int(digits))
            except ValueError:
                pass
        stmt = stmt.where(or_(*conds))
    return stmt


async def _collect_outbound_rows(
    db: AsyncSession,
    accessible: list[int],
    cmig_id: int | None,
    source: str | None,
    status: str | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
    invoice_limit: int | None = None,
    sort_by: str | None = None,
    sort_dir: str = "desc",
) -> list[dict]:
    """Monta a lista unificada de NF-e de saída: Invoices do módulo fiscal +
    NF-e do Faturador ML (a partir de orders.nfe_*). Ordenada por emissão desc.

    Fase 3b — memória limitada: a fonte fiscal (Invoice), que cresce com a captura
    de TODAS as notas, é limitada em SQL ao `invoice_limit` (= page*page_size) já
    ordenada por emissão desc; a fonte ML só traz pedidos AINDA NÃO virados Invoice
    (`NOT EXISTS`), conjunto que encolhe a ~0 após o backfill. Assim o `[offset:...]`
    do chamador é correto sem materializar milhares de linhas."""
    cmig_ids = [cmig_id] if cmig_id is not None else accessible

    cmig_rows = (
        await db.execute(select(CMIG.id, CMIG.company_name).where(CMIG.id.in_(cmig_ids)))
    ).all()
    cmig_names = dict(cmig_rows)

    rows: list[dict] = []

    # ── Fonte 1: módulo fiscal (Invoice direction='out') ──────────────────────
    if source in (None, "", "all", "fiscal"):
        # A ordenação do LIMIT tem de alinhar com o sort pedido, senão o topN vem errado
        # para esse sort (proxy de coluna p/ cmig/tipo — a reordenação exata é feita em
        # Python sobre o conjunto já reduzido).
        _sort_col = {
            "numero": Invoice.nfe_number,
            "cmig": Invoice.cmig_id,
            "tipo": Invoice.purpose,
            "emissao": Invoice.issue_date,
        }.get(sort_by, Invoice.issue_date)
        _order = _sort_col.asc().nullslast() if sort_dir == "asc" else _sort_col.desc().nullslast()
        stmt = _invoice_outbound_filters(
            select(Invoice), cmig_ids, status, date_from, date_to, search
        ).order_by(_order)
        if invoice_limit:
            stmt = stmt.limit(invoice_limit)
        invs = (await db.execute(stmt)).scalars().all()

        person_ids = {i.person_id for i in invs if i.person_id}
        persons = {}
        if person_ids:
            ps = (await db.execute(select(Person).where(Person.id.in_(person_ids)))).scalars().all()
            persons = {p.id: p for p in ps}

        # Notas do Faturador ML (source='ml_faturador', Fase 3c) não guardam XML local:
        # o XML/DANFE baixa do ML pelo invoice_id do pedido vinculado. Batch-load dos
        # pedidos p/ preservar o botão de download (evita a regressão da Fase 3b).
        ml_fat_order_ids = {
            inv.order_id for inv in invs if inv.source == "ml_faturador" and inv.order_id
        }
        ml_fat_orders: dict[int, Order] = {}
        if ml_fat_order_ids:
            ords = (
                await db.execute(select(Order).where(Order.id.in_(ml_fat_order_ids)))
            ).scalars().all()
            ml_fat_orders = {o.id: o for o in ords}

        for inv in invs:
            p = persons.get(inv.person_id)
            # Download: NF-e própria (SEFAZ) tem XML local; ml_faturador baixa do ML.
            ml_inv_id = None
            xml_avail = bool(inv.xml_url) or (inv.status == "authorized" and bool(inv.xml_local_path))
            danfe_avail = bool(inv.danfe_url) or (inv.status == "authorized" and bool(inv.xml_local_path))
            if inv.source == "ml_faturador":
                _o = ml_fat_orders.get(inv.order_id)
                if _o is not None:
                    ml_inv_id = _ml_invoice_id_from_order(_o)
                    _ok = _o.nfe_status == "authorized" and bool(ml_inv_id)
                    xml_avail = _ok
                    danfe_avail = _ok
            rows.append(
                {
                    "source": "fiscal",
                    "id": inv.id,
                    "order_id": inv.order_id,
                    "platform_order_id": None,
                    "cmig_id": inv.cmig_id,
                    "cmig_name": cmig_names.get(inv.cmig_id),
                    "nfe_number": inv.nfe_number,
                    "serie": inv.serie,
                    "access_key": inv.access_key,
                    "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
                    "recipient": p.name if p else None,
                    "recipient_document": p.document if p else None,
                    "total": _f(inv.total_invoice),
                    "status": inv.status,
                    "nfe_type": inv.purpose,
                    "nfe_type_label": _PURPOSE_LABELS.get(inv.purpose, inv.purpose or "—"),
                    # Sinal de revisão (Fase 3c): saída ml_faturador sem pedido casado.
                    "needs_review": bool(
                        inv.source == "ml_faturador" and inv.direction == "out" and not inv.order_id
                    ),
                    "review_note": inv.fiscal_info if inv.source == "ml_faturador" else None,
                    "xml_url": inv.xml_url,
                    "danfe_url": inv.danfe_url,
                    "ml_invoice_id": ml_inv_id,
                    # NF-e própria (SEFAZ) guarda o XML local → baixa pelos endpoints
                    # /invoices/{id}/xml|danfe (não por URL). Disponível quando autorizada.
                    "xml_available": xml_avail,
                    "danfe_available": danfe_avail,
                    # PRÉVIA (marca d'água "SEM VALOR FISCAL") p/ nota não autorizada. Flag
                    # separado de danfe_available de propósito: o export ZIP contábil filtra
                    # por danfe_available e NÃO pode misturar prévias com DANFEs reais.
                    "danfe_preview": inv.status in ("draft", "finalized"),
                }
            )

    # ── Fonte 2: Faturador ML (orders.nfe_*) ──────────────────────────────────
    # Quando o pedido já teve as NF-e consultadas (modal de NF-e), a lista
    # completa — venda + notas de referência, como Retorno Simbólico de
    # pedidos Full — fica cacheada em orders.nfe_invoices_json. Caímos no
    # registro único derivado de orders.nfe_* só quando esse cache não existe.
    if source in (None, "", "all", "ml"):
        # NOT EXISTS: só pedidos cuja NF-e de venda AINDA NÃO virou Invoice (Fase 3b).
        # Depois do backfill (Fase 4), toda venda é Invoice → esta fonte esvazia e a
        # listagem passa a ser servida só pela fonte fiscal (paginada em SQL).
        stmt = select(Order).where(
            and_(
                Order.cmig_id.in_(cmig_ids),
                Order.platform == "mercadolivre",
                Order.nfe_status.isnot(None),
                ~exists().where(
                    and_(Invoice.access_key == Order.nfe_key, Invoice.direction == "out")
                ),
            )
        )
        if date_from:
            stmt = stmt.where(
                Order.created_at >= datetime(date_from.year, date_from.month, date_from.day)
            )
        if date_to:
            stmt = stmt.where(
                Order.created_at <= datetime(date_to.year, date_to.month, date_to.day, 23, 59, 59)
            )
        if search:
            s = f"%{search.strip()}%"
            stmt = stmt.where(or_(Order.nfe_key.like(s), Order.platform_order_id.like(s)))
        orders = (await db.execute(stmt)).scalars().all()

        for o in orders:
            issue_dt = o.paid_at or o.created_at
            order_issue = issue_dt.isoformat() if issue_dt else None

            cached = []
            if o.nfe_invoices_json:
                try:
                    parsed_json = _json.loads(o.nfe_invoices_json)
                    if isinstance(parsed_json, list):
                        cached = parsed_json
                except (ValueError, TypeError):
                    cached = []

            if cached:
                for inv in cached:
                    t_type = inv.get("transaction_type") or "sale"
                    rows.append(
                        {
                            "source": "ml",
                            "id": inv.get("id") or f"order-{o.id}",
                            "order_id": o.id,
                            "platform_order_id": o.platform_order_id,
                            "cmig_id": o.cmig_id,
                            "cmig_name": cmig_names.get(o.cmig_id),
                            "nfe_number": inv.get("invoice_number"),
                            "serie": inv.get("invoice_series"),
                            "access_key": inv.get("invoice_key"),
                            "issue_date": inv.get("issued_date") or order_issue,
                            "recipient": o.buyer_name,
                            "recipient_document": o.buyer_document,
                            "total": _f(inv.get("amount")),
                            "status": _ML_STATUS_MAP.get(
                                inv.get("status"), inv.get("status") or "authorized"
                            ),
                            "nfe_type": t_type,
                            "nfe_type_label": inv.get("transaction_type_label")
                            or _ML_TYPE_LABELS.get(t_type, t_type.replace("_", " ").title()),
                            "xml_url": None,
                            "danfe_url": None,
                            "ml_invoice_id": str(inv.get("id")) if inv.get("id") else None,
                            "xml_available": bool(inv.get("xml_location")),
                            "danfe_available": bool(inv.get("danfe_location")),
                        }
                    )
            else:
                # Fallback: pedido ainda não teve as NF-e consultadas — só a de venda
                parsed = _parse_access_key(o.nfe_key)
                ml_inv_id = _ml_invoice_id_from_order(o)
                authorized = o.nfe_status == "authorized"
                rows.append(
                    {
                        "source": "ml",
                        "id": ml_inv_id or f"order-{o.id}",
                        "order_id": o.id,
                        "platform_order_id": o.platform_order_id,
                        "cmig_id": o.cmig_id,
                        "cmig_name": cmig_names.get(o.cmig_id),
                        "nfe_number": parsed.get("nfe_number"),
                        "serie": parsed.get("serie"),
                        "access_key": o.nfe_key,
                        "issue_date": order_issue,
                        "recipient": o.buyer_name,
                        "recipient_document": o.buyer_document,
                        "total": _f(o.sale_amount),
                        "status": _ML_STATUS_MAP.get(o.nfe_status, o.nfe_status),
                        "nfe_type": "sale",
                        "nfe_type_label": "Venda",
                        "xml_url": None,
                        "danfe_url": None,
                        "ml_invoice_id": ml_inv_id,
                        "xml_available": authorized and bool(ml_inv_id),
                        "danfe_available": authorized and bool(ml_inv_id),
                    }
                )

    # Filtro de status aplicado de forma uniforme (após expandir o cache ML)
    if status:
        rows = [r for r in rows if r["status"] == status]

    # Paridade de contrato: as linhas ML não trazem os campos de revisão (só a fonte
    # fiscal). Garante shape uniforme para o frontend (default falso/None).
    for r in rows:
        r.setdefault("needs_review", False)
        r.setdefault("review_note", None)

    rows.sort(key=lambda r: r["issue_date"] or "", reverse=True)
    return rows


@router.get("/outbound")
async def list_outbound_invoices(
    cmig_id: int | None = Query(None),
    source: str | None = Query(None, regex="^(all|fiscal|ml)$"),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    sort_by: str | None = Query(None),  # cmig | numero | tipo | emissao
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista unificada de NF-e de saída por CMIG: módulo fiscal + Faturador ML."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "by_cmig": []}
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    # Fase 3b — memória limitada: pede à fonte fiscal só o topN (offset+page_size) já
    # ordenado em SQL; a fonte ML (uncovered) vem completa (encolhe pós-backfill). O
    # slice [start:start+page_size] sobre o merge ordenado é correto porque o topN
    # global cabe na união (topN fiscal + todas as ML uncovered).
    start = (page - 1) * page_size
    invoice_limit = start + page_size
    rows = await _collect_outbound_rows(
        db, accessible, cmig_id, source, status, date_from, date_to, search,
        invoice_limit=invoice_limit, sort_by=sort_by, sort_dir=sort_dir,
    )

    # Dedup por chave de acesso: a NF-e pode vir como Invoice (source=fiscal — inclui as
    # notas do Faturador ML capturadas na Fase 3c) e/ou do cache de pedido (source=ml).
    # A linha 'fiscal' tem prioridade MAS herda o download da linha 'ml' quando não tem
    # arquivo próprio (nota ml_faturador não guarda XML local → o botão viria do ML).
    def _merge_download(winner: dict, loser: dict) -> dict:
        if winner.get("source") == "fiscal" and not winner.get("xml_available") and not winner.get("danfe_available"):
            for k in ("xml_available", "danfe_available", "ml_invoice_id"):
                if loser.get(k):
                    winner[k] = loser[k]
        return winner

    seen: dict[str, int] = {}
    deduped: list[dict] = []
    for r in rows:
        ak = (r.get("access_key") or "").strip()
        if ak and len(ak) == 44:
            if ak not in seen:
                seen[ak] = len(deduped)
                deduped.append(r)
            else:
                cur = deduped[seen[ak]]
                if r.get("source") == "fiscal" and cur.get("source") != "fiscal":
                    deduped[seen[ak]] = _merge_download(r, cur)
                elif cur.get("source") == "fiscal" and r.get("source") != "fiscal":
                    deduped[seen[ak]] = _merge_download(cur, r)
        else:
            deduped.append(r)
    rows = deduped

    def _num(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    # As chaves de ordenação Python ESPELHAM a coluna-proxy do LIMIT SQL (cmig→cmig_id,
    # tipo→nfe_type) — senão o topN truncado no SQL diverge do sort final e linhas somem
    # da página. (Agrupa por CMIG/tipo de forma consistente; não é alfabético pelo rótulo.)
    _SORT_KEYS = {
        "cmig": lambda r: _num(r.get("cmig_id")),
        "numero": lambda r: _num(r.get("nfe_number")),
        "tipo": lambda r: (r.get("nfe_type") or ""),
        "emissao": lambda r: str(r.get("issue_date") or ""),
    }
    keyfn = _SORT_KEYS.get(sort_by) or (lambda r: str(r.get("issue_date") or ""))
    rows.sort(key=keyfn, reverse=(sort_dir == "desc"))

    # ── Total + resumo por CMIG via SQL (não materializa a tabela inteira) ──────
    cmig_ids = [cmig_id] if cmig_id is not None else accessible
    # Fonte fiscal: COUNT + SUM(total) por CMIG.
    inv_count = 0
    by_cmig: dict[int, dict] = {}
    cmig_names = dict(
        (await db.execute(select(CMIG.id, CMIG.company_name).where(CMIG.id.in_(cmig_ids)))).all()
    )
    if source in (None, "", "all", "fiscal"):
        agg = (
            await db.execute(
                _invoice_outbound_filters(
                    select(Invoice.cmig_id, func.count(), func.coalesce(func.sum(Invoice.total_invoice), 0)),
                    cmig_ids, status, date_from, date_to, search,
                ).group_by(Invoice.cmig_id)
            )
        ).all()
        for cid, cnt, tot in agg:
            inv_count += int(cnt or 0)
            by_cmig[cid] = {"cmig_id": cid, "cmig_name": cmig_names.get(cid),
                            "count": int(cnt or 0), "total": float(tot or 0)}
    # Fonte ML (uncovered) já está materializada e completa em `rows` — soma de lá,
    # evitando recontar o que virou Invoice.
    ml_count = 0
    for r in rows:
        if r.get("source") == "ml":
            ml_count += 1
            b = by_cmig.setdefault(
                r["cmig_id"],
                {"cmig_id": r["cmig_id"], "cmig_name": r.get("cmig_name"), "count": 0, "total": 0.0},
            )
            b["count"] += 1
            b["total"] += r.get("total") or 0.0

    total = inv_count + ml_count
    return {
        "items": rows[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "by_cmig": sorted(by_cmig.values(), key=lambda x: (x.get("cmig_name") or "")),
    }


@router.get("/outbound/export")
async def export_outbound_invoices(
    kind: str = Query(..., regex="^(xml|danfe)$"),
    cmig_id: int | None = Query(None),
    source: str | None = Query(None, regex="^(all|fiscal|ml)$"),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exporta um .zip com os XMLs (ou DANFEs) de todas as NF-e de saída filtradas."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        raise HTTPException(status_code=404, detail="Nenhuma CMIG acessível")
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    MAX = 400
    # Limite generoso na fonte fiscal (memória) — mais recentes primeiro; o corte final
    # é MAX após filtrar por disponibilidade de documento.
    rows = await _collect_outbound_rows(
        db, accessible, cmig_id, source, status, date_from, date_to, search,
        invoice_limit=MAX * 5,
    )
    avail_key = "xml_available" if kind == "xml" else "danfe_available"
    rows = [r for r in rows if r.get(avail_key)]
    capped = len(rows) > MAX
    rows = rows[:MAX]
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma NF-e com documento disponível no filtro atual",
        )

    # Tokens ML necessários para baixar XML/DANFE do Faturador — inclui as notas
    # ml_faturador (source='fiscal' mas com invoice_id do pedido vinculado, Fase 3c).
    ml_order_ids = [r["order_id"] for r in rows if r.get("ml_invoice_id") and r.get("order_id")]
    accounts_by_order: dict[int, MarketplaceAccount] = {}
    if ml_order_ids:
        o_rows = (
            await db.execute(select(Order.id, Order.account_id).where(Order.id.in_(ml_order_ids)))
        ).all()
        acc_ids = {aid for _, aid in o_rows if aid}
        accs = {}
        if acc_ids:
            accs = {
                a.id: a
                for a in (
                    await db.execute(
                        select(MarketplaceAccount).where(MarketplaceAccount.id.in_(acc_ids))
                    )
                )
                .scalars()
                .all()
            }
        accounts_by_order = {oid: accs.get(aid) for oid, aid in o_rows}

    ext = "xml" if kind == "xml" else "pdf"
    errors: list[str] = []
    used_names: set[str] = set()
    buf = _io.BytesIO()

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True):
        with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            for r in rows:
                label = f"NFe {r['nfe_number'] or r['access_key'] or r['id']}"
                try:
                    if r["source"] == "fiscal" and not r.get("ml_invoice_id"):
                        # NF-e própria (SEFAZ): XML autorizado é local; DANFE é gerado.
                        finv = (
                            await db.execute(select(Invoice).where(Invoice.id == r["id"]))
                        ).scalar_one_or_none()
                        if not finv or not finv.xml_local_path:
                            errors.append(f"{label}: XML autorizado indisponível")
                            continue
                        try:
                            xml_text = _read_authorized_xml(finv)
                        except HTTPException:
                            errors.append(f"{label}: arquivo XML não encontrado")
                            continue
                        if kind == "xml":
                            content = xml_text.encode("utf-8")
                        else:
                            from services.fiscal.sefaz.danfe import DanfeError, gerar_danfe
                            try:
                                content = await asyncio.to_thread(gerar_danfe, xml_text)
                            except DanfeError as e:
                                errors.append(f"{label}: falha ao gerar DANFE ({e})")
                                continue
                    else:  # ml
                        acc = accounts_by_order.get(r["order_id"])
                        inv_id = r["ml_invoice_id"]
                        if not acc or not acc.access_token or not inv_id:
                            errors.append(f"{label}: pedido ML sem conta válida ou invoice_id")
                            continue
                        if kind == "xml":
                            path = (
                                f"/users/{acc.platform_user_id}/invoices/documents"
                                f"/xml/{inv_id}/authorized"
                            )
                        else:
                            path = (
                                f"/users/{acc.platform_user_id}/invoices/sites/MLB"
                                f"/documents/danfe/{inv_id}"
                            )
                        content, _ = await _ml.fetch_invoice_file(acc.access_token, path)

                    folder = (
                        _re.sub(
                            r"[^\w\- ]", "_", (r["cmig_name"] or f"CMIG_{r['cmig_id']}")
                        ).strip()
                        or f"CMIG_{r['cmig_id']}"
                    )
                    base = r["access_key"] or f"{r['source']}_{r['id']}"
                    name = f"{folder}/{base}.{ext}"
                    n = 1
                    while name in used_names:
                        name = f"{folder}/{base}_{n}.{ext}"
                        n += 1
                    used_names.add(name)
                    zf.writestr(name, content)
                except HTTPException as e:
                    errors.append(f"{label}: {e.detail}")
                except Exception as e:
                    errors.append(f"{label}: {e}")

            notes = []
            if capped:
                notes.append(
                    f"Exportação limitada a {MAX} NF-e. Refine os filtros (CMIG, "
                    f"período) para exportar o restante."
                )
            if errors:
                notes.append(f"{len(errors)} NF-e não puderam ser baixadas:\n" + "\n".join(errors))
            if notes:
                zf.writestr("_avisos.txt", "\n\n".join(notes))

    buf.seek(0)
    fname = f"nfe_saidas_{kind}_{date.today().isoformat()}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/outbound/sync-ml")
async def sync_ml_outbound_invoices(
    cmig_id: int | None = Query(None),
    limit: int = Query(25, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Popula o cache de NF-e do Faturador ML (orders.nfe_invoices_json) para os
    pedidos que ainda não foram consultados — assim a tela Fiscal>Saídas passa a
    listar também as notas de referência (ex.: Retorno Simbólico de pedidos Full).

    Processa no máximo `limit` pedidos por chamada e retorna `remaining`; o
    frontend repete a chamada até zerar. Reaproveita o mesmo endpoint do botão
    de NF-e da tela de Pedidos (fetch_and_cache_order_invoices)."""
    from routers.orders import fetch_and_cache_order_invoices

    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"processed": 0, "remaining": 0, "errors": []}
    cmig_ids = [cmig_id] if cmig_id is not None else accessible
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    base_filter = and_(
        Order.cmig_id.in_(cmig_ids),
        Order.platform == "mercadolivre",
        Order.nfe_status.isnot(None),
        Order.nfe_invoices_json.is_(None),
    )

    remaining = (
        await db.execute(select(func.count()).select_from(Order).where(base_filter))
    ).scalar() or 0
    if remaining == 0:
        return {"processed": 0, "remaining": 0, "errors": []}

    orders = (
        (
            await db.execute(
                select(Order).where(base_filter).order_by(Order.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    # Contas em batch
    acc_ids = {o.account_id for o in orders if o.account_id}
    accounts = {}
    if acc_ids:
        accounts = {
            a.id: a
            for a in (
                await db.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id.in_(acc_ids))
                )
            )
            .scalars()
            .all()
        }

    processed = 0
    errors: list[str] = []
    for o in orders:
        acc = accounts.get(o.account_id)
        if not acc or not acc.access_token:
            # Sem conta válida — marca como vazio para não reprocessar infinitamente
            o.nfe_invoices_json = "[]"
            await db.commit()
            errors.append(f"Pedido {o.platform_order_id or o.id}: conta ML sem token")
            continue
        try:
            await fetch_and_cache_order_invoices(db, o, acc)
            if o.nfe_invoices_json is None:
                o.nfe_invoices_json = "[]"  # nada retornado — evita reprocessar
                await db.commit()
            processed += 1
        except Exception as e:
            errors.append(f"Pedido {o.platform_order_id or o.id}: {e}")

    return {"processed": processed, "remaining": max(0, remaining - processed), "errors": errors}


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = (
        await db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.items).selectinload(InvoiceItem.cmig_product),
                selectinload(Invoice.events),
            )
            .where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    person = None
    if inv.person_id:
        person = (
            await db.execute(select(Person).where(Person.id == inv.person_id))
        ).scalar_one_or_none()

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
    valid_purposes = (
        "venda",
        "devolucao",
        "remessa",
        "retorno",
        "transferencia",
        "complementar",
        "ajuste",
        "outros",
    )
    if purpose not in valid_purposes:
        raise HTTPException(status_code=422, detail=f"purpose deve ser um de: {valid_purposes}")

    person_id = body.get("person_id")
    if person_id:
        p = (
            await db.execute(
                select(Person).where(and_(Person.id == person_id, Person.cmig_id == cmig_id))
            )
        ).scalar_one_or_none()
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
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe uma NF-e com essa série e número para esta CMIG. Verifique os dados e tente novamente.",
        )
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
        raise HTTPException(
            status_code=400, detail=f"Não é possível editar NFe com status '{inv.status}'"
        )

    editable = {
        "purpose",
        "natureza_operacao",
        "person_id",
        "freight_modality",
        "carrier_person_id",
        "payment_method",
        "payment_terms_json",
        "additional_info",
        "fiscal_info",
        "exit_date",
        "issue_date",
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
    """Exclui NFe.

    Permitido em:
    - `draft` — nunca tocou em estoque, exclui direto.
    - `finalized` — finalizada SEM SEFAZ. Captura produtos afetados antes,
      exclui a NFe, e recalcula estoque dos produtos (o evento "vai embora"
      do replay automaticamente — `_fetch_*_events` para de retornar).

    BLOQUEADO em:
    - `authorized` — foi transmitida à SEFAZ; precisa CANCELAR (botão dedicado).
    - Demais status (queued, processing, rejected, cancelled).
    """
    from services.fiscal.stock_calculator import (
        affected_products_from_invoice,
        recompute_cmig_product_stock,
        recompute_pg_product_stock,
    )

    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    if inv.status not in ("draft", "finalized"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível excluir NFe com status '{inv.status}'. "
                "NFes transmitidas à SEFAZ precisam ser canceladas, não excluídas."
            ),
        )

    # Captura produtos afetados ANTES de deletar a NFe — após o delete, o
    # replay não enxerga mais esses eventos e o recompute vai zerar/reverter.
    cmig_ids: set[int] = set()
    pg_ids: set[int] = set()
    needs_recompute = inv.status == "finalized" and inv.direction == "in"
    if needs_recompute:
        cmig_ids, pg_ids = await affected_products_from_invoice(inv, db)

    db.delete(inv)
    await db.flush()

    if needs_recompute:
        for cp_id in cmig_ids:
            await recompute_cmig_product_stock(cp_id, db)
        for pg_id in pg_ids:
            await recompute_pg_product_stock(pg_id, db)

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
        raise HTTPException(
            status_code=400, detail=f"NFe em status '{inv.status}' não pode ser editada"
        )
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
        catalog_product_id=body.get("catalog_product_id"),
        sku=body.get("sku"),
        source_type=body.get("source_type"),
        cfop=body.get("cfop"),
        ncm=_norm_ncm(body.get("ncm")),
        cest=_norm_cest(body.get("cest")),
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
        "quantity",
        "unit_value",
        "total_value",
        "discount",
        "freight_value",
        "insurance_value",
        "other_value",
        "icms_base",
        "icms_aliquota",
        "icms_value",
        "icms_st_base",
        "icms_st_aliquota",
        "icms_st_value",
        "ipi_aliquota",
        "ipi_value",
        "pis_aliquota",
        "pis_value",
        "cofins_aliquota",
        "cofins_value",
    }
    str_fields = {
        "cfop",
        "ncm",
        "cest",
        "description",
        "ean",
        "unit",
        "sku",
        "source_type",
        "icms_cst",
        "icms_csosn",
        "ipi_cst",
        "pis_cst",
        "cofins_cst",
        "additional_info",
    }
    int_fields = {"origin", "cmig_product_id", "catalog_product_id"}

    for k, v in body.items():
        if k in decimal_fields and v is not None:
            setattr(item, k, Decimal(str(v)))
        elif k in str_fields:
            if k == "ncm":
                v = _norm_ncm(v)
            elif k == "cest":
                v = _norm_cest(v)
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
        person = (
            await db.execute(select(Person).where(Person.id == inv.person_id))
        ).scalar_one_or_none()

    # Sugerir CFOP se ainda não tiver
    suggested_cfop = suggest_cfop(
        purpose=inv.purpose,
        uf_emit=cmig.state,
        uf_dest=person.state if person else cmig.state,
    )

    # Detectar se destino é consumidor final não-contribuinte (DIFAL obrigatório)
    is_difal_applicable = (
        person is not None
        and (person.person_type == "PF" or getattr(person, "ie_isento", False))
        and cmig.state
        and person.state
        and cmig.state.upper() != (person.state or "").upper()
    )

    for item in inv.items or []:
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
            tax_regime_mode=cfg.tax_regime_mode or "legacy",
        )
        for k, v in result.items():
            setattr(item, k, v)

        # DIFAL — interestadual para não-contribuinte
        if is_difal_applicable and item.cfop and item.cfop.startswith("6"):
            from decimal import Decimal as D
            aliq_orig = await get_icms_rate(db, cmig.state, cmig.state)
            aliq_dest = await get_icms_rate(db, person.state, person.state)
            difal_data = compute_difal(
                base_value=item.total_value or D("0"),
                aliquota_orig=aliq_orig,
                aliquota_dest=aliq_dest,
                fcp_aliquota=D("2"),  # FCP padrão 2% — ajustável por UF futuramente
            )
            for k, v in difal_data.items():
                setattr(item, k, v)

    _recompute_totals(inv)
    await db.commit()
    await db.refresh(inv, attribute_names=["items"])
    return _serialize(inv, with_items=True)


def _validate_ready_to_transmit(inv: Invoice, cfg: CMIGFiscalConfig, person: Person | None):
    if inv.status != "draft":
        raise HTTPException(
            status_code=400, detail=f"NFe em status '{inv.status}' não pode ser transmitida"
        )
    if not (cfg.cert_path and cfg.cert_pass_encrypted):
        raise HTTPException(
            status_code=400,
            detail="Certificado A1 não configurado para esta CMIG (envie o .pfx em Configuração Fiscal)",
        )
    if not cfg.manual_nfe_serie:
        raise HTTPException(
            status_code=400, detail="Configure a Série da NF-e manual (SEFAZ) na Configuração Fiscal"
        )
    if not person:
        raise HTTPException(status_code=400, detail="Selecione o destinatário antes de transmitir")
    if not inv.items:
        raise HTTPException(status_code=400, detail="NFe sem itens")
    for it in inv.items:
        if not it.cfop:
            raise HTTPException(
                status_code=400,
                detail=f"Item {it.item_number} sem CFOP — clique em 'Calcular Impostos'",
            )
        if not it.ncm:
            raise HTTPException(status_code=400, detail=f"Item {it.item_number} sem NCM")


@router.post("/{invoice_id}/transmit")
async def transmit_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transmite a NFe diretamente à SEFAZ (mTLS + XMLDSig), via série manual configurável."""
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)
    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()
    person = None
    if inv.person_id:
        person = (
            await db.execute(select(Person).where(Person.id == inv.person_id))
        ).scalar_one_or_none()

    _validate_ready_to_transmit(inv, cfg, person)

    try:
        await sefaz_service.emitir(db, inv, cmig, cfg, person, list(inv.items))
    except sefaz_service.SefazServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _SefazNetError as e:
        # Rede/SEFAZ fora — a nota fica em 'processing'; o usuário recupera com
        # "Atualizar status" (consulta N-6 pela chave, sem reemitir).
        raise HTTPException(
            status_code=502,
            detail=f"SEFAZ indisponível: {e}. Use 'Atualizar status' para retomar.",
        )
    except _SefazFiscalError as e:
        raise HTTPException(status_code=422, detail=f"Falha fiscal ao montar a NF-e: {e}")

    # Autorizada → baixa o estoque (a saída deixou o galpão). Sem isto a nota fica invisível
    # ao recálculo de estoque (o replay filtra stock_updated==True). Falha aqui NÃO derruba a
    # transmissão (a nota já está autorizada) — apenas sinaliza pendência recuperável.
    stock_ok = await _apply_stock_on_authorization(inv, db)
    await db.refresh(inv, attribute_names=["items"])
    resp = _serialize(inv, with_items=True)
    if not stock_ok:
        resp["stock_pending"] = True
    return resp


async def _apply_stock_movement(inv: Invoice, db: AsyncSession, *, full_cycle: bool = False) -> dict:
    """Recalcula estoque dos produtos afetados por esta NFe.

    No modelo canônico (event-sourced), `stock_quantity` é cache do resultado
    do replay dos eventos. Esta função:
    1) Identifica produtos CMIG/PG tocados pelos itens.
    2) Chama `recompute_*_stock` pra cada um — recalcula a partir do zero.

    `stock_updated=True` é apenas marker histórico de que essa NFe já passou
    por esse processamento (pra evitar reprocessar em loops).

    `full_cycle=True` (remessa/retorno de/para o depósito do ML): MOVE estoque mesmo sendo
    'simbólico' — o par remessa(galpão−)⇄retorno(galpão+) transfere estoque entre Galpão e FULL.
    """
    from services.fiscal.stock_calculator import recompute_after_invoice_change

    # Guard central: NF-e simbólica não movimenta estoque (não seta stock_updated, logo fica inerte
    # ao recompute event-sourced). Protege TODOS os call-sites — EXCETO o ciclo FULL (full_cycle).
    if _is_simbolica(inv.natureza_operacao) and not full_cycle:
        return {"cmig_ids": set(), "pg_ids": set(), "simbolica": True}

    if inv.stock_updated:
        return {
            "cmig_recomputed": 0,
            "pg_recomputed": 0,
            "already_updated": True,
        }

    # Seta True e flush ANTES do recompute: _fetch_direct_pg_events e
    # _fetch_nfe_events_for_cmig_product filtram stock_updated==True,
    # então a própria NFe só entra nos eventos se a flag já estiver ativa.
    inv.stock_updated = True
    await db.flush()

    result = await recompute_after_invoice_change(inv, db)
    return {**result, "already_updated": False}


async def _post_commit_full_and_push(inv: Invoice, db: AsyncSession, stock: dict) -> None:
    """Pós-commit de uma nota que moveu estoque (finalize OU transmissão/consulta SEFAZ):
    aplica o estoque FULL (se a contraparte for CNPJ FULL) e agenda o push de sync p/ os
    marketplaces. Best-effort — nunca quebra a emissão. Relê o status no banco (guard anti-`/reopen`
    do finalize; inócuo na transmissão, onde `/reopen` é bloqueado em 'authorized')."""
    if inv.person_id:
        try:
            from services.full_stock_service import (
                apply_nfe_entrada_from_full,
                apply_nfe_saida_to_full,
                is_full_cnpj,
            )
            _st = (
                await db.execute(select(Invoice.status).where(Invoice.id == inv.id))
            ).scalar_one_or_none()
            _person = (
                await db.execute(select(Person).where(Person.id == inv.person_id))
            ).scalar_one_or_none()
            if (
                _st in ("finalized", "authorized")
                and _person and _person.document
                and not _is_simbolica(inv.natureza_operacao)
            ):
                _full_cnpj = await is_full_cnpj(db, _person.document, inv.cmig_id)
                if _full_cnpj:
                    if inv.direction == "out":
                        await apply_nfe_saida_to_full(db, inv, _full_cnpj.marketplace_account_id)
                    elif inv.direction == "in":
                        await apply_nfe_entrada_from_full(db, inv, _full_cnpj.marketplace_account_id)
                    await db.commit()
        except Exception:
            logger.warning("[estoque] falha ao aplicar FULL da NF-e %s", inv.id, exc_info=True)
    try:
        from services.stock_sync_service import schedule_push
        schedule_push(stock.get("cmig_ids", set()), stock.get("pg_ids", set()))
    except Exception:
        pass


async def _apply_stock_on_authorization(inv: Invoice, db: AsyncSession) -> bool:
    """Baixa de estoque quando uma NF-e é AUTORIZADA pela SEFAZ própria — na transmissão
    (`transmit_invoice`) OU na recuperação N-6 via consulta (`refresh_status`). Sem isto a saída
    autorizada nunca sai do estoque e fica invisível ao recálculo (o replay filtra
    `stock_updated==True`). Espelha o finalize: `_apply_stock_movement` (idempotente por
    `stock_updated`, pula simbólica) + FULL + push. Idempotente — seguro chamar nos dois caminhos.

    Retorna True se baixou (ou já estava baixado); False se falhou. **Nunca propaga**: a
    autorização SEFAZ já está gravada (commit dentro de `emitir`) e não pode virar HTTP 500 por
    um erro de estoque pós-fato — a baixa é recuperável clicando "Recalcular Estoque" ou via N-6.
    """
    if inv.status != "authorized" or inv.stock_updated:
        return True
    try:
        stock = await _apply_stock_movement(inv, db)
        await db.commit()
        await _post_commit_full_and_push(inv, db, stock)
        return True
    except Exception:
        logger.warning(
            "[estoque] falha ao baixar estoque da NF-e %s pós-autorização "
            "(recuperável via Recalcular Estoque)", inv.id, exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass
        return False


@router.post("/{invoice_id}/finalize-no-sefaz")
async def finalize_invoice_no_sefaz(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Finaliza a NFe SEM transmitir à SEFAZ.

    A NFe entra no status 'finalized' e:
    - É contabilizada nos totalizadores da tela Fiscal > Saídas (por Natureza da Operação);
    - Movimenta o estoque dos CMIGProducts vinculados (decrementa em saídas, incrementa em entradas).

    Útil para NFes auxiliares (devolução manual, ajustes, controles internos) onde o cliente
    não exige a transmissão à SEFAZ via Focus NFe, mas o estoque precisa refletir a operação.
    """
    inv = await _get_invoice_for_edit(invoice_id, current_user, db)

    if not inv.items:
        raise HTTPException(
            status_code=400, detail="NFe sem itens — adicione itens antes de finalizar"
        )
    if not inv.person_id:
        recipient = "destinatário" if inv.direction == "out" else "fornecedor"
        raise HTTPException(status_code=400, detail=f"Selecione o {recipient} antes de finalizar")

    if not inv.issue_date:
        inv.issue_date = datetime.utcnow()

    stock = await _apply_stock_movement(inv, db)

    inv.status = "finalized"
    inv.focus_status = None
    inv.focus_message = "Finalizada sem transmissão à SEFAZ"

    db.add(
        InvoiceEvent(
            invoice_id=inv.id,
            event_type="finalize_no_sefaz",
            reason=(
                f"Finalizada sem transmissão à SEFAZ "
                f"(estoque: {stock.get('matched', 0)} OK, {stock.get('unmatched', 0)} sem vínculo)"
            ),
            created_by_user_id=current_user.id,
        )
    )

    _recompute_totals(inv)
    await db.commit()
    await _post_commit_full_and_push(inv, db, stock)
    await db.refresh(inv, attribute_names=["items"])
    return {
        **_serialize(inv, with_items=True),
        "stock_movement": stock,
    }


@router.post("/{invoice_id}/reopen")
async def reopen_invoice(
    invoice_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reabre a nota para edição (volta a `draft`).

    Permitido em:
    - `finalized` (sem SEFAZ) — desfaz a movimentação de estoque: `stock_updated=False` volta a
      nota para fora do replay (`stock_history` só conta authorized/finalized com o flag) e o
      recompute recalcula os produtos afetados do zero.
    - `rejected` (SEFAZ recusou) — nunca movimentou estoque; limpa os campos da tentativa
      (chave/cStat/xMotivo) e libera a edição. A retransmissão reserva um número NOVO; o
      número rejeitado pode ser inutilizado depois (POST /invoices/inutilize).

    BLOQUEADO em `authorized` (só cancelamento/CC-e, por lei), e quando a nota:
    - está vinculada a um pedido (editar divergiria dos itens do pedido);
    - já creditou estoque FULL (subsistema incremental — reabrir duplicaria na re-finalização).
    """
    from models.stock_movement import StockMovement
    from services.fiscal.stock_calculator import recompute_after_invoice_change

    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    if inv.status not in ("finalized", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível reabrir nota com status '{inv.status}'. "
                "Nota autorizada na SEFAZ só pode ser cancelada ou corrigida por CC-e."
            ),
        )
    if inv.order_id:
        raise HTTPException(
            status_code=400,
            detail="Esta nota está vinculada a um pedido — reabri-la divergiria dos itens do "
                   "pedido. Cancele/exclua e gere outra a partir do pedido.",
        )
    # Movimento FULL é incremental (não event-sourced): reabrir e re-finalizar duplicaria o
    # crédito no FULL, e as quantidades editadas nunca chegariam lá (dedup por invoice_id).
    full_mov = (
        await db.execute(
            select(StockMovement.id).where(StockMovement.invoice_id == inv.id).limit(1)
        )
    ).first()
    if full_mov:
        # O movimento FULL é incremental (não event-sourced): não há como desfazê-lo
        # automaticamente, nem excluindo a nota (a FK stock_movements.invoice_id impede).
        raise HTTPException(
            status_code=400,
            detail="Esta nota já creditou estoque FULL — não pode ser reaberta. "
                   "Faça o acerto do FULL pelo módulo de estoque antes de mexer nesta nota.",
        )

    era = inv.status
    await audit_service.record(
        db, current_user, "invoice.reopen", "invoice", inv.id,
        details={"de_status": era, "serie": inv.serie, "nfe_number": inv.nfe_number,
                 "access_key": inv.access_key, "direction": inv.direction},
        request=request,
    )

    inv.status = "draft"
    inv.focus_status = None
    inv.focus_message = None
    if era == "rejected":
        # A tentativa morta não pode "assombrar" o rascunho: a retransmissão reserva número
        # NOVO, e manter o número rejeitado faria a prévia (e um eventual finalize) exibirem
        # uma numeração que será inutilizada. Mesma limpeza da recuperação de 217 (fonte única).
        sefaz_service.reset_invoice_to_draft(inv)

    stock: dict = {}
    if era == "finalized":
        # Fora do replay ANTES do recompute (stock_history filtra stock_updated + status).
        inv.stock_updated = False
        await db.flush()
        stock = await recompute_after_invoice_change(inv, db)

    db.add(
        InvoiceEvent(
            invoice_id=inv.id,
            event_type="reopened",
            reason=f"Reaberta para edição (era '{era}')",
            created_by_user_id=current_user.id,
        )
    )
    await db.commit()

    if stock:
        try:
            from services.stock_sync_service import schedule_push
            schedule_push(stock.get("cmig_ids", set()), stock.get("pg_ids", set()))
        except Exception:
            pass

    await db.refresh(inv, attribute_names=["items"])
    return _serialize(inv, with_items=True)


@router.post("/{invoice_id}/reapply-stock")
async def reapply_stock_for_pg_items(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("fiscal_entradas")),
):
    """Recalcula estoque de todos os produtos afetados por esta NFe a partir dos eventos.

    Operação idempotente — pode ser chamada N vezes sem acumular. Usa o mesmo
    replay determinístico do fluxo normal de finalização.
    """
    from services.fiscal.stock_calculator import recompute_after_invoice_change

    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status not in ("finalized", "authorized"):
        raise HTTPException(
            status_code=400,
            detail="Apenas NFes finalizadas ou autorizadas podem ter o estoque reaplicado",
        )

    result = await recompute_after_invoice_change(inv, db)

    db.add(
        InvoiceEvent(
            invoice_id=inv.id,
            event_type="stock_reapplied",
            reason=f"Recalculo: cmig={result['cmig_recomputed']}, pg={result['pg_recomputed']}",
            created_by_user_id=current_user.id,
        )
    )
    await db.commit()
    try:
        from services.stock_sync_service import schedule_push
        schedule_push(result.get("cmig_ids", set()), result.get("pg_ids", set()))
    except Exception:
        pass
    return {k: v for k, v in result.items() if k not in ("cmig_ids", "pg_ids")}


@router.post("/{invoice_id}/refresh-status")
async def refresh_status(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reconsulta o status da NFe na SEFAZ pela chave (regra N-6) — recupera notas em 'processing'."""
    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if not inv.access_key:
        raise HTTPException(status_code=400, detail="NFe ainda não foi transmitida")
    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()

    try:
        result = await sefaz_service.consultar(db, inv, cmig, cfg)
    except sefaz_service.SefazServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _SefazNetError as e:
        raise HTTPException(status_code=502, detail=f"SEFAZ indisponível: {e}")

    # Se a consulta N-6 confirmou a autorização (nota que caiu em 'processing' na transmissão),
    # baixa o estoque agora — mesmo efeito da transmissão bem-sucedida.
    stock_ok = await _apply_stock_on_authorization(inv, db)

    return {
        "status": inv.status,
        "cstat": result.get("cstat"),
        "motivo": result.get("motivo"),
        "protocolo": result.get("protocolo"),
        "stock_pending": not stock_ok,
    }


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancela NFe autorizada (até 24h após autorização)."""
    inv = (
        await db.execute(
            select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status != "authorized":
        raise HTTPException(status_code=400, detail="Apenas NFes autorizadas podem ser canceladas")
    if not inv.access_key:
        raise HTTPException(status_code=400, detail="NFe sem chave de acesso")

    reason = (body.get("reason") or "").strip()
    if len(reason) < 15 or len(reason) > 255:
        raise HTTPException(
            status_code=422, detail="Justificativa deve ter entre 15 e 255 caracteres"
        )

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()
    try:
        result = await sefaz_service.cancelar(db, inv, cmig, cfg, reason)
    except sefaz_service.SefazServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _SefazNetError as e:
        raise HTTPException(status_code=502, detail=f"SEFAZ indisponível: {e}")

    if not result.get("cancelada"):
        raise HTTPException(
            status_code=422,
            detail=f"SEFAZ não cancelou (cStat {result.get('cstat')}): {result.get('motivo')}",
        )
    db.add(
        InvoiceEvent(
            invoice_id=inv.id,
            event_type="cancellation",
            reason=reason,
            sefaz_protocol=inv.cancel_protocol,
            sefaz_status_code=str(result.get("cstat") or ""),
            sefaz_message=result.get("motivo"),
            created_by_user_id=current_user.id,
        )
    )
    await db.commit()
    # Estorno de estoque: a nota cancelada sai do replay (filtro `status in (authorized,finalized)`),
    # então o saldo volta sozinho no próximo cálculo — mas o cache `stock_quantity` só atualiza
    # recomputando os produtos afetados agora. Só recomputa se a nota chegou a baixar estoque.
    if inv.stock_updated:
        try:
            from services.fiscal.stock_calculator import recompute_after_invoice_change
            _res = await recompute_after_invoice_change(inv, db)
            await db.commit()
            from services.stock_sync_service import schedule_push
            schedule_push(_res.get("cmig_ids", set()), _res.get("pg_ids", set()))
        except Exception:
            logger.warning(
                "[estoque] falha ao estornar cache da NF-e %s pós-cancelamento "
                "(o job diário reconcilia)", inv.id, exc_info=True,
            )
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
    if not inv.access_key:
        raise HTTPException(status_code=400, detail="NFe sem chave de acesso")

    text = (body.get("text") or "").strip()
    if len(text) < 15 or len(text) > 1000:
        raise HTTPException(status_code=422, detail="Texto deve ter entre 15 e 1000 caracteres")

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()
    # Próximo número da CCe (sequência — vale sempre a última)
    cce_count = sum(1 for ev in (inv.events or []) if ev.event_type == "correction_letter")
    n_seq = cce_count + 1
    try:
        result = await sefaz_service.carta_correcao(db, inv, cmig, cfg, text, n_seq)
    except sefaz_service.SefazServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _SefazNetError as e:
        raise HTTPException(status_code=502, detail=f"SEFAZ indisponível: {e}")

    if not result.get("ok"):
        raise HTTPException(
            status_code=422,
            detail=f"SEFAZ recusou a CC-e (cStat {result.get('cstat')}): {result.get('motivo')}",
        )
    db.add(
        InvoiceEvent(
            invoice_id=inv.id,
            event_type="correction_letter",
            sequence_number=n_seq,
            reason=text,
            sefaz_protocol=result.get("protocolo"),
            sefaz_message=result.get("motivo"),
            created_by_user_id=current_user.id,
        )
    )
    await db.commit()
    return {"detail": "Carta de correção enviada"}


def _read_authorized_xml(inv: Invoice) -> str:
    """Lê o XML autorizado (procNFe) gravado localmente."""
    if not inv.xml_local_path:
        raise HTTPException(status_code=404, detail="XML da NF-e não disponível")
    p = _Path(inv.xml_local_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Arquivo XML não encontrado no servidor")
    return p.read_text(encoding="utf-8")


def _invoice_download_name(inv, tipo: str, ext: str) -> str:
    """Nome do arquivo da NF-e: usa o pedido vinculado (venda + cliente) quando existe;
    senão (NF-e de entrada, sem pedido) cai para a chave/número da nota."""
    if getattr(inv, "order", None) is not None:
        return order_download_filename(tipo, ext, order=inv.order)
    venda = inv.access_key or f"nfe-{inv.id}"
    return order_download_filename(tipo, ext, venda=venda, cliente=None)


@router.get("/{invoice_id}/xml")
async def download_xml(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Baixa o XML autorizado (procNFe) da NF-e própria."""
    inv = (
        await db.execute(
            select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.order))
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    xml = _read_authorized_xml(inv)
    fname = _invoice_download_name(inv, TIPO_NFE, "xml")
    return Response(
        content=xml.encode("utf-8"), media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{invoice_id}/danfe")
async def download_danfe(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gera e baixa o DANFE PDF da NF-e própria.

    - `authorized` → DANFE oficial, a partir do XML autorizado (comportamento original).
    - `draft` / `finalized` → **PRÉVIA**: monta o XML da nota SEM reservar número nem assinar,
      e a BrazilFiscalReport desenha a marca d'água "SEM VALOR FISCAL" (não há protocolo).
      Serve para conferir/imprimir a nota de saída com ou sem SEFAZ.
    """
    from services.fiscal.sefaz.danfe import DanfeError, gerar_danfe, gerar_danfe_previa

    inv = (
        await db.execute(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(selectinload(Invoice.order), selectinload(Invoice.items))
        )
    ).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)

    if inv.status == "authorized":
        xml = _read_authorized_xml(inv)
        try:
            pdf = await asyncio.to_thread(gerar_danfe, xml)
        except DanfeError as e:
            raise HTTPException(status_code=422, detail=f"Falha ao gerar DANFE: {e}")
        fname = _invoice_download_name(inv, TIPO_DANFE, "pdf")
    elif inv.status in ("draft", "finalized"):
        if inv.direction != "out":
            # A prévia monta o XML sempre com a CMIG como EMITENTE (tpNF=1/saída). Imprimir uma
            # COMPRA nesse formato seria um papel fiscalmente invertido circulando no galpão.
            raise HTTPException(
                status_code=400,
                detail="Prévia em PDF disponível apenas para notas de SAÍDA.",
            )
        cfg = await _get_fiscal_config(inv.cmig_id, db)
        cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()
        person = None
        if inv.person_id:
            person = (
                await db.execute(select(Person).where(Person.id == inv.person_id))
            ).scalar_one_or_none()
        from services.fiscal.sefaz.exceptions import FiscalError

        try:
            xml = sefaz_service.montar_xml_previa(inv, cmig, cfg, person, list(inv.items))
            pdf = await asyncio.to_thread(gerar_danfe_previa, xml)
        except sefaz_service.SefazServiceError as e:
            # Falhar alto: a prévia usa as MESMAS validações da emissão (IBGE/IE/NCM/destinatário)
            # e diz o que falta, em vez de imprimir um documento capenga.
            raise HTTPException(status_code=400, detail=f"Prévia indisponível: {e}")
        except DanfeError as e:
            raise HTTPException(status_code=422, detail=f"Falha ao gerar a prévia do DANFE: {e}")
        except FiscalError as e:
            # Erros de montagem do XML (campo de cadastro inválido) → 400 com o motivo,
            # nunca 500 genérico.
            raise HTTPException(status_code=400, detail=f"Prévia indisponível: {e}")
        fname = f"nfe-previa-{inv.id}.pdf"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"DANFE indisponível para nota com status '{inv.status}'.",
        )
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.post("/{invoice_id}/email")
async def email_invoice(
    invoice_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia o XML + DANFE da NF-e autorizada por e-mail, via SMTP próprio."""
    from services.fiscal.sefaz.danfe import DanfeError, gerar_danfe

    inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="NFe não encontrada")
    await _check_cmig_access(inv.cmig_id, current_user, db)
    if inv.status != "authorized":
        raise HTTPException(status_code=400, detail="Só é possível enviar e-mail de NF-e autorizada")

    emails = body.get("emails") or []
    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(",") if e.strip()]
    if not emails and inv.person_id:
        person = (
            await db.execute(select(Person).where(Person.id == inv.person_id))
        ).scalar_one_or_none()
        if person and person.email:
            emails = [person.email]
    if not emails:
        raise HTTPException(status_code=422, detail="Informe ao menos um e-mail")

    xml = _read_authorized_xml(inv)
    try:
        pdf = await asyncio.to_thread(gerar_danfe, xml)
    except DanfeError as e:
        raise HTTPException(status_code=422, detail=f"Falha ao gerar DANFE: {e}")

    chave = inv.access_key or str(inv.id)
    attachments = [
        (f"NFe-{chave}.xml", xml.encode("utf-8"), "application", "xml"),
        (f"DANFE-{chave}.pdf", pdf, "application", "pdf"),
    ]
    from services import email_service

    subject = f"NF-e {inv.nfe_number or ''} — chave {chave}"
    html = (
        "<p>Segue em anexo a NF-e (XML) e o DANFE (PDF).</p>"
        f"<p>Chave de acesso: <strong>{chave}</strong></p>"
    )
    sent = 0
    for to in emails:
        try:
            await email_service.send_email(db, to, subject, html, attachments=attachments)
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[nfe] falha ao enviar e-mail para %s: %s", to, e)
    if sent == 0:
        raise HTTPException(status_code=502, detail="Falha ao enviar e-mail (verifique a config SMTP).")
    return {"detail": f"E-mail enviado para {sent} destinatário(s)"}


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
            raise HTTPException(
                status_code=422, detail="Justificativa obrigatória (15+ caracteres)"
            )

    cfg = await _get_fiscal_config(inv.cmig_id, db)
    cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one()

    try:
        result = await sefaz_service.manifestar(db, inv, cmig, cfg, tipo, justificativa)
    except sefaz_service.SefazServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _SefazNetError as e:
        raise HTTPException(status_code=502, detail=f"SEFAZ indisponível: {e}")

    if not result.get("ok"):
        raise HTTPException(
            status_code=422,
            detail=f"SEFAZ recusou a manifestação (cStat {result.get('cstat')}): {result.get('motivo')}",
        )
    db.add(
        InvoiceEvent(
            invoice_id=inv.id,
            event_type="manifestation",
            reason=justificativa,
            sefaz_protocol=inv.manifestation_protocol,
            sefaz_message=result.get("motivo") or tipo,
            created_by_user_id=current_user.id,
        )
    )
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


def _is_simbolica(natureza: str | None) -> bool:
    """Alias local p/ a regra compartilhada (services.fiscal.fiscal_rules.is_simbolica).
    NF-e simbólica NÃO movimenta estoque (nem LOCAL nem FULL)."""
    from services.fiscal.fiscal_rules import is_simbolica

    return is_simbolica(natureza)


async def _upsert_supplier(parsed_emit: dict, cmig_id: int, db: AsyncSession) -> Person:
    """Cria ou atualiza Person (fornecedor) a partir do bloco emit do XML."""
    document = parsed_emit.get("document") or ""
    if not document:
        raise HTTPException(
            status_code=422, detail="XML não contém documento (CNPJ/CPF) do emitente"
        )

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
    """Identifica produtos CMIG/PG via EAN/SKU dos itens do XML e dispara recompute
    canônico (event-sourced) pra cada um. Items aqui não estão persistidos ainda;
    quando os items forem salvos como InvoiceItem e a NFe finalizar, o recompute
    via `_apply_stock_movement` cobre. Mantemos esta função pra import-XML legacy.
    """
    from services.fiscal.stock_calculator import (
        recompute_cmig_product_stock,
        recompute_pg_product_stock,
    )

    cmig_ids: set[int] = set()
    pg_ids: set[int] = set()
    unmatched = 0
    for it in items_data:
        ean = (it.get("ean") or "").strip()
        sku = (it.get("sku") or "").strip()
        qty = int(it.get("quantity") or 0)
        if qty == 0:
            unmatched += 1
            continue
        # Tenta CMIG por EAN dentro da cmig_id
        prod_cmig_id = None
        if ean:
            prod_cmig_id = (
                await db.execute(
                    select(CMIGProduct.id).where(
                        and_(CMIGProduct.cmig_id == cmig_id, CMIGProduct.ean == ean)
                    )
                )
            ).scalar_one_or_none()
        if prod_cmig_id:
            cmig_ids.add(prod_cmig_id)
            continue
        # Fallback: PG por SKU → EAN
        prod_pg_id = None
        if sku:
            prod_pg_id = (
                await db.execute(select(CatalogProduct.id).where(CatalogProduct.sku == sku))
            ).scalar_one_or_none()
        if not prod_pg_id and ean:
            prod_pg_id = (
                await db.execute(select(CatalogProduct.id).where(CatalogProduct.ean == ean))
            ).scalar_one_or_none()
        if prod_pg_id:
            pg_ids.add(prod_pg_id)
            continue
        unmatched += 1

    for cp_id in cmig_ids:
        await recompute_cmig_product_stock(cp_id, db)
    for pg_id in pg_ids:
        await recompute_pg_product_stock(pg_id, db)

    return {
        "cmig_recomputed": len(cmig_ids),
        "pg_recomputed": len(pg_ids),
        "unmatched": unmatched,
    }


@router.post("/import-xml", status_code=201)
async def import_xml(
    cmig_id: int = Form(...),
    update_stock: bool = Form(False),
    xml_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("fiscal_entradas")),
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

    # Atualizar estoque (opcional). NF-e simbólica NÃO movimenta estoque, mesmo
    # com update_stock marcado (mantém stock_updated=False → inerte ao recompute).
    stock_result = {"matched": 0, "unmatched": 0}
    if update_stock and not _is_simbolica(inv.natureza_operacao):
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


# ── Importação de XML (saída / remessa para FULL) ─────────────────────────────


def _invoice_item_from_parsed(invoice_id: int, it_data: dict) -> InvoiceItem:
    """Cria um InvoiceItem a partir de um item parseado do XML (mapeamento fiscal)."""
    return InvoiceItem(
        invoice_id=invoice_id,
        item_number=it_data.get("item_number") or 1,
        cfop=it_data.get("cfop") or None,
        ncm=it_data.get("ncm") or None,
        cest=it_data.get("cest") or None,
        description=it_data.get("description") or "(sem descrição)",
        sku=it_data.get("sku") or None,
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


async def _resolve_item_match(item: InvoiceItem, cmig_id: int | None, db: AsyncSession) -> bool:
    """Casa o item a um produto (PG por SKU→EAN; CMIG por EAN no cmig_id) e grava
    `source_type` + FK. NÃO muta estoque (event-sourced). Retorna True se casou.

    Necessário tanto para a baixa LOCAL (recompute filtra PG por source_type='pg')
    quanto para o crédito FULL (apply_nfe_saida_to_full casa por FK)."""
    from services.fiscal.stock_apply import _find_cmig, _find_pg

    pg = await _find_pg(item, db)
    if pg:
        item.source_type = "pg"
        item.catalog_product_id = pg.id
        return True
    cmig = await _find_cmig(item, cmig_id, db)
    if cmig:
        item.source_type = "cmig"
        item.cmig_product_id = cmig.id
        return True
    return False


async def _upsert_recipient(parsed_dest: dict, cmig_id: int, db: AsyncSession) -> Person:
    """Cria/atualiza Person (destinatário) a partir do bloco dest do XML de saída."""
    document = parsed_dest.get("document") or ""
    if not document:
        raise HTTPException(
            status_code=422, detail="XML não contém documento (CNPJ/CPF) do destinatário"
        )
    existing = (
        await db.execute(
            select(Person).where(and_(Person.cmig_id == cmig_id, Person.document == document))
        )
    ).scalar_one_or_none()
    if existing:
        if not existing.is_customer:
            existing.is_customer = True
        if not existing.ie and parsed_dest.get("ie"):
            existing.ie = parsed_dest["ie"]
        return existing
    person = Person(
        cmig_id=cmig_id,
        name=parsed_dest.get("name") or "Destinatário",
        trade_name=parsed_dest.get("trade_name") or None,
        document=document,
        person_type="PJ" if len(_normalize_cnpj(document)) == 14 else "PF",
        ie=parsed_dest.get("ie") or None,
        is_customer=True,
        street=parsed_dest.get("street") or None,
        address_number=parsed_dest.get("number") or None,
        neighborhood=parsed_dest.get("neighborhood") or None,
        city=parsed_dest.get("city") or None,
        state=parsed_dest.get("state") or None,
        zip_code=parsed_dest.get("zip_code") or None,
    )
    db.add(person)
    await db.flush()
    return person


@router.post("/import-xml-saida", status_code=201)
async def import_xml_saida(
    cmig_id: int = Form(...),
    xml_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("fiscal_saidas")),
):
    """Importa um XML de NFe de SAÍDA emitida pela CMIG.

    Dá baixa no estoque LOCAL (event-sourced). Se o destinatário for um CNPJ FULL
    cadastrado, é uma remessa: credita o estoque FULL da conta correspondente.
    """
    from services.full_stock_service import apply_nfe_saida_to_full, is_full_cnpj

    cmig = await _check_cmig_access(cmig_id, current_user, db)

    content = await xml_file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo XML vazio")
    try:
        parsed = parse_nfe_xml(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    access_key = parsed.get("access_key") or ""
    if not access_key or len(access_key) != 44:
        raise HTTPException(status_code=422, detail="Chave de acesso inválida ou ausente no XML")

    # Na saída, o EMITENTE é a CMIG.
    emit_cnpj = _normalize_cnpj(parsed.get("emit", {}).get("document", ""))
    cmig_cnpj = _normalize_cnpj(cmig.cnpj)
    if emit_cnpj and cmig_cnpj and emit_cnpj != cmig_cnpj:
        raise HTTPException(
            status_code=422,
            detail=f"XML emitido pelo CNPJ {emit_cnpj}, mas a CMIG selecionada é {cmig_cnpj}",
        )

    existing = (
        await db.execute(select(Invoice).where(Invoice.access_key == access_key))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"NFe já importada (Invoice #{existing.id})")

    dest = parsed.get("dest", {}) or {}
    recipient = await _upsert_recipient(dest, cmig_id, db)
    dest_document = dest.get("document") or ""

    full_cnpj = await is_full_cnpj(db, dest_document, cmig_id)
    totals = parsed.get("totals", {})
    transport = parsed.get("transport", {})

    inv = Invoice(
        cmig_id=cmig_id,
        direction="out",
        purpose="remessa" if full_cnpj else "venda",
        model=parsed.get("model") or "55",
        serie=parsed.get("serie"),
        nfe_number=parsed.get("nfe_number"),
        access_key=access_key,
        person_id=recipient.id,
        natureza_operacao=parsed.get("natureza_operacao")
        or ("Remessa para depósito (FULL)" if full_cnpj else "Venda"),
        issue_date=parsed.get("issue_date"),
        exit_date=parsed.get("exit_date"),
        status="authorized",  # XML já autorizado pelo marketplace
        # 'xml_upload' é o valor permitido pelo CHECK chk_inv_inbound_source;
        # a saída se distingue da entrada por direction='out'.
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

    matched, unmatched = [], []
    for it_data in parsed.get("items", []):
        item = _invoice_item_from_parsed(inv.id, it_data)
        db.add(item)
        await db.flush()
        if await _resolve_item_match(item, cmig_id, db):
            matched.append(item.description)
        else:
            unmatched.append(item.description)

    # Baixa LOCAL (event-sourced) + crédito FULL em UMA transação atômica:
    # se o FULL falhar, nada é persistido (a NF-e pode ser reimportada).
    full_result = None
    simbolica = _is_simbolica(inv.natureza_operacao)
    try:
        if simbolica:
            # Remessa/saída simbólica: registra a NF-e mas NÃO movimenta estoque.
            stock = {"cmig_ids": set(), "pg_ids": set(), "simbolica": True}
            await db.commit()
        else:
            stock = await _apply_stock_movement(inv, db)
            if full_cnpj:
                full_result = await apply_nfe_saida_to_full(db, inv, full_cnpj.marketplace_account_id)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("[import-xml-saida] falha ao aplicar estoque/FULL")
        raise HTTPException(status_code=500, detail=f"Falha ao aplicar estoque/FULL: {exc}")

    try:
        from services.stock_sync_service import schedule_push

        schedule_push(stock.get("cmig_ids", set()), stock.get("pg_ids", set()))
    except Exception:  # noqa: BLE001
        pass

    return {
        "invoice_id": inv.id,
        "access_key": access_key,
        "direction": "out",
        "is_full_remessa": bool(full_cnpj),
        "full_account_id": full_cnpj.marketplace_account_id if full_cnpj else None,
        "full_credit": full_result,
        "recipient": {"id": recipient.id, "name": recipient.name, "document": recipient.document},
        "items_count": len(parsed.get("items", [])),
        "matched_count": len(matched),
        "unmatched": unmatched,
        "stock_movement": stock,
    }


# ── Reconciliação da sequência de NF-e emitidas (Fase 3d) ────────────────────


async def _compute_sequence_report(
    db: AsyncSession, cmig_id: int, serie: int | None = None, missing_cap: int = 500
) -> dict:
    """Reconstrói a sequência de NF-e EMITIDAS pela CMIG (por série) a partir do que
    está persistido, e aponta os FUROS reais.

    Base da sequência = notas da CMIG com número/série, EXCETO devolução (emitida por
    terceiro — não pertence à numeração da CMIG). Um número ausente no intervalo
    [min,max] só é FURO se NÃO estiver coberto por uma inutilização registrada
    (`nfe_inutilizacoes`). Cancelada/denegada CONSOME número (fica presente, com status).

    Furo = ALERTA, não prova de erro: pode ser inutilização feita no próprio ML (a API
    não expõe) ou nota de outro mês ainda não sincronizada. Read-only, reutilizável
    (job de sync + rota /outbound/sequence-report)."""
    # Base da sequência = notas NUMERADAS pela CMIG. Exclui SÓ a devolução de ENTRADA
    # de terceiro capturada do Faturador ML (número pertence à série do cliente). A
    # devolução emitida pela PRÓPRIA CMIG (emissão própria / saída) numera na série da
    # CMIG e DEVE entrar — senão vira furo falso (A1). Discriminador = direction+source,
    # não `purpose`.
    q = select(Invoice.serie, Invoice.nfe_number, Invoice.status).where(
        Invoice.cmig_id == cmig_id,
        Invoice.nfe_number.isnot(None),
        Invoice.serie.isnot(None),
        ~and_(
            Invoice.purpose == "devolucao",
            Invoice.direction == "in",
            func.coalesce(Invoice.source, "") == "ml_faturador",
        ),
    )
    if serie is not None:
        q = q.where(Invoice.serie == serie)
    present: dict[int, dict[int, str]] = {}
    for s, n, st in (await db.execute(q)).all():
        present.setdefault(int(s), {})[int(n)] = st

    inut_q = select(
        NfeInutilizacao.serie, NfeInutilizacao.nro_ini, NfeInutilizacao.nro_fim
    ).where(NfeInutilizacao.cmig_id == cmig_id)
    if serie is not None:
        inut_q = inut_q.where(NfeInutilizacao.serie == serie)
    inut: dict[int, set[int]] = {}
    for s, a, b in (await db.execute(inut_q)).all():
        rng = inut.setdefault(int(s), set())
        rng.update(range(int(a), int(b) + 1))

    _CANCELLED = {"cancelled", "cancelada", "canceled", "denegada", "denied"}
    series_out = []
    for s in sorted(set(present) | set(inut)):
        nums = present.get(s, {})
        inut_s = inut.get(s, set())
        allnums = set(nums) | inut_s
        if not allnums:
            continue
        lo, hi = min(allnums), max(allnums)
        # Guard: um número outlier (parse anômalo / série renumerada) não pode materializar
        # um range de milhões. Acima do teto, reporta a anomalia sem expandir.
        _RANGE_CAP = 200_000
        if hi - lo > _RANGE_CAP:
            series_out.append(
                {
                    "serie": s, "count": len(nums), "min": lo, "max": hi,
                    "expected": hi - lo + 1, "missing_count": -1, "missing": [],
                    "missing_truncated": True, "inutilized_count": len(inut_s),
                    "inutilized": [], "cancelled_count": 0, "cancelled": [],
                    "anomaly": "intervalo de numeração acima do teto — verifique número atípico",
                }
            )
            continue
        missing = [n for n in range(lo, hi + 1) if n not in nums and n not in inut_s]
        cancelled = sorted(n for n, st in nums.items() if (st or "").lower() in _CANCELLED)
        series_out.append(
            {
                "serie": s,
                "count": len(nums),
                "min": lo,
                "max": hi,
                "expected": hi - lo + 1,
                "missing_count": len(missing),
                "missing": missing[:missing_cap],
                "missing_truncated": len(missing) > missing_cap,
                "inutilized_count": len(inut_s),
                "inutilized": sorted(inut_s)[:missing_cap],
                "cancelled_count": len(cancelled),
                "cancelled": cancelled[:missing_cap],
            }
        )
    return {
        "cmig_id": cmig_id,
        "series": series_out,
        "total_missing": sum(x["missing_count"] for x in series_out),
    }


# ── Sincronização de TODAS as NF-e do mês (batch do Faturador ML) ─────────────
# Fecha a sequência (todas as notas viram registro — Fase 3c) e move estoque APENAS
# das notas de FULL: remessa (LOCAL↓+FULL↑) e retorno/retirada (LOCAL↑+FULL↓). Venda
# casada / saída-sem-pedido / devolução são fiscal-only (não mexem estoque).


async def _sync_ml_fiscal_account(account_id: int, cmig_id: int, year: int, month: int, user_id: int) -> dict:
    """Background: baixa o lote de NF-e do mês de uma conta ML e cria os registros
    que faltam. HTTP do zip FORA da sessão de BD; uma transação curta por nota."""
    import calendar as _cal

    from services.full_stock_service import (
        _is_deposito_cycle,
        apply_nfe_entrada_from_full,
        apply_nfe_saida_to_full,
        is_full_cnpj,
    )

    async with task_db() as db:
        acc = (
            await db.execute(select(MarketplaceAccount).where(MarketplaceAccount.id == account_id))
        ).scalar_one_or_none()
        if not acc or not acc.access_token or not acc.platform_user_id:
            return {"account_id": account_id, "created": 0, "skipped": 0, "full_moved": 0}
        token, seller_id = acc.access_token, acc.platform_user_id

    start = f"{year}{month:02d}01"
    last = _cal.monthrange(year, month)[1]
    end = f"{year}{month:02d}{last:02d}"
    try:
        entries = await _ml.download_invoices_batch(token, seller_id, start, end)
    except _ml.MLInvoiceBatchError as exc:
        # Falha de fetch (429/5xx/rede após retries): o mês fica INCOMPLETO. NÃO processa nem roda
        # detecção de furos (reportaria furos FALSOS). Sinaliza p/ re-tentar depois (falhar alto).
        logger.warning(
            "[fiscal] batch %s-%02d conta %s FALHOU (mês incompleto, não reconciliar): %s",
            year, month, account_id, exc)
        return {"account_id": account_id, "created": 0, "skipped": 0, "full_moved": 0,
                "fetch_failed": True, "gaps": {}}

    created = skipped = full_moved = simbolicas = 0
    vendas_casadas = saidas_sem_pedido = devolucoes = descartadas = errored = 0
    vendas_full_baixadas = 0  # vendas de pedido FULL que baixaram o galpão (par do retorno)
    seq: dict[int, set[int]] = {}  # série → números de NF-e vistos no lote (p/ furos)
    # O zip do ML não separa por tipo (vem tudo em "emitidas_mercado_livre/"), então
    # classificamos pela própria nota, em BALDES (Fase 3c — guardar TODAS p/ fechar a
    # sequência sem furo falso). O estoque é movido APENAS pelo balde FULL:
    #   • FULL (dest/emit = CNPJ FULL): remessa (LOCAL↓+FULL↑) / retorno (LOCAL↑+FULL↓) — MOVE estoque.
    #   • Venda casada (saída não-FULL cuja chave = Order.nfe_key): fiscal-only, order_id setado,
    #     NÃO move estoque (o pedido já debitou o LOCAL — ADR-0019).
    #   • Saída sem pedido (saída não-FULL sem pedido casado): registra e SINALIZA (order_id NULL +
    #     fiscal_info), NÃO move estoque (bonificação/brinde/comodato a revisar).
    #   • Devolução (entrada não-FULL, CFOP 1/2/3): fiscal-only (ADR-0009 — contadores de inspeção
    #     são a fonte canônica), NÃO move estoque.
    # Modelo ≠ 55/65 (CT-e 57 / MDF-e 58) é descartado. Eventos (CC-e/cancelamento) são
    # procEventoNFe → parse_nfe_xml levanta ValueError e caem no except (pulados).
    for _category, _name, xml_bytes in entries:
        try:
            parsed = parse_nfe_xml(xml_bytes)
        except Exception:  # noqa: BLE001
            continue
        access_key = parsed.get("access_key") or ""
        if len(access_key) != 44:
            continue
        # Coleta nº por série (todas as NF-e do lote) para detectar furos depois.
        _s, _n = parsed.get("serie"), parsed.get("nfe_number")
        if _s is not None and _n is not None:
            try:
                seq.setdefault(int(_s), set()).add(int(_n))
            except (TypeError, ValueError):
                pass
        # Só NF-e/NFC-e (modelo 55/65). CT-e (57)/MDF-e (58)/outros: descartar (fora do lote fiscal).
        model = str(parsed.get("model") or "55")
        if model not in ("55", "65"):
            descartadas += 1
            continue
        try:
            async with task_db() as db:
                dest = parsed.get("dest", {}) or {}
                emit = parsed.get("emit", {}) or {}

                # Dedup por chave — agora vale p/ TODAS as notas (não só FULL). Idempotente:
                # re-sincronizar o mês não duplica nada. (Upsert de cancelamento fica p/ quando
                # houver fonte confiável do status — o lote de NF-e não expõe cancelamento.)
                existing = (
                    await db.execute(
                        select(Invoice).where(Invoice.access_key == access_key)
                    )
                ).scalar_one_or_none()
                if existing:
                    # Religa órfão: se a nota de venda foi capturada ANTES de o pedido gravar
                    # Order.nfe_key, ficou com order_id NULL. Agora que o pedido existe, vincula
                    # (fiscal-only — não mexe em estoque). Evita órfão permanente (M2).
                    if (
                        existing.order_id is None
                        and existing.source == "ml_faturador"
                        and existing.direction == "out"
                        and existing.purpose == "venda"
                    ):
                        mo = (
                            await db.execute(
                                select(Order.id).where(
                                    and_(Order.nfe_key == access_key, Order.cmig_id == cmig_id)
                                )
                            )
                        ).scalar_one_or_none()
                        if mo:
                            existing.order_id = mo
                            existing.fiscal_info = None  # deixa de ser "saída sem pedido"
                            await db.commit()
                    skipped += 1
                    continue

                # Direção pela CFOP do 1º item (não pela posição do CNPJ):
                # 1/2/3 = entrada; 5/6/7 = saída.
                first_cfop = next(
                    (str(it.get("cfop") or "") for it in parsed.get("items", []) if it.get("cfop")),
                    "",
                )
                # Direção: tpNF (canônico — MOC B11: 0=entrada, 1=saída) é a fonte primária;
                # CFOP do 1º item é reforço. Sem nenhum dos dois, NÃO assumir (falhar alto).
                tp_nf = parsed.get("tp_nf")
                if tp_nf == 0:
                    is_inbound = True
                elif tp_nf == 1:
                    is_inbound = False
                elif first_cfop[:1] in ("1", "2", "3"):
                    is_inbound = True
                elif first_cfop[:1] in ("5", "6", "7"):
                    is_inbound = False
                else:
                    logger.warning(
                        "[sync-ml-fiscal] nota ...%s sem tpNF/CFOP p/ definir direção — pulada",
                        access_key[-6:],
                    )
                    skipped += 1
                    continue

                full_dest = await is_full_cnpj(db, dest.get("document") or "", cmig_id)
                full_emit = await is_full_cnpj(db, emit.get("document") or "", cmig_id)
                full = full_dest or full_emit
                # Retorno de depósito é AUTO-EMITIDO pelo vendedor (a nota não traz o CNPJ do EBAZAR
                # — emitente e destinatário são o próprio vendedor), então `is_full_cnpj` falha.
                # Reconhece pela natureza de depósito e usa a conta FULL da CMIG.
                if not full and _is_deposito_cycle(parsed.get("natureza_operacao")):
                    from services.full_stock_service import FullCnpj
                    full = (
                        await db.execute(
                            select(FullCnpj)
                            .where(FullCnpj.cmig_id == cmig_id, FullCnpj.is_active == 1)
                            .order_by(FullCnpj.marketplace_account_id)
                        )
                    ).scalars().first()

                # ── Classificação em baldes ─────────────────────────────────────
                review_note = None
                matched_order_id = None
                matched_order_full = False
                if full:
                    # BALDE FULL (comportamento inalterado): move estoque LOCAL⇄FULL.
                    # NB: `move="full_out"/"full_in"` aqui = remessa/retorno que CREDITA/DEBITA
                    # o FULL via NF-e. NÃO confundir com o débito de venda do FULL da ADR-0019
                    # (dirigido pelo PEDIDO em recompute_full_stock) — este código não o emite.
                    if is_inbound:
                        direction, purpose, party, move = "in", "retorno", emit, "full_in"
                    else:
                        direction, purpose, party, move = "out", "remessa", dest, "full_out"
                elif is_inbound:
                    # BALDE DEVOLUÇÃO (não-FULL, entrada): fiscal-only, NÃO move estoque (ADR-0009).
                    direction, purpose, party, move = "in", "devolucao", emit, "none"
                    for rk in parsed.get("referenced_keys", []):
                        mo = (
                            await db.execute(
                                select(Order.id).where(
                                    and_(Order.nfe_key == rk, Order.cmig_id == cmig_id)
                                )
                            )
                        ).scalar_one_or_none()
                        if mo:
                            matched_order_id = mo
                            break
                else:
                    # Saída não-FULL: venda casada com pedido OU saída sem pedido (SINALIZAR).
                    direction, purpose, party, move = "out", "venda", dest, "none"
                    _mo = (
                        await db.execute(
                            select(Order.id, Order.shipping_mode).where(
                                and_(Order.nfe_key == access_key, Order.cmig_id == cmig_id)
                            )
                        )
                    ).first()
                    matched_order_id = _mo[0] if _mo else None
                    # Modalidade do pedido casado: decide QUEM baixa o galpão nesta venda
                    # (ver o ramo `elif matched_order_id:` mais abaixo).
                    matched_order_full = bool(_mo) and (_mo[1] or "") == "full"
                    if not matched_order_id:
                        # BALDE SAÍDA-SEM-PEDIDO: registra e SINALIZA (order_id NULL + fiscal_info).
                        # NÃO debita estoque (bonificação/brinde/comodato/amostra a revisar).
                        review_note = (
                            "Saída do Faturador ML sem pedido casado — revisar "
                            "(bonificação/brinde/comodato/amostra?)."
                        )

                person = (
                    await _upsert_recipient(party, cmig_id, db)
                    if direction == "out"
                    else await _upsert_supplier(party, cmig_id, db)
                )
                totals = parsed.get("totals", {})
                transport = parsed.get("transport", {})
                inv = Invoice(
                    cmig_id=cmig_id,
                    direction=direction,
                    purpose=purpose,
                    model=model,
                    serie=parsed.get("serie"),
                    nfe_number=parsed.get("nfe_number"),
                    access_key=access_key,
                    person_id=person.id,
                    order_id=matched_order_id,
                    natureza_operacao=parsed.get("natureza_operacao"),
                    issue_date=parsed.get("issue_date"),
                    exit_date=parsed.get("exit_date"),
                    status="authorized",
                    source="ml_faturador",
                    inbound_source="xml_upload" if direction == "in" else None,
                    manifestation="not_required" if direction == "in" else None,
                    freight_modality=transport.get("freight_modality"),
                    additional_info=parsed.get("additional_info") or None,
                    fiscal_info=review_note,
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
                    created_by_user_id=user_id,
                )
                db.add(inv)
                await db.flush()
                for it_data in parsed.get("items", []):
                    item = _invoice_item_from_parsed(inv.id, it_data)
                    db.add(item)
                    await db.flush()
                    await _resolve_item_match(item, cmig_id, db)

                # ── Estoque: o balde FULL move (inclui remessa/retorno SIMBÓLICO do ciclo FULL:
                # o par transfere Galpão⇄FULL). Simbólica NÃO-FULL (`not full`) segue inerte. ──
                if _is_simbolica(inv.natureza_operacao) and not full:
                    # Simbólica não-FULL: registra (mantém a sequência) mas NÃO move estoque.
                    simbolicas += 1
                elif move == "full_out":
                    await _apply_stock_movement(inv, db, full_cycle=True)
                    await apply_nfe_saida_to_full(db, inv, full.marketplace_account_id)
                    full_moved += 1
                elif move == "full_in":
                    await _apply_stock_movement(inv, db, full_cycle=True)
                    await apply_nfe_entrada_from_full(db, inv, full.marketplace_account_id)
                    full_moved += 1
                elif direction == "in":
                    devolucoes += 1  # fiscal-only
                elif matched_order_id and matched_order_full:
                    # VENDA DE PEDIDO FULL: o par fiscal da venda FULL são DUAS notas —
                    # o retorno simbólico (entrada, devolve ao galpão e debita o FULL) e
                    # ESTA nota de venda, que dá a baixa FÍSICA do galpão. O PEDIDO FULL é
                    # excluído do débito local de propósito (`local_order_clause`), então
                    # sem esta baixa o crédito do retorno fica solto e infla o galpão.
                    # `full_cycle=True`: participa do ciclo FULL como o retorno que a precede.
                    await _apply_stock_movement(inv, db, full_cycle=True)
                    vendas_full_baixadas += 1
                elif matched_order_id:
                    # Venda NÃO-FULL: o pedido já debitou o galpão (local_order_clause inclui
                    # o pedido não-FULL) → a nota é fiscal-only, senão haveria DUPLA baixa.
                    vendas_casadas += 1
                else:
                    saidas_sem_pedido += 1  # SINALIZADA (order_id NULL + fiscal_info)

                await db.commit()
                created += 1
        except Exception as e:  # noqa: BLE001
            errored += 1  # nota problemática não some em silêncio — vai no resumo
            logger.warning("[sync-ml-fiscal] nota ...%s: %s", access_key[-6:], e)

    # Furos de sequência (cross-mês): agora que TODAS as notas do lote foram persistidas
    # (Fase 3c), a reconciliação sai do estado do BD via o helper reutilizável (Fase 3d),
    # que já cruza inutilizações e ignora devolução. Reporta só as séries vistas no lote.
    gaps: dict[int, list[int]] = {}
    seen_series = set(seq.keys())
    async with task_db() as db:
        rep = await _compute_sequence_report(db, cmig_id, missing_cap=200)
    for s in rep["series"]:
        if s["serie"] in seen_series and s["missing"]:
            gaps[s["serie"]] = s["missing"]
    if gaps:
        logger.warning(
            "[sync-ml-fiscal] conta %s %s/%s FUROS de sequência (sincronizar de novo): %s",
            account_id, month, year, gaps,
        )
    logger.info(
        "[sync-ml-fiscal] conta %s %s/%s: criadas=%s (full=%s venda=%s s/pedido=%s devol=%s "
        "simb=%s) puladas=%s descartadas=%s erros=%s furos=%s",
        account_id, month, year, created, full_moved, vendas_casadas, saidas_sem_pedido,
        devolucoes, simbolicas, skipped, descartadas, errored,
        sum(len(v) for v in gaps.values()),
    )
    return {
        "account_id": account_id,
        "created": created,
        "skipped": skipped,
        "descartadas": descartadas,
        "errored": errored,
        "full_moved": full_moved,
        "vendas_casadas": vendas_casadas,
        "vendas_full_baixadas": vendas_full_baixadas,
        "saidas_sem_pedido": saidas_sem_pedido,
        "devolucoes": devolucoes,
        "simbolicas": simbolicas,
        "gaps": gaps,
    }


async def _launch_ml_fiscal_sync(
    db: AsyncSession, cmig_ids: list[int], periods: list[tuple[int, int]], uid: int
) -> int:
    """Resolve as contas ML ativas das CMIGs e dispara, em BACKGROUND, o sync fiscal do
    batch do Faturador para cada (conta × período). Sequencial (o batch é sensível a 429).
    Compartilhado por sync mensal e backfill (evita divergência de RBAC/duplicação). Retorna
    o nº de contas."""
    accounts = (
        await db.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.cmig_id.in_(cmig_ids),
                MarketplaceAccount.platform == "mercadolivre",
                MarketplaceAccount.is_active == True,  # noqa: E712
                MarketplaceAccount.access_token.isnot(None),
            )
        )
    ).scalars().all()
    pairs = [(acc.id, acc.cmig_id) for acc in accounts]

    async def _run():
        for acc_id, acc_cmig in pairs:
            for (yy, mm) in periods:
                try:
                    await _sync_ml_fiscal_account(acc_id, acc_cmig, yy, mm, uid)
                except Exception as e:  # noqa: BLE001
                    logger.error("[ml-fiscal-sync] conta %s %s/%s: %s", acc_id, mm, yy, e)

    task = asyncio.create_task(_run())
    _BG_TASKS.add(task)  # retém referência (evita coleta pelo GC)
    task.add_done_callback(_BG_TASKS.discard)
    return len(pairs)


@router.post("/outbound/sync-ml-fiscal")
async def sync_ml_fiscal(
    period: str = Query(..., regex=r"^\d{6}$"),  # AAAAMM
    cmig_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ac", "admin")),
):
    """Dispara (em background) a sincronização de TODAS as NF-e do mês das contas ML da
    CMIG via batch do Faturador — grava a sequência completa e move estoque das notas FULL.
    Restrito a ac/admin (escrita fiscal + movimento de estoque), como /inutilize."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"started": 0, "accounts": 0, "period": period}
    cmig_ids = [cmig_id] if cmig_id is not None else accessible
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    year, month = int(period[:4]), int(period[4:6])
    if not (1 <= month <= 12):
        raise HTTPException(status_code=422, detail="Período inválido (use AAAAMM).")

    started = await _launch_ml_fiscal_sync(db, cmig_ids, [(year, month)], current_user.id)
    return {"started": started, "accounts": started, "period": period}


@router.post("/outbound/backfill-ml-fiscal")
async def backfill_ml_fiscal(
    cmig_id: int | None = Query(None),
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ac", "admin")),
):
    """Backfill (em background) de TODAS as NF-e dos últimos `months` meses das contas
    ML da CMIG — varre mês a mês do mais recente ao mais antigo (Fase 4). Idempotente:
    o dedup por chave da Fase 3c evita duplicar o que já foi capturado. Roda DEPOIS da
    paginação (Fase 3b) já estar no ar, então o volume gerado não estoura a listagem.
    Restrito a ac/admin (escrita fiscal + movimento de estoque), como o sync mensal."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"started": 0, "accounts": 0, "months": months, "periods": []}
    cmig_ids = [cmig_id] if cmig_id is not None else accessible
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    # Lista de (ano, mês) do mais recente p/ trás (datetime.now aqui, no request, é seguro).
    from datetime import datetime as _dt
    today = _dt.now()
    periods: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(months):
        periods.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    started = await _launch_ml_fiscal_sync(db, cmig_ids, periods, current_user.id)
    return {"started": started, "accounts": started, "months": months,
            "periods": [f"{yy}{mm:02d}" for yy, mm in periods]}


@router.get("/outbound/sequence-report")
async def outbound_sequence_report(
    cmig_id: int | None = Query(None),
    serie: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Relatório READ-ONLY da sequência de NF-e emitidas por CMIG (Fase 3d/4): por série,
    total, faixa [min,max], furos reais (descontando inutilizações), inutilizados e
    cancelados. Furo = ALERTA (pode ser inutilização feita no ML, que a API não expõe)."""
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"items": []}
    if cmig_id is not None and cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
    target = [cmig_id] if cmig_id is not None else accessible

    cmig_names = dict(
        (await db.execute(select(CMIG.id, CMIG.company_name).where(CMIG.id.in_(target)))).all()
    )
    items = []
    for cid in target:
        rep = await _compute_sequence_report(db, cid, serie=serie)
        if rep["series"]:
            items.append({"cmig_id": cid, "cmig_name": cmig_names.get(cid), **rep})
    return {"items": items}


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


async def _upsert_customer_from_order(
    db: AsyncSession, order: Order, cmig_id: int
) -> Person | None:
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
        (addr.get("city") or {}).get("name")
        if isinstance(addr.get("city"), dict)
        else addr.get("city") or addr.get("municipio") or ""
    )
    state = (
        (addr.get("state") or {}).get("id")
        if isinstance(addr.get("state"), dict)
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
            description=(oi.title or (cmig_product.title if cmig_product else "(sem descrição)"))[
                :500
            ],
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

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe uma NF-e com essa série e número para esta CMIG.",
        )
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
            if items_unmapped
            else []
        ),
    }


# ── Inutilização de numeração (Fase 1 — Controle de Gaps) ─────────────────────


@router.post("/inutilize")
async def inutilize_nfe_range(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Inutiliza faixa de numeração NFe que não foi emitida (evita gaps).

    Body:
      cmig_id, ano, serie, nro_ini, nro_fim, justificativa
    """
    if current_user.role not in ("ac", "admin"):
        raise HTTPException(status_code=403, detail="Apenas AC ou admin podem inutilizar numeração")

    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=422, detail="cmig_id obrigatório")

    justificativa = (body.get("justificativa") or "").strip()
    if len(justificativa) < 15:
        raise HTTPException(
            status_code=422, detail="justificativa deve ter no mínimo 15 caracteres"
        )

    nro_ini = body.get("nro_ini")
    nro_fim = body.get("nro_fim") or nro_ini
    serie = body.get("serie", 1)
    ano = body.get("ano") or date.today().year

    if not nro_ini:
        raise HTTPException(status_code=422, detail="nro_ini obrigatório")

    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    cfg = await _get_fiscal_config(cmig_id, db)
    if not (cfg.cert_path and cfg.cert_pass_encrypted):
        raise HTTPException(status_code=400, detail="CMIG sem certificado A1 configurado")

    try:
        result = await sefaz_service.inutilizar(
            db, cmig, cfg, serie=int(serie), n_ini=int(nro_ini), n_fim=int(nro_fim),
            ano=int(ano), justificativa=justificativa,
        )
    except sefaz_service.SefazServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _SefazNetError as e:
        raise HTTPException(status_code=502, detail=f"SEFAZ indisponível: {e}")

    if not result.get("ok"):
        raise HTTPException(
            status_code=422,
            detail=f"SEFAZ não inutilizou (cStat {result.get('cstat')}): {result.get('motivo')}",
        )

    # Persiste a faixa inutilizada para a reconciliação de sequência (Fase 3d) NÃO
    # reportar esses números como furo. Sem este registro, todo número inutilizado
    # apareceria como furo falso.
    inut = NfeInutilizacao(
        cmig_id=int(cmig_id),
        serie=int(serie),
        nro_ini=int(nro_ini),
        nro_fim=int(nro_fim),
        justificativa=justificativa,
        protocol=result.get("protocolo"),
        inut_date=datetime.utcnow(),
        source="sefaz_own",
    )
    db.add(inut)
    await db.commit()
    return {
        "detail": f"Numeração {nro_ini}-{nro_fim} (série {serie}/{ano}) inutilizada",
        "protocolo": result.get("protocolo"),
    }


@router.post("/outbound/inutilizacao-manual")
async def register_manual_inutilizacao(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ac", "admin")),
):
    """Registra uma faixa de numeração inutilizada FORA do sistema — tipicamente uma
    inutilização feita no próprio Mercado Livre (a API do ML não a expõe), para a
    reconciliação de sequência (Fase 3d) não reportar esses números como furo.

    Body: cmig_id, serie, nro_ini, nro_fim, justificativa?  (source='manual')."""
    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=422, detail="cmig_id obrigatório")
    accessible = await _accessible_cmig_ids(current_user, db)
    if cmig_id not in accessible:
        raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")

    try:
        serie = int(body.get("serie", 1))
        nro_ini = int(body.get("nro_ini"))
        nro_fim = int(body.get("nro_fim") or nro_ini)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="serie/nro_ini/nro_fim inválidos")
    if nro_fim < nro_ini:
        raise HTTPException(status_code=422, detail="nro_fim deve ser >= nro_ini")

    inut = NfeInutilizacao(
        cmig_id=int(cmig_id),
        serie=serie,
        nro_ini=nro_ini,
        nro_fim=nro_fim,
        justificativa=(body.get("justificativa") or "Inutilização registrada manualmente").strip()[:255],
        protocol=None,
        inut_date=datetime.utcnow(),
        source="manual",
    )
    db.add(inut)
    await db.commit()
    return {"detail": f"Faixa {nro_ini}-{nro_fim} (série {serie}) registrada como inutilizada"}

import json
import logging
import os
import uuid as _uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.return_ import Return
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pending-validation")
async def list_pending_validation(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Return).where(Return.status == "awaiting_validation")
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Return.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    return {
        "items": [_serialize(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("")
async def list_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = None,
    all: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if all and current_user.role in ("ugo", "admin"):
        query = select(Return)
    else:
        query = select(Return).where(Return.dropshipper_id == current_user.id)
    if status:
        query = query.where(Return.status == status)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query = query.order_by(Return.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": r.id,
                "order_id": r.order_id,
                "reason": r.reason,
                "tracking_code": r.tracking_code,
                "status": r.status,
                "return_type": r.return_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=201)
async def create_return(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ret = Return(
        dropshipper_id=current_user.id,
        order_id=body.get("order_id"),
        reason=body.get("reason"),
        description=body.get("description"),
        tracking_code=body.get("tracking_code"),
        tracking_url=body.get("tracking_url"),
        carrier=body.get("carrier"),
        security_code=body.get("security_code"),
    )
    db.add(ret)
    await db.commit()
    await db.refresh(ret)
    return {"id": ret.id, "status": ret.status}


@router.get("/{return_id}")
async def get_return(
    return_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")
    if current_user.role not in ("ugo", "admin") and ret.dropshipper_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return _serialize(ret)


@router.put("/{return_id}/status")
async def update_return_status(
    return_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")

    prev_status = ret.status
    ret.status = body["status"]
    if body.get("supplier_notes"):
        ret.supplier_notes = body["supplier_notes"]
    if body.get("credit_amount"):
        ret.credit_amount = body["credit_amount"]

    await db.commit()

    new_status = ret.status
    if prev_status != new_status and new_status in ("returned", "awaiting_validation"):
        try:
            from services.stock_reservation_service import receive_customer_return
            await receive_customer_return(db, ret)
        except Exception as exc:
            logger.warning("receive_customer_return return=%s: %s", ret.id, exc)

    return {"ok": True, "status": ret.status}


@router.post("/{return_id}/upload-photo")
async def upload_return_photo(
    return_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    filename = f"{_uuid.uuid4().hex}.{ext}"
    os.makedirs("static/uploads/returns", exist_ok=True)
    with open(f"static/uploads/returns/{filename}", "wb") as f:
        f.write(await file.read())
    return {"url": f"/static/uploads/returns/{filename}"}


@router.post("/{return_id}/validate")
async def validate_return_endpoint(
    return_id: int,
    body: dict,
    current_user: User = Depends(require_menu_permission("devolucoes")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolução não encontrada")
    if ret.status != "awaiting_validation":
        raise HTTPException(
            status_code=400,
            detail=f"Devolução não está em aguardando validação (status atual: {ret.status})",
        )

    approved = body.get("approved", False)
    ret.status = "validated_ok" if approved else "validated_unfit"
    ret.validation_notes = body.get("notes")
    ret.validated_by = current_user.id
    ret.validated_at = datetime.now(UTC)
    if body.get("photos"):
        ret.validation_photos_json = json.dumps(body["photos"])

    try:
        if ret.devolution_invoice_id:
            # NF-e-driven: usa a QTD da NF-e de devolução (devolução parcial).
            from models.fiscal import Invoice, InvoiceItem
            from routers.invoices import _check_cmig_access
            from services.stock_reservation_service import validate_return_items

            inv = (
                await db.execute(
                    select(Invoice).where(Invoice.id == ret.devolution_invoice_id)
                )
            ).scalar_one_or_none()
            if inv:
                # Escopo: só valida devolução de CMIG acessível ao usuário (403 se não).
                await _check_cmig_access(inv.cmig_id, current_user, db)
            inv_items = (
                await db.execute(
                    select(InvoiceItem).where(InvoiceItem.invoice_id == ret.devolution_invoice_id)
                )
            ).scalars().all()
            await validate_return_items(db, ret, inv_items, approved, current_user.id)
            if not approved:
                # Não apto → nota de descarte (sem SEFAFZ, sem efeito no estoque vendável).
                discard = await _create_discard_note(db, ret, inv_items, current_user.id)
                if discard:
                    ret.discard_invoice_id = discard.id
            await db.commit()
        else:
            from services.stock_reservation_service import validate_return
            await validate_return(db, ret, approved, current_user.id)  # commita internamente
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("validate_return return=%s: %s", ret.id, exc)
        raise HTTPException(status_code=500, detail=f"Falha ao validar devolução: {exc}")

    return {"ok": True, "status": ret.status, "discard_invoice_id": ret.discard_invoice_id}


def _serialize(r: Return) -> dict:
    return {
        "id": r.id,
        "order_id": r.order_id,
        "reason": r.reason,
        "description": r.description,
        "tracking_code": r.tracking_code,
        "tracking_url": r.tracking_url,
        "carrier": r.carrier,
        "status": r.status,
        "return_type": r.return_type,
        "supplier_notes": r.supplier_notes,
        "credit_amount": float(r.credit_amount) if r.credit_amount else None,
        "validation_notes": r.validation_notes,
        "validated_by": r.validated_by,
        "validated_at": r.validated_at.isoformat() if r.validated_at else None,
        "validation_photos_json": r.validation_photos_json,
        "devolution_invoice_id": r.devolution_invoice_id,
        "discard_invoice_id": r.discard_invoice_id,
        "referenced_access_key": r.referenced_access_key,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ─── Devolução NF-e-driven (Fase B) ──────────────────────────────────────────


async def _create_discard_note(db, ret, inv_items, user_id):
    """Nota de descarte (sem SEFAFZ) p/ devolução não apta. Documento puramente
    fiscal, SEM efeito no estoque vendável: stock_updated=False faz o recompute
    event-sourced (que filtra Invoice.stock_updated==True) ignorá-la por completo.
    A baixa do não-apto já ocorre via unfit_quantity (UPDATE direto)."""
    from decimal import Decimal

    from models.fiscal import Invoice, InvoiceItem

    dev = (
        await db.execute(select(Invoice).where(Invoice.id == ret.devolution_invoice_id))
    ).scalar_one_or_none()
    if not dev:
        return None
    note = Invoice(
        cmig_id=dev.cmig_id,
        direction="out",
        purpose="ajuste",
        natureza_operacao="Descarte de mercadoria avariada (devolução não apta)",
        status="finalized",
        inbound_source="manual",
        issue_date=datetime.now(UTC),
        stock_updated=False,  # inerte ao recompute (filtro é stock_updated==True)
        focus_message="Descarte sem transmissão à SEFAFZ",
        created_by_user_id=user_id,
        total_products=dev.total_products or Decimal("0"),
        total_invoice=dev.total_invoice or Decimal("0"),
    )
    db.add(note)
    await db.flush()
    for it in inv_items:
        db.add(
            InvoiceItem(
                invoice_id=note.id,
                item_number=it.item_number or 1,
                description=it.description,
                sku=it.sku,
                ean=it.ean,
                unit=it.unit or "UN",
                quantity=it.quantity,
                unit_value=it.unit_value or Decimal("0"),
                total_value=it.total_value or Decimal("0"),
            )  # SEM source_type/FK → recompute ignora (sem efeito de estoque)
        )
    return note


async def _ingest_devolution(db, cmig, parsed: dict, dropshipper_id: int) -> dict:
    """Cria a Invoice de devolução (itens casados) + o Return vinculado e recebe a
    devolução (pending_validation pela QTD da NF-e). Casa o pedido via refNFe.
    `cmig` é o objeto CMIG já validado para o usuário."""
    from decimal import Decimal

    from models.fiscal import Invoice
    from models.order import Order
    from routers.invoices import (
        _invoice_item_from_parsed,
        _normalize_cnpj,
        _resolve_item_match,
        _upsert_recipient,
    )
    from services.stock_reservation_service import receive_return_items

    cmig_id = cmig.id
    access_key = parsed.get("access_key") or ""
    if len(access_key) != 44:
        raise HTTPException(status_code=422, detail="Chave de acesso inválida ou ausente no XML")
    if (await db.execute(select(Invoice.id).where(Invoice.access_key == access_key))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="NF-e de devolução já importada")

    items_data = parsed.get("items", [])
    first_cfop = next((str(i.get("cfop") or "") for i in items_data if i.get("cfop")), "")
    direction = "in" if first_cfop[:1] in ("1", "2", "3") else "out"
    # A CMIG é a contraparte do `party`: na devolução de cliente (in) a CMIG é o
    # destinatário; na saída (out) a CMIG é o emitente. Valida que o XML pertence
    # mesmo à CMIG selecionada (paridade com /invoices/import-xml-saida).
    cmig_block = (parsed.get("dest") or {}) if direction == "in" else (parsed.get("emit") or {})
    cmig_doc = _normalize_cnpj(cmig_block.get("document", ""))
    cmig_cnpj = _normalize_cnpj(cmig.cnpj)
    if cmig_doc and cmig_cnpj and cmig_doc != cmig_cnpj:
        raise HTTPException(
            status_code=422,
            detail=f"NF-e referente ao CNPJ {cmig_doc}, mas a CMIG selecionada é {cmig_cnpj}",
        )

    party = (parsed.get("emit") or {}) if direction == "in" else (parsed.get("dest") or {})
    person = await _upsert_recipient(party, cmig_id, db)
    totals = parsed.get("totals", {})

    inv = Invoice(
        cmig_id=cmig_id,
        direction=direction,
        purpose="devolucao",
        model=parsed.get("model") or "55",
        serie=parsed.get("serie"),
        nfe_number=parsed.get("nfe_number"),
        access_key=access_key,
        person_id=person.id,
        natureza_operacao=parsed.get("natureza_operacao") or "Devolução",
        issue_date=parsed.get("issue_date"),
        exit_date=parsed.get("exit_date"),
        status="authorized",
        inbound_source="xml_upload",
        manifestation="not_required",
        # Fonte canônica da movimentação é o Return (pending_validation → apto/unfit,
        # UPDATE direto). stock_updated=False mantém esta NF-e inerte ao recompute
        # event-sourced — senão a devolução apta seria contada em dobro (nfe_in +
        # UPDATE direto), e a entrada apareceria ANTES da inspeção (fura o portão).
        stock_updated=False,
        total_products=totals.get("total_products") or Decimal("0"),
        total_invoice=totals.get("total_invoice") or Decimal("0"),
        created_by_user_id=dropshipper_id,
    )
    db.add(inv)
    await db.flush()
    items = []
    for it in items_data:
        item = _invoice_item_from_parsed(inv.id, it)
        db.add(item)
        await db.flush()
        await _resolve_item_match(item, cmig_id, db)
        items.append(item)

    # Casa o pedido original pela NF-e referenciada (refNFe → Order.nfe_key).
    order_id = None
    ref_key = None
    for rk in parsed.get("referenced_keys") or []:
        o = (
            await db.execute(
                select(Order.id).where(Order.cmig_id == cmig_id, Order.nfe_key == rk)
            )
        ).scalar_one_or_none()
        ref_key = ref_key or rk
        if o:
            order_id = o
            break

    matched_items = [i for i in items if i.catalog_product_id or i.cmig_product_id]
    ret = Return(
        dropshipper_id=dropshipper_id,
        order_id=order_id,
        return_type="customer_nfe",
        reason="devolucao_nfe",
        status="awaiting_validation" if matched_items else "unlinked",
        devolution_invoice_id=inv.id,
        referenced_access_key=ref_key,
    )
    db.add(ret)
    await db.flush()
    try:
        received = await receive_return_items(db, ret, items)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("ingest_devolution access_key=%s: %s", access_key, exc)
        raise HTTPException(status_code=500, detail=f"Falha ao registrar devolução: {exc}")
    return {
        "return_id": ret.id,
        "invoice_id": inv.id,
        "status": ret.status,
        "order_id": order_id,
        "items_matched": len(matched_items),
        "items_total": len(items),
        "received_qty": received,
    }


@router.post("/import-xml", status_code=201)
async def import_devolution_xml(
    cmig_id: int = Form(...),
    xml_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("devolucoes")),
):
    """Importa um XML de NF-e de devolução: cria a devolução (pending_validation) p/
    o operador marcar apto/não apto. Casa o pedido original via NF-e referenciada."""
    from routers.invoices import _check_cmig_access
    from services.fiscal.nfe_xml_parser import parse_nfe_xml

    cmig = await _check_cmig_access(cmig_id, current_user, db)  # 403/404 se sem acesso

    if (xml_file.content_type or "") not in ("text/xml", "application/xml", "application/octet-stream", ""):
        raise HTTPException(status_code=422, detail="Arquivo deve ser um XML")
    content = await xml_file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo XML vazio")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="XML excede o tamanho máximo (5 MB)")
    try:
        parsed = parse_nfe_xml(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return await _ingest_devolution(db, cmig, parsed, current_user.id)

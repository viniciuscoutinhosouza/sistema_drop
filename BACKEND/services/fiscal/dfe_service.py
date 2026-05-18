"""Orquestra a coleta de NFes recebidas via DFe (Focus NFe → SEFAZ-RS).

Fluxo:
1. `sync_received_for_cmig` lista as NFes do CNPJ via Focus, dedup por chave,
   baixa o XML completo das novas, parseia e cria Invoice de entrada.
2. `process_received_nfe` é o entrypoint do webhook (1 chave por vez).
3. `update_stock_from_invoice` movimenta estoque CMIG por EAN.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from database import task_db
from models.cmig import CMIG, CMIGProduct
from models.fiscal import CMIGFiscalConfig, Invoice, InvoiceItem
from models.notification import Notification
from models.person import Person
from services.fiscal import focus_service
from services.fiscal.nfe_xml_parser import parse_nfe_xml

log = logging.getLogger(__name__)


async def sync_all() -> dict:
    """Sincroniza NFes recebidas para todas CMIGs com Focus configurado.
    Retorna estatísticas agregadas."""
    stats = {"cmigs": 0, "new": 0, "skipped": 0, "errors": 0}
    async with task_db() as db:
        cfgs = (
            (
                await db.execute(
                    select(CMIGFiscalConfig).where(
                        CMIGFiscalConfig.focus_company_token.is_not(None)
                    )
                )
            )
            .scalars()
            .all()
        )

    for cfg in cfgs:
        try:
            r = await sync_received_for_cmig(cfg.cmig_id)
            stats["cmigs"] += 1
            stats["new"] += r.get("new", 0)
            stats["skipped"] += r.get("skipped", 0)
        except Exception as e:
            log.exception("DFe sync falhou para CMIG %s: %s", cfg.cmig_id, e)
            stats["errors"] += 1
    return stats


async def sync_received_for_cmig(cmig_id: int) -> dict:
    """Sincroniza NFes recebidas para uma CMIG específica.
    Cria Invoices novas para chaves que ainda não existem."""
    async with task_db() as db:
        cfg = (
            await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
        ).scalar_one_or_none()
        if not cfg or not cfg.focus_company_token:
            raise ValueError("CMIG sem configuração Focus NFe")

        cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one()

        # Listar resumos via Focus
        try:
            documentos = await focus_service.list_received(cfg, cmig.cnpj)
        except focus_service.FocusError as e:
            raise ValueError(f"Focus NFe: {e.message}")

        new_count = 0
        skipped = 0
        errors: list[str] = []

        for doc in documentos:
            chave = doc.get("chave_nfe") or doc.get("chave") or ""
            if not chave or len(chave) != 44:
                continue
            # Dedup: se já existe Invoice com essa access_key, pula
            existing = (
                await db.execute(select(Invoice.id).where(Invoice.access_key == chave))
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            try:
                await _create_invoice_from_received(db, cfg, cmig, chave)
                new_count += 1
            except Exception as e:
                log.exception("Erro ao processar chave %s: %s", chave, e)
                errors.append(f"{chave[:20]}…: {e}")

        await db.commit()

    return {"new": new_count, "skipped": skipped, "errors": errors}


async def process_received_nfe(cmig_id: int, chave: str) -> Invoice | None:
    """Entrypoint do webhook — processa 1 chave."""
    async with task_db() as db:
        # Dedup
        existing = (
            await db.execute(select(Invoice).where(Invoice.access_key == chave))
        ).scalar_one_or_none()
        if existing:
            return existing

        cfg = (
            await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
        ).scalar_one_or_none()
        if not cfg or not cfg.focus_company_token:
            raise ValueError("CMIG sem configuração Focus NFe")

        cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one()
        inv = await _create_invoice_from_received(db, cfg, cmig, chave)
        await db.commit()
        return inv


async def _create_invoice_from_received(
    db, cfg: CMIGFiscalConfig, cmig: CMIG, chave: str
) -> Invoice:
    """Baixa XML, parseia e cria Invoice (direction='in', source='dfe_focus')."""
    try:
        xml_bytes = await focus_service.download_received_xml(cfg, chave)
    except focus_service.FocusError as e:
        raise RuntimeError(f"Falha ao baixar XML: {e.message}")

    parsed = parse_nfe_xml(xml_bytes)

    # Upsert fornecedor
    supplier = await _upsert_supplier_from_parsed(db, parsed["emit"], cmig.id)

    totals = parsed.get("totals", {})
    transport = parsed.get("transport", {})

    inv = Invoice(
        cmig_id=cmig.id,
        direction="in",
        purpose="venda",
        model=parsed.get("model") or "55",
        serie=parsed.get("serie"),
        nfe_number=parsed.get("nfe_number"),
        access_key=chave,
        person_id=supplier.id,
        natureza_operacao=parsed.get("natureza_operacao") or "Compra para revenda",
        issue_date=parsed.get("issue_date"),
        exit_date=parsed.get("exit_date"),
        status="authorized",
        inbound_source="dfe_focus",
        manifestation="pending",
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
    )
    db.add(inv)
    await db.flush()

    for it_data in parsed.get("items", []):
        db.add(
            InvoiceItem(
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
        )

    # Notification para o AC owner
    try:
        db.add(
            Notification(
                dropshipper_id=cmig.owner_ac_id,
                title="Nova NFe recebida",
                body=f"Fornecedor: {supplier.name} — Total R$ {inv.total_invoice} — Manifestação pendente",
                reference_type="invoice",
                reference_id=inv.id,
                type="fiscal",
            )
        )
    except Exception:
        # Defensivo — não derruba o sync se Notification falhar
        pass

    await db.flush()
    return inv


async def _upsert_supplier_from_parsed(db, emit_data: dict, cmig_id: int) -> Person:
    """Cria ou atualiza Person (fornecedor) a partir dos dados do XML."""
    document = emit_data.get("document") or ""
    if not document:
        raise ValueError("XML sem documento do emitente")

    existing = (
        await db.execute(
            select(Person).where(and_(Person.cmig_id == cmig_id, Person.document == document))
        )
    ).scalar_one_or_none()

    if existing:
        if not existing.is_supplier:
            existing.is_supplier = True
        if not existing.ie and emit_data.get("ie"):
            existing.ie = emit_data["ie"]
        return existing

    p = Person(
        cmig_id=cmig_id,
        person_type=emit_data.get("person_type") or "PJ",
        document=document,
        ie=emit_data.get("ie") or None,
        ie_isento=False,
        im=emit_data.get("im") or None,
        name=emit_data.get("name") or "(Sem nome)",
        trade_name=emit_data.get("trade_name") or None,
        phone=emit_data.get("phone") or None,
        zip_code=emit_data.get("zip_code") or None,
        street=emit_data.get("street") or None,
        address_number=emit_data.get("address_number") or None,
        complement=emit_data.get("complement") or None,
        neighborhood=emit_data.get("neighborhood") or None,
        city=emit_data.get("city") or None,
        state=emit_data.get("state") or None,
        ibge_code=emit_data.get("ibge_code") or None,
        country_code=emit_data.get("country_code") or "1058",
        is_customer=False,
        is_supplier=True,
        is_carrier=False,
        is_active=True,
    )
    db.add(p)
    await db.flush()
    return p


async def update_stock_from_invoice(invoice_id: int) -> dict:
    """Após manifestação/autorização de NFe (entrada), recalcula estoque dos
    produtos afetados via modelo canônico (event-sourced). Marca
    `stock_updated=True` pra rastrear que essa NFe já passou."""
    from services.fiscal.stock_calculator import recompute_after_invoice_change

    async with task_db() as db:
        inv = (
            await db.execute(
                select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
            )
        ).scalar_one_or_none()
        if not inv:
            raise ValueError("Invoice não encontrada")
        if inv.direction != "in":
            raise ValueError("Apenas entradas podem mover estoque")
        if inv.stock_updated:
            return {
                "cmig_recomputed": 0,
                "pg_recomputed": 0,
                "already_updated": True,
            }

        result = await recompute_after_invoice_change(inv, db)
        inv.stock_updated = True
        await db.commit()
        return {**result, "already_updated": False}

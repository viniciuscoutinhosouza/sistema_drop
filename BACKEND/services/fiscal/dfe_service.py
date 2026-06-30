"""Orquestra a coleta de NFes recebidas via Distribuição de DFe (SEFAZ — Ambiente Nacional).

Fluxo (emissão/recebimento próprios, sem Focus):
1. `sync_received_for_cmig` consulta a Distribuição de DFe a partir do último NSU,
   dedup por chave, parseia o XML completo (docZip) e cria Invoice de entrada.
2. `update_stock_from_invoice` movimenta estoque CMIG por EAN.

Rate-limit (regra do AN): quando ultNSU==maxNSU não há novos; cStat 656 = consumo
indevido → aguardar ~1h. O `ultimo_nsu` é persistido por CMIG em CMIGFiscalConfig.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from config import get_settings
from database import task_db
from models.cmig import CMIG
from models.fiscal import CMIGFiscalConfig, DFeRecebido, DFeSyncLog, Invoice, InvoiceItem
from models.notification import Notification
from models.person import Person
from services.fiscal import sefaz_service
from services.fiscal.nfe_xml_parser import parse_nfe_xml
from services.fiscal.sefaz import distribuicao
from services.fiscal.sefaz.xml_builder import codigo_uf

log = logging.getLogger(__name__)

_MAX_BATCHES_PER_RUN = 20  # bound do loop ultNSU→maxNSU por execução
_RE_CHAVE = re.compile(r"(\d{44})")

# Limiar de erros consecutivos antes de emitir alerta via Socket.io
_MAX_CONSECUTIVE_ERRORS = 3


async def sync_all() -> dict:
    """Sincroniza NFes recebidas para todas CMIGs com Focus configurado.

    Falhas isoladas por CMIG são registradas em dfe_sync_log e não interrompem
    as demais CMIGs. Após _MAX_CONSECUTIVE_ERRORS falhas seguidas, emite alerta
    via Socket.io para o AC proprietário.
    """
    stats = {"cmigs": 0, "new": 0, "skipped": 0, "errors": 0}
    async with task_db() as db:
        cfgs = (
            (
                await db.execute(
                    select(CMIGFiscalConfig).where(CMIGFiscalConfig.cert_path.is_not(None))
                )
            )
            .scalars()
            .all()
        )

    for cfg in cfgs:
        log_entry = DFeSyncLog(cmig_id=cfg.cmig_id, status="running")
        try:
            r = await sync_received_for_cmig(cfg.cmig_id)
            stats["cmigs"] += 1
            stats["new"] += r.get("new", 0)
            stats["skipped"] += r.get("skipped", 0)

            log_entry.status = "ok"
            log_entry.invoices_created = r.get("new", 0)
            log_entry.invoices_skipped = r.get("skipped", 0)
            log_entry.errors_count = len(r.get("errors", []))
            log_entry.consecutive_errors = 0
        except Exception as exc:
            log.exception("DFe sync falhou para CMIG %s: %s", cfg.cmig_id, exc)
            stats["errors"] += 1
            log_entry.status = "error"
            log_entry.error_detail = str(exc)[:4000]
            log_entry.errors_count = 1

            # Conta erros consecutivos desta CMIG para alertar
            log_entry.consecutive_errors = await _count_consecutive_errors(cfg.cmig_id)
            if log_entry.consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                await _emit_dfe_error_alert(cfg.cmig_id, str(exc))
        finally:
            log_entry.finished_at = datetime.utcnow()
            async with task_db() as db:
                db.add(log_entry)
                await db.commit()

    return stats


async def _count_consecutive_errors(cmig_id: int) -> int:
    """Retorna quantos erros consecutivos esta CMIG teve nos últimos registros."""
    async with task_db() as db:
        rows = (
            await db.execute(
                select(DFeSyncLog.status)
                .where(DFeSyncLog.cmig_id == cmig_id)
                .order_by(DFeSyncLog.started_at.desc())
                .limit(10)
            )
        ).scalars().all()

    count = 0
    for status in rows:
        if status == "error":
            count += 1
        else:
            break
    return count + 1  # inclui o erro atual


async def _emit_dfe_error_alert(cmig_id: int, error: str) -> None:
    """Emite alerta Socket.io para AC proprietário da CMIG."""
    try:
        from socket_manager import sio
        await sio.emit(
            "dfe_sync_error",
            {
                "cmig_id": cmig_id,
                "message": f"DFe sync falhou {_MAX_CONSECUTIVE_ERRORS}× consecutivas. Verifique o certificado A1 / credenciamento.",
                "error": error[:500],
            },
            room=f"cmig_{cmig_id}",
        )
    except Exception:
        pass  # alerta via socket é melhor-esforço


async def sync_received_for_cmig(cmig_id: int) -> dict:
    """Consulta a Distribuição de DFe da CMIG (loop ultNSU→maxNSU, bounded) e cria
    Invoices de entrada para NF-e completas novas. Persiste o último NSU processado."""
    async with task_db() as db:
        cfg = (
            await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id))
        ).scalar_one_or_none()
        if not cfg or not cfg.cert_path:
            raise ValueError("CMIG sem certificado A1 configurado (emissão própria)")
        cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one()
        if not cmig.cnpj or not cmig.state:
            raise ValueError("CMIG sem CNPJ/UF para a Distribuição de DFe")

        pfx_path, senha = sefaz_service.resolve_cert(cfg)
        settings = get_settings()
        ambiente = sefaz_service._AMB.get(cfg.environment or "homolog", "homologacao")
        cnpj = re.sub(r"\D", "", cmig.cnpj)
        c_uf = codigo_uf(cmig.state.upper())

        new_count = 0
        skipped = 0
        errors: list[str] = []
        ult = cfg.ultimo_nsu or "0"

        for _ in range(_MAX_BATCHES_PER_RUN):
            ret = await asyncio.to_thread(
                distribuicao.consultar_dfe,
                cnpj=cnpj, c_uf=c_uf, ambiente=ambiente, ult_nsu=ult,
                pfx_path=pfx_path, pfx_password=senha,
                timeout=int(settings.NFE_SEFAZ_TIMEOUT),
                verify_ssl=sefaz_service._verify_ssl(cfg.environment or "homolog"),
                runtime_dir=str(Path(settings.NFE_CERTS_DIR) / "runtime"),
            )
            if ret.cstat == distribuicao.CSTAT_CONSUMO_INDEVIDO:
                errors.append("consumo indevido (656) — aguardando janela de ~1h")
                break
            if ret.cstat not in (distribuicao.CSTAT_DOCS_ENCONTRADOS, distribuicao.CSTAT_NENHUM_DOC):
                errors.append(f"cStat {ret.cstat}: {ret.motivo}")
                break

            for doc in ret.docs:
                try:
                    r = await _process_dfe_doc(db, cmig, doc)
                    if r == "new":
                        new_count += 1
                    elif r == "skip":
                        skipped += 1
                except Exception as e:  # noqa: BLE001
                    log.exception("Erro ao processar docZip NSU %s: %s", doc.nsu, e)
                    errors.append(f"NSU {doc.nsu}: {e}")

            ult = ret.ult_nsu or ult
            cfg.ultimo_nsu = ult
            await db.commit()
            if not ret.docs or not ret.tem_mais:
                break

    return {"new": new_count, "skipped": skipped, "errors": errors}


def _extract_chave(xml: str) -> str | None:
    m = _RE_CHAVE.search(xml)
    return m.group(1) if m else None


async def _process_dfe_doc(db, cmig: CMIG, doc) -> str:
    """Trata um docZip: registra em dfe_recebidos; cria Invoice se for NF-e completa nova.

    Retorna 'new' | 'skip' | 'event'."""
    chave = _extract_chave(doc.xml)
    # Dedup do NSU
    exists_nsu = (
        await db.execute(
            select(DFeRecebido.id).where(
                and_(DFeRecebido.cmig_id == cmig.id, DFeRecebido.nsu == doc.nsu)
            )
        )
    ).scalar_one_or_none()
    if not exists_nsu:
        db.add(DFeRecebido(
            cmig_id=cmig.id, nsu=doc.nsu, chave=chave, schema_dfe=doc.schema,
            resumo_json=doc.xml if doc.is_resumo_nfe else None,
            xml=doc.xml if doc.is_nfe_completa else None,
        ))
    if doc.is_evento or doc.is_resumo_nfe or not doc.is_nfe_completa:
        return "event"
    if not chave:
        return "event"
    # Dedup do Invoice por chave
    existing = (
        await db.execute(select(Invoice.id).where(Invoice.access_key == chave))
    ).scalar_one_or_none()
    if existing:
        return "skip"
    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig.id))
    ).scalar_one_or_none()
    await _create_invoice_from_xml(db, cfg, cmig, chave, doc.xml.encode("utf-8"))
    return "new"


async def _create_invoice_from_xml(
    db, cfg: CMIGFiscalConfig, cmig: CMIG, chave: str, xml_bytes: bytes
) -> Invoice:
    """Parseia o XML completo e cria Invoice (direction='in', source='dfe_focus')."""
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
        # NF-e simbólica não movimenta estoque (não seta stock_updated).
        from services.fiscal.fiscal_rules import is_simbolica

        if is_simbolica(inv.natureza_operacao):
            return {"cmig_recomputed": 0, "pg_recomputed": 0, "simbolica": True}

        result = await recompute_after_invoice_change(inv, db)
        inv.stock_updated = True
        await db.commit()
        # Se a NF-e de entrada veio de um CNPJ FULL, debita o full_stock
        try:
            from models.person import Person as _Person
            from services.full_stock_service import apply_nfe_entrada_from_full, is_full_cnpj
            _person = (await db.execute(select(_Person).where(_Person.id == inv.person_id))).scalar_one_or_none()
            if _person and _person.document:
                _full_cnpj = await is_full_cnpj(db, _person.document, inv.cmig_id)
                if _full_cnpj:
                    await apply_nfe_entrada_from_full(db, inv, _full_cnpj.marketplace_account_id)
                    await db.commit()
        except Exception:
            log.exception("update_stock_from_invoice: erro ao processar full_stock para invoice %s", inv.id)
        try:
            from services.stock_sync_service import schedule_push
            schedule_push(result.get("cmig_ids", set()), result.get("pg_ids", set()))
        except Exception:
            pass
        return {k: v for k, v in result.items() if k not in ("cmig_ids", "pg_ids")} | {"already_updated": False}

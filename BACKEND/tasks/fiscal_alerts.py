"""Job APScheduler — alertas fiscais.

Roda diariamente às 09:00:
1. Certificados A1 que expiram em ≤ 30 dias → cria Notification para AC owner
2. Invoices em status 'queued'/'processing' há > 1h → reconsulta Focus
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, select

from database import task_db
from models.cmig import CMIG
from models.fiscal import CMIGFiscalConfig, Invoice
from models.notification import Notification
from services.fiscal import focus_service

log = logging.getLogger(__name__)


async def run_fiscal_alerts():
    stats = {"cert_alerts": 0, "stale_invoices": 0, "errors": 0}

    async with task_db() as db:
        await _check_expiring_certificates(db, stats)

    async with task_db() as db:
        await _refresh_stale_invoices(db, stats)

    log.info(
        "Fiscal alerts: %d alertas de cert, %d invoices reconsultadas, %d erros",
        stats["cert_alerts"],
        stats["stale_invoices"],
        stats["errors"],
    )
    return stats


async def _check_expiring_certificates(db, stats: dict):
    """Notifica owners de CMIGs cujos certificados expiram em ≤ 30 dias."""
    now = datetime.utcnow()
    threshold = now + timedelta(days=30)

    cfgs = (
        (
            await db.execute(
                select(CMIGFiscalConfig).where(
                    and_(
                        CMIGFiscalConfig.certificate_expires_at.is_not(None),
                        CMIGFiscalConfig.certificate_expires_at <= threshold,
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    for cfg in cfgs:
        cmig = (await db.execute(select(CMIG).where(CMIG.id == cfg.cmig_id))).scalar_one_or_none()
        if not cmig:
            continue

        days_left = (cfg.certificate_expires_at - now).days
        is_expired = days_left < 0

        # Dedup: já existe alerta para este cert (mesmo dia)?
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        existing = (
            await db.execute(
                select(Notification).where(
                    and_(
                        Notification.dropshipper_id == cmig.owner_ac_id,
                        Notification.reference_type == "cert_expiring",
                        Notification.reference_id == cfg.id,
                        Notification.created_at >= today_start,
                    )
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue

        if is_expired:
            title = f"Certificado A1 VENCIDO — {cmig.company_name}"
            body = (
                f"O certificado digital da CMIG {cmig.company_name} venceu há "
                f"{abs(days_left)} dia(s). NFes não poderão ser emitidas até a renovação."
            )
        else:
            title = f"Certificado A1 expira em {days_left} dia(s) — {cmig.company_name}"
            body = (
                f"O certificado digital da CMIG {cmig.company_name} expira em "
                f"{cfg.certificate_expires_at.strftime('%d/%m/%Y')}. Renove para evitar interrupções."
            )

        try:
            db.add(
                Notification(
                    dropshipper_id=cmig.owner_ac_id,
                    title=title,
                    body=body,
                    reference_type="cert_expiring",
                    reference_id=cfg.id,
                    type="fiscal",
                )
            )
            stats["cert_alerts"] += 1
        except Exception as e:
            log.exception("Erro criando notification cert: %s", e)
            stats["errors"] += 1

    await db.commit()


async def _refresh_stale_invoices(db, stats: dict):
    """Para invoices em queued/processing há > 1h, reconsulta Focus."""
    cutoff = datetime.utcnow() - timedelta(hours=1)

    stale = (
        (
            await db.execute(
                select(Invoice).where(
                    and_(
                        Invoice.status.in_(("queued", "processing")),
                        Invoice.focus_ref.is_not(None),
                        Invoice.updated_at <= cutoff,
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    for inv in stale:
        cfg = (
            await db.execute(
                select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == inv.cmig_id)
            )
        ).scalar_one_or_none()
        if not cfg or not cfg.focus_company_token:
            continue

        try:
            result = await focus_service.consult_nfe(cfg, inv.focus_ref)
        except focus_service.FocusError as e:
            log.warning("Falha consultando NFe %s: %s", inv.focus_ref, e.message)
            stats["errors"] += 1
            continue

        focus_status = result.get("status")
        inv.focus_status = focus_status or inv.focus_status
        inv.focus_message = result.get("mensagem_sefaz") or result.get("mensagem")

        if focus_status == "autorizado":
            inv.status = "authorized"
            inv.access_key = result.get("chave_nfe") or inv.access_key
            if result.get("numero"):
                try:
                    inv.nfe_number = int(result["numero"])
                except (ValueError, TypeError):
                    pass
            if result.get("serie"):
                try:
                    inv.serie = int(result["serie"])
                except (ValueError, TypeError):
                    pass
            inv.xml_url = focus_service.absolutize_focus_url(
                cfg, result.get("caminho_xml_nota_fiscal") or ""
            )
            inv.danfe_url = focus_service.absolutize_focus_url(
                cfg, result.get("caminho_danfe") or ""
            )
        elif focus_status == "cancelado":
            inv.status = "cancelled"
        elif focus_status == "denegado":
            inv.status = "denied"
        elif focus_status == "erro_autorizacao":
            inv.status = "rejected"
        stats["stale_invoices"] += 1

    await db.commit()

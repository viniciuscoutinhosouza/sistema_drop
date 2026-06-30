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
from tasks._job_wrapper import tracked_job

log = logging.getLogger(__name__)


async def run_fiscal_alerts():
    async with tracked_job("fiscal_alerts") as result:
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
        result.set(stats)
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
    """Para notas próprias presas em 'processing' há > 1h, consulta a SEFAZ pela
    chave (regra N-6) e finaliza o status — recupera transmissões interrompidas."""
    from models.cmig import CMIG
    from services.fiscal import sefaz_service
    from services.fiscal.sefaz.exceptions import FiscalError, SefazError

    cutoff = datetime.utcnow() - timedelta(hours=1)
    stale = (
        (
            await db.execute(
                select(Invoice).where(
                    and_(
                        Invoice.status.in_(("queued", "processing")),
                        Invoice.emission_provider == "sefaz",
                        Invoice.access_key.is_not(None),
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
        if not cfg or not cfg.cert_path:
            continue
        cmig = (await db.execute(select(CMIG).where(CMIG.id == inv.cmig_id))).scalar_one_or_none()
        if not cmig:
            continue
        try:
            await sefaz_service.consultar(db, inv, cmig, cfg)  # já dá commit + atualiza status
            stats["stale_invoices"] += 1
        except (sefaz_service.SefazServiceError, SefazError, FiscalError) as e:
            log.warning("Falha consultando NFe %s na SEFAZ: %s", inv.access_key, e)
            stats["errors"] += 1
            continue

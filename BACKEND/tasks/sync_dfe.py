"""Job APScheduler — sincroniza NFes recebidas (DFe) de todas as CMIGs ativas.

Roda como backup do webhook do Focus NFe. Executa a cada 30 minutos.
"""

import logging

from services.fiscal import dfe_service
from tasks._job_wrapper import tracked_job

log = logging.getLogger(__name__)


async def sync_all_dfe():
    """Sincroniza NFes recebidas (DFe) para todas as CMIGs com Focus configurado."""
    async with tracked_job("sync_dfe") as result:
        try:
            stats = await dfe_service.sync_all()
            log.info(
                "DFe sync: %d CMIGs, %d novas NFes, %d puladas, %d erros",
                stats.get("cmigs", 0),
                stats.get("new", 0),
                stats.get("skipped", 0),
                stats.get("errors", 0),
            )
            result.set(
                {
                    "cmigs_processed": stats.get("cmigs", 0),
                    "dfes_new": stats.get("new", 0),
                    "dfes_skipped": stats.get("skipped", 0),
                    "errors": stats.get("errors", 0),
                }
            )
            return stats
        except Exception as e:
            log.exception("Erro fatal no DFe sync: %s", e)
            result.set({"error": str(e)})
            raise

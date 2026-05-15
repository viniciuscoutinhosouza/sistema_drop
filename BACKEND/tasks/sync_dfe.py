"""Job APScheduler — sincroniza NFes recebidas (DFe) de todas as CMIGs ativas.

Roda como backup do webhook do Focus NFe. Executa a cada 30 minutos.
"""

import logging

from services.fiscal import dfe_service

log = logging.getLogger(__name__)


async def sync_all_dfe():
    """Sincroniza NFes recebidas (DFe) para todas as CMIGs com Focus configurado."""
    try:
        stats = await dfe_service.sync_all()
        log.info(
            "DFe sync: %d CMIGs, %d novas NFes, %d puladas, %d erros",
            stats.get("cmigs", 0),
            stats.get("new", 0),
            stats.get("skipped", 0),
            stats.get("errors", 0),
        )
        return stats
    except Exception as e:
        log.exception("Erro fatal no DFe sync: %s", e)
        return {"error": str(e)}

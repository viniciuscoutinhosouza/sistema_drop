"""Auditoria de ações destrutivas.

Uso: `await audit_service.record(db, current_user, "anuncio.delete", "product_listing", id, ...)`
imediatamente ANTES de apagar (o snapshot precisa do objeto ainda vivo). Não faz commit — a
transação é do chamador, para o registro morrer junto se a exclusão for revertida.
"""
import json
import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit import AuditEvent

logger = logging.getLogger(__name__)


async def record(
    db: AsyncSession,
    user,
    action: str,
    entity_type: str,
    entity_id,
    *,
    details: dict | None = None,
    request: Request | None = None,
) -> None:
    """Registra o evento. NUNCA levanta: auditoria quebrada não pode impedir a operação."""
    try:
        ip = None
        user_agent = None
        if request is not None:
            # X-Forwarded-For: atrás do nginx, o client.host é 127.0.0.1.
            fwd = request.headers.get("x-forwarded-for")
            ip = (fwd.split(",")[0].strip() if fwd else None) or (
                request.client.host if request.client else None
            )
            user_agent = (request.headers.get("user-agent") or "")[:400] or None

        db.add(
            AuditEvent(
                user_id=getattr(user, "id", None),
                user_email=getattr(user, "email", None),
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                details=json.dumps(details, ensure_ascii=False, default=str)[:32000]
                if details
                else None,
                ip=ip,
                user_agent=user_agent,
            )
        )
        # Log também: o banco pode ser restaurado, o log fica.
        logger.warning(
            "[AUDIT] %s %s=%s por user=%s (%s) ip=%s",
            action, entity_type, entity_id,
            getattr(user, "id", None), getattr(user, "email", None), ip,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[AUDIT] falha ao registrar %s %s: %s", action, entity_id, exc)

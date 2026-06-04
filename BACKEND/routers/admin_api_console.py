"""Console de API para administradores.

Página de testes que permite fazer requests diretas à API do Mercado Livre
usando o token válido da conta selecionada. Apenas role='admin' tem acesso.

Endpoint:
- POST /api/v1/admin/api-console/execute

Body:
  {
    "account_id": int,
    "method": "GET"|"POST"|"PUT"|"DELETE"|"PATCH",
    "path": "/users/me",            # backend prepende https://api.mercadolibre.com
    "query": {...} (opcional),
    "headers": {...} (opcional, extras — Authorization é auto-injetado),
    "body_json": ... (opcional, qualquer JSON serializável)
  }

Response:
  {
    "request_url": str,
    "status": int,
    "elapsed_ms": int,
    "response_headers": dict,
    "response_body": parsed_json | raw_text
  }
"""
import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_role
from models.integration import MarketplaceAccount
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

ML_BASE_URL = "https://api.mercadolibre.com"
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


@router.get("/accounts")
async def list_all_accounts_for_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Lista TODAS as contas de marketplace pro Console de API.

    Diferente do GET /accounts (filtra por co-administração do usuário),
    aqui o admin vê tudo — é o ponto de entrada da ferramenta de debug.
    """
    result = await db.execute(
        select(MarketplaceAccount).order_by(
            MarketplaceAccount.platform, MarketplaceAccount.created_at
        )
    )
    return [
        {
            "id": a.id,
            "platform": a.platform,
            "description": a.description,
            "platform_username": a.platform_username,
            "email": a.email,
            "requires_reauth": getattr(a, "requires_reauth", False),
            "cmig_id": getattr(a, "cmig_id", None),
        }
        for a in result.scalars().all()
    ]


@router.post("/execute")
async def execute_request(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Encaminha a request para a API do marketplace usando o token da conta."""
    # Import tardio para evitar import circular
    from routers.anuncios import _get_account_or_403, _get_valid_token

    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(status_code=422, detail="account_id é obrigatório")

    method = (body.get("method") or "").strip().upper()
    if method not in ALLOWED_METHODS:
        raise HTTPException(
            status_code=422,
            detail=f"method inválido. Aceitos: {', '.join(sorted(ALLOWED_METHODS))}",
        )

    path = (body.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=422, detail="path é obrigatório (ex: '/users/me')")
    if not path.startswith("/"):
        path = "/" + path

    query = body.get("query") or {}
    if not isinstance(query, dict):
        raise HTTPException(status_code=422, detail="query deve ser um objeto")

    extra_headers = body.get("headers") or {}
    if not isinstance(extra_headers, dict):
        raise HTTPException(status_code=422, detail="headers deve ser um objeto")

    # body_json pode ser dict, list, None ou primitivo — qualquer JSON
    body_json = body.get("body_json")

    # Resolve conta e token
    account = await _get_account_or_403(int(account_id), current_user, db)
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Plataforma '{account.platform}' ainda não suportada no Console de API. "
                "Por enquanto só Mercado Livre."
            ),
        )

    # Pode lançar 401 com mensagem amigável de invalid_grant — deixamos subir
    access_token = await _get_valid_token(account, db)

    # Monta headers — Authorization auto, depois extras (usuário não consegue
    # sobrescrever Authorization)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    for k, v in extra_headers.items():
        if not k:
            continue
        if k.lower() == "authorization":
            continue  # ignora — o backend é dono desse header
        headers[str(k)] = str(v)

    if body_json is not None and "Content-Type" not in headers and "content-type" not in headers:
        headers["Content-Type"] = "application/json"

    # Audit log — quem fez o quê
    logger.info(
        "[api-console] user=%s account=%s %s %s",
        current_user.id, account_id, method, path,
    )

    request_url = f"{ML_BASE_URL}{path}"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method=method,
                url=request_url,
                params=query if query else None,
                headers=headers,
                json=body_json if body_json is not None else None,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao chamar o marketplace: {exc.__class__.__name__}: {exc}",
        ) from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # Tenta interpretar JSON; fallback para texto
    try:
        response_body = resp.json()
    except Exception:
        response_body = resp.text

    # Filtra response_headers — alguns headers binários ficam estranhos no JSON
    response_headers = {k: v for k, v in resp.headers.items()}

    return {
        "request_url": str(resp.request.url),
        "status": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "response_headers": response_headers,
        "response_body": response_body,
    }

"""Cliente RPC do eShip.

A API do eShip não é REST: há um único endpoint e a operação vai no query param
`funcao`. A autenticação é por API Key no header `api`.

    POST {base_url}/?api&funcao=webServiceXxx
    Header: api: <apikey>
    Body:   JSON

Toda chamada externa ao eShip passa por aqui — nenhum router fala HTTP direto.
"""

import logging

import httpx

from .config import EShipConfig

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


class EShipError(Exception):
    """Falha de comunicação/negócio com o eShip."""


async def call(cfg: EShipConfig, funcao: str, payload: dict | None = None) -> dict:
    """Executa uma função RPC do eShip e retorna o JSON de resposta.

    Levanta EShipError se a config for inválida ou a chamada falhar.
    """
    if not cfg or not cfg.base_url or not cfg.api_key:
        raise EShipError("eShip não configurado (base_url/api_key ausentes) para este galpão.")

    base = cfg.base_url.rstrip("/")
    url = f"{base}/?api&funcao={funcao}"
    headers = {"api": cfg.api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload or {})
    except httpx.HTTPError as e:
        raise EShipError(f"Erro de rede ao chamar eShip {funcao}: {e}") from e

    if resp.status_code != 200:
        raise EShipError(f"eShip {funcao} respondeu {resp.status_code}: {resp.text[:300]}")

    try:
        return resp.json()
    except ValueError:
        # Algumas funções podem devolver texto puro.
        return {"raw": resp.text}

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
        data = resp.json()
    except ValueError:
        # Algumas funções podem devolver texto puro.
        return {"raw": resp.text}

    # O eShip responde HTTP 200 MESMO em erro de negócio, sinalizando no campo `erros`
    # (ex.: {"erros":[{"erro":{"mensagem":"...","codigo":"MAP0014"}}]}). Sem isto, uma
    # falha (função inexistente, payload inválido) era contada como sucesso.
    erros = data.get("erros") if isinstance(data, dict) else None
    if erros:  # None / [] / {} / "" são falsy → sucesso
        msg, cod = _extract_eship_error(erros)
        raise EShipError(f"eShip {funcao} retornou erro{f' {cod}' if cod else ''}: {msg}")
    return data


def _extract_eship_error(erros) -> tuple[str, str]:
    """Extrai (mensagem, codigo) do envelope `erros` do eShip, tolerante a formatos."""
    node = erros[0] if isinstance(erros, list) and erros else erros
    if isinstance(node, dict):
        e = node.get("erro") if isinstance(node.get("erro"), dict) else node
        return str(e.get("mensagem") or e.get("message") or e or "erro desconhecido"), str(e.get("codigo") or "")
    return str(node)[:200], ""

"""Consulta de CNPJ via BrasilAPI (gratuita, sem chave). Cache em memória 1h."""
import time
import re
import httpx
from typing import Optional

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SECONDS = 3600
_BASE_URL = "https://brasilapi.com.br/api/cnpj/v1"


def _clean_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


async def lookup_cnpj(cnpj: str, timeout: float = 10.0) -> Optional[dict]:
    """Consulta CNPJ na BrasilAPI; retorna dict normalizado ou None se não encontrado."""
    digits = _clean_cnpj(cnpj)
    if len(digits) != 14:
        return None

    now = time.time()
    cached = _CACHE.get(digits)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]

    url = f"{_BASE_URL}/{digits}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError:
        return None

    normalized = _normalize(data)
    _CACHE[digits] = (now, normalized)
    return normalized


def _normalize(d: dict) -> dict:
    """Mapeia o JSON da BrasilAPI para o shape que o frontend espera."""
    return {
        "cnpj": d.get("cnpj"),
        "razao_social": d.get("razao_social") or d.get("nome_empresarial") or "",
        "nome_fantasia": d.get("nome_fantasia") or "",
        "email": d.get("email") or "",
        "phone": _format_phone(d.get("ddd_telefone_1") or ""),
        "zip_code": _format_cep(d.get("cep") or ""),
        "street": d.get("logradouro") or "",
        "address_number": d.get("numero") or "",
        "complement": d.get("complemento") or "",
        "neighborhood": d.get("bairro") or "",
        "city": d.get("municipio") or "",
        "state": d.get("uf") or "",
        "ibge_code": str(d.get("codigo_municipio_ibge") or "") or None,
        "cnae": str(d.get("cnae_fiscal") or "") or None,
        "situacao": d.get("descricao_situacao_cadastral") or "",
    }


def _format_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return raw or ""


def _format_cep(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return raw or ""

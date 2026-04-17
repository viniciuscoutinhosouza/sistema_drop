"""
Bling V3 API service.
Authentication: API Key (Bearer token)
Docs: https://developer.bling.com.br/bling-api
"""
import httpx
from fastapi import HTTPException

BLING_API_BASE = "https://www.bling.com.br/Api/v3"


async def validate_api_key(api_key: str) -> dict:
    """Validate a Bling API key by fetching account info."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BLING_API_BASE}/empresas",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Chave API Bling inválida")
    return resp.json()


async def sync_product(api_key: str, product_data: dict) -> dict:
    """Create or update a product in Bling."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BLING_API_BASE}/produtos",
            headers={"Authorization": f"Bearer {api_key}"},
            json=product_data,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao sincronizar produto Bling: {resp.text}")
    return resp.json()

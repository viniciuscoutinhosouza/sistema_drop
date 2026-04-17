import httpx
from fastapi import HTTPException


async def fetch_address(cep: str) -> dict:
    """
    Query ViaCEP API for a given ZIP code.
    Returns a dict with logradouro, bairro, localidade, uf.
    Raises HTTP 404 if CEP not found.
    """
    digits = cep.replace("-", "").replace(".", "").strip()
    if len(digits) != 8 or not digits.isdigit():
        raise HTTPException(status_code=400, detail="CEP inválido")

    url = f"https://viacep.com.br/ws/{digits}/json/"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url)
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Serviço ViaCEP indisponível")

    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="CEP não encontrado")

    data = response.json()
    if data.get("erro"):
        raise HTTPException(status_code=404, detail="CEP não encontrado")

    return {
        "zip_code": data.get("cep", ""),
        "street": data.get("logradouro", ""),
        "complement": data.get("complemento", ""),
        "neighborhood": data.get("bairro", ""),
        "city": data.get("localidade", ""),
        "state": data.get("uf", ""),
    }

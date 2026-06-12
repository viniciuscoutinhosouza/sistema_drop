from pydantic import BaseModel


class EShipConfigIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None  # só atualizado se vier preenchido
    is_active: bool = False

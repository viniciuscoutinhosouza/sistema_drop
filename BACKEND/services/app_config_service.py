"""Config GLOBAL chave/valor (ADR-nenhuma; tabela app_config, migration 168).

Ajustes simples sem tabela de domínio própria. Default resolvido aqui quando a chave não existe.
"""
from sqlalchemy import select

from models.app_config import AppConfig

# Defaults por chave (fallback quando a linha não existe).
_DEFAULTS = {
    "separation.finish_photos_code": "FIM-FOTOS",
}


async def get_config(db, key: str, default: str | None = None) -> str | None:
    row = (
        await db.execute(select(AppConfig.value).where(AppConfig.key == key))
    ).scalar_one_or_none()
    if row is not None:
        return row
    return default if default is not None else _DEFAULTS.get(key)


async def set_config(db, key: str, value: str, user_id: int | None = None, commit: bool = True) -> None:
    row = (await db.execute(select(AppConfig).where(AppConfig.key == key))).scalar_one_or_none()
    if row is None:
        row = AppConfig(key=key, value=value, updated_by=user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by = user_id
    if commit:
        await db.commit()

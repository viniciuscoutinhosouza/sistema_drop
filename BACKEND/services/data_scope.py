"""SSOT do ESCOPO DE DADOS do usuário (isolamento por galpão / por CMIG).

Ponto ÚNICO que decide o "modo de escopo" e resolve os conjuntos de dados visíveis.
Hoje o modo deriva de `User.role`; no plano "só Perfil de Acesso" (ADR-0035, Fase 1) ESTE
módulo passa a ser o único lugar a repontar para o Perfil de Acesso quando o campo `users.role`
for removido. Por isso todo escopo novo deve chamar estas funções em vez de ler `user.role`
inline (eram ~150 checagens espalhadas).

Modos canônicos:
  - GLOBAL ('admin') → vê tudo.
  - GALPAO ('go')    → isola por `warehouse_id` (ADR-0026).
  - CONTA  ('ac')    → isola por CMIGs administradas (`cmig_administrators`).
'ugo' (papel de galpão aposentado na ADR-0026) é normalizado para 'go'.

NÃO cobre a política do Atendimento (`services/atendimento_access.py`), que é AC+admin-only
(galpão = vazio) de propósito — política distinta, mantida separada.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIG, CMIGAdministrator
from models.user import User

GLOBAL = "admin"
GALPAO = "go"
CONTA = "ac"


def scope_mode(user: User) -> str:
    """Modo de escopo canônico do usuário.

    Fonte ATUAL: `user.role` (que hoje é cópia de `UserProfile.base_role`). Na Fase 3 do plano,
    quando `users.role` for removido, SÓ esta função muda (passa a ler do Perfil de Acesso) —
    é o valor do desacoplamento: um único ponto a repontar.
    """
    r = (user.role or "").strip().lower()
    if r == "ugo":  # papel de galpão aposentado (ADR-0026) → Galpão
        return GALPAO
    return r


def is_global(user: User) -> bool:
    return scope_mode(user) == GLOBAL


def is_galpao(user: User) -> bool:
    return scope_mode(user) == GALPAO


def is_conta(user: User) -> bool:
    return scope_mode(user) == CONTA


def warehouse_scope(user: User) -> int | None:
    """`None` se global (vê todos os galpões); senão o `warehouse_id` do usuário (ADR-0026)."""
    return None if is_global(user) else user.warehouse_id


async def administered_cmig_ids(user: User, db: AsyncSession) -> set[int]:
    """CMIGs em que o usuário é administrador (`cmig_administrators`) — bloco do escopo CONTA (AC)."""
    rows = (
        await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
    ).scalars().all()
    return set(rows)


async def accessible_cmig_ids(user: User, db: AsyncSession) -> set[int] | None:
    """Tríade canônica de CMIGs visíveis. `None` = todas (global/admin).

    - GLOBAL → None.
    - GALPAO → CMIGs do próprio `warehouse_id` (vazio se sem galpão — fail-closed).
    - CONTA  → CMIGs administradas.
    """
    if is_global(user):
        return None
    if is_galpao(user):
        if not user.warehouse_id:
            return set()  # Galpão sem galpão vinculado não vê nenhuma CMIG
        rows = (
            await db.execute(select(CMIG.id).where(CMIG.warehouse_id == user.warehouse_id))
        ).scalars().all()
        return set(rows)
    # CONTA (ac) e qualquer outro modo não-global → CMIGs administradas
    return await administered_cmig_ids(user, db)

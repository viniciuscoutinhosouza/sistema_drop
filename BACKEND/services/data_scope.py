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

from fastapi import HTTPException
from sqlalchemy import and_, select
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


async def assert_cmig_access(
    cmig: CMIG, user: User, db: AsyncSession, *, require_owner: bool = False
) -> None:
    """Valida se o usuário pode acessar a CMIG (ponto ÚNICO — era copiado em `cmigs` e `eship`).

    - GLOBAL → libera.
    - GALPAO → `cmig.warehouse_id == user.warehouse_id` (fail-closed se sem warehouse);
      `require_owner` nunca vale p/ galpão (galpão não é "AC proprietário") → 403.
    - CONTA  → precisa de linha em `cmig_administrators`; `require_owner` exige `is_owner`.
    - outro  → 403.
    """
    if is_global(user):
        return
    if is_galpao(user):
        # Fail-closed: Galpão sem warehouse_id (ou CMIG órfã) NÃO concede acesso — senão
        # None != None seria False e liberaria CMIG sem galpão (vazamento entre galpões).
        if not user.warehouse_id or cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        if require_owner:
            raise HTTPException(
                status_code=403, detail="Apenas o AC proprietário pode realizar esta ação"
            )
        return
    if is_conta(user):
        adm = (
            await db.execute(
                select(CMIGAdministrator).where(
                    and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig.id)
                )
            )
        ).scalar_one_or_none()
        if not adm:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        if require_owner and not adm.is_owner:
            raise HTTPException(
                status_code=403, detail="Apenas o AC proprietário pode realizar esta ação"
            )
        return
    raise HTTPException(status_code=403, detail="Permissão insuficiente")

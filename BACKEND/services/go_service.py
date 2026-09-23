"""Consistência do Gestor Operacional (GO).

Um usuário com papel `go` precisa ter um registro na tabela `goes` para ser reconhecido como GO
(ex.: aparecer no seletor de "GO dono" do galpão). Criar o usuário pela tela de Usuários setava só
`user.role='go'` e deixava o registro de GO faltando. Este helper fecha essa lacuna: sempre que um
usuário passa a ter papel GO, garante o registro correspondente (idempotente).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.go import GO
from models.user import User


async def ensure_go_record(user: User, db: AsyncSession) -> bool:
    """Garante um registro em `goes` para um usuário com papel GO.

    Idempotente: só cria quando `user.role == 'go'` e ainda não há GO para esse `user_id`.
    Não commita (segue a transação do chamador). Retorna True se criou um registro.
    """
    if not user or user.role != "go":
        return False
    existing = (
        await db.execute(select(GO).where(GO.user_id == user.id))
    ).scalar_one_or_none()
    if existing:
        return False
    db.add(GO(user_id=user.id, is_active=True))  # warehouse_id fica nulo até ser atribuído
    return True

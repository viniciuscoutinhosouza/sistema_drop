"""Consistência do Gestor Operacional (GO) dono.

ATENÇÃO — após a unificação Galpão, o papel `go` é o papel do OPERADOR de galpão (papel unificado
que substituiu o antigo `ugo`). Ter papel `go` NÃO significa ser GO-dono. O GO-dono é definido pelo
registro em `goes` + permissões de perfil (menus `go_empresa`/`go_usuarios`), não pelo base_role.

Por isso este helper NÃO deve ser disparado por cadastro de operador (auth.register_user/register_ugo
não o chamam mais). Ele é usado apenas quando um admin PROMOVE explicitamente um usuário a GO-dono
(routers/users.py update, admin-gated). O fluxo dedicado routers/goes.py:create_go cria o `GO`
diretamente, sem passar por aqui. Mantém idempotência para esse caminho de promoção.
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

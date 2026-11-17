"""Rota PÚBLICA (sem login) da gaiola — LINK EXTERNO (molde do checkout público, ADR-0033).

Um galpão que despacha mas NÃO tem acesso ao sistema abre UMA gaiola só pelo token e faz: ver os
pedidos, imprimir picking list / etiqueta / NF-e, bipar (manual/scan/scan_auto), fotos (opcional) e
CONCLUIR — SEM exigir foto (requisito do dono). O token escopa a UMA gaiola.

REUSO: cada endpoint resolve a gaiola pelo token, carrega o "ator" (criador da gaiola, via
`separation.cart_actor`) e chama a MESMA função autenticada de `routers.separation` — zero
duplicação da lógica de etiqueta/scan/NF-e/foto. O escopo-por-galpão das funções passa (o criador ∈
galpão da gaiola) e a auditoria (by_id) atribui ao criador. Montado SEM dependência de JWT em main.py.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.order import Order
from models.picking import PickingCart, PickingCartOrder
from routers import separation as sep

router = APIRouter()


async def _cart_by_token(token: str, db: AsyncSession) -> PickingCart:
    """Resolve a gaiola pelo token público. 404 se inválido/revogado. O token É a autorização —
    escopa a ESTA gaiola só (nunca a outras)."""
    if not token or len(token) < 20:
        raise HTTPException(status_code=404, detail="Link inválido")
    cart = (
        await db.execute(select(PickingCart).where(PickingCart.public_token == token))
    ).scalar_one_or_none()
    if not cart:
        raise HTTPException(status_code=404, detail="Link inválido ou revogado")
    return cart


async def _ctx(token: str, db: AsyncSession):
    cart = await _cart_by_token(token, db)
    actor = await sep.cart_actor(db, cart)
    return cart, actor


@router.get("/{token}")
async def public_view_cart(token: str, db: AsyncSession = Depends(get_db)):
    """A gaiola + pedidos (igual à tela interna) — reusa separation.get_cart."""
    cart, actor = await _ctx(token, db)
    return await sep.get_cart(cart.id, current_user=actor, db=db)


@router.post("/{token}/picking-list")
async def public_picking_list(token: str, db: AsyncSession = Depends(get_db)):
    """PDF consolidado da lista de picking (o que pegar) — reusa separation.picking_list_pdf."""
    cart, actor = await _ctx(token, db)
    oids = [
        r[0] for r in (
            await db.execute(
                select(PickingCartOrder.order_id).where(PickingCartOrder.cart_id == cart.id)
            )
        ).all()
    ]
    return await sep.picking_list_pdf({"order_ids": oids}, current_user=actor, db=db)


@router.get("/{token}/orders/{order_id}/shopee-label")
async def public_shopee_label(token: str, order_id: int, db: AsyncSession = Depends(get_db)):
    """Etiqueta Shopee (gerar = despachar) — reusa separation.cart_shopee_label."""
    cart, actor = await _ctx(token, db)
    return await sep.cart_shopee_label(cart.id, order_id, current_user=actor, db=db)


@router.get("/{token}/labels.pdf")
async def public_labels(
    token: str, order_id: int | None = None, account_id: int | None = None,
    manual: bool = False, layout: str = "10x15", fmt: str = "pdf",
    db: AsyncSession = Depends(get_db),
):
    """Etiquetas ML/manual (PDF/ZPL) — reusa separation.cart_labels."""
    cart, actor = await _ctx(token, db)
    return await sep.cart_labels(
        cart.id, account_id=account_id, order_id=order_id, manual=manual,
        layout=layout, fmt=fmt, current_user=actor, db=db,
    )


@router.get("/{token}/nfe")
async def public_nfe(
    token: str, order_id: int | None = None, mark: int = 0, db: AsyncSession = Depends(get_db)
):
    """URLs da DANFE de cada pedido — reusa separation.cart_nfe_urls (as URLs apontam p/ os endpoints
    públicos abaixo, reescritas no front)."""
    cart, actor = await _ctx(token, db)
    return await sep.cart_nfe_urls(cart.id, order_id=order_id, mark=mark, current_user=actor, db=db)


@router.post("/{token}/orders/{order_id}/scan")
async def public_scan(token: str, order_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """Bipagem (modo scan) de um item de um pedido — reusa separation.scan_order_item."""
    cart, actor = await _ctx(token, db)
    return await sep.scan_order_item(cart.id, order_id, body, current_user=actor, db=db)


@router.post("/{token}/scan-locate")
async def public_scan_locate(token: str, body: dict, db: AsyncSession = Depends(get_db)):
    """Bipagem automática: localiza o pedido pelo código — reusa separation.scan_locate."""
    cart, actor = await _ctx(token, db)
    return await sep.scan_locate(cart.id, body, current_user=actor, db=db)


@router.post("/{token}/orders/{order_id}/separate")
async def public_separate(
    token: str, order_id: int, files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Separar COM foto (opcional no fluxo externo) — reusa separation.separate_order."""
    cart, actor = await _ctx(token, db)
    return await sep.separate_order(cart.id, order_id, files=files, current_user=actor, db=db)


@router.post("/{token}/conclude")
async def public_conclude(token: str, db: AsyncSession = Depends(get_db)):
    """Conclui a gaiola pelo link externo — SEM exigir FOTO (requisito do dono). Mantém os gates de
    BIPAGEM (modo scan) e ETIQUETA impressa (despacho), mas marca os pedidos como separados sem a
    foto. Espelha separation.conclude_cart, sem a exigência de foto."""
    cart, actor = await _ctx(token, db)
    if cart.status != "open":
        raise HTTPException(status_code=409, detail="Gaiola não está aberta")
    pcos = (
        await db.execute(select(PickingCartOrder).where(PickingCartOrder.cart_id == cart.id))
    ).scalars().all()
    if not pcos:
        raise HTTPException(status_code=422, detail="Gaiola sem pedidos")
    now = datetime.now(UTC)
    for pco in pcos:
        if pco.item_status == "separated":
            continue
        order = (
            await db.execute(select(Order).where(Order.id == pco.order_id))
        ).scalar_one_or_none()
        # Gate de bipagem (scan/scan_auto): 100% bipado antes de concluir.
        if await sep._scan_blocks_label(db, cart, pco):
            raise HTTPException(
                status_code=422,
                detail=f"Pedido #{pco.order_id}: bipe todos os itens antes de concluir.",
            )
        # Gate de etiqueta impressa (= despacho) — mantém; NÃO exige foto.
        if order and not sep._label_done(pco, order):
            raise HTTPException(
                status_code=422,
                detail=f"Pedido #{pco.order_id}: imprima a etiqueta antes de concluir.",
            )
        pco.item_status = "separated"
        pco.separated_by = actor.id
        pco.separated_at = now
        if order:
            order.status = "separated"
            order.separated_at = now
            order.separated_by = actor.id
    cart.status = "separated"
    cart.separated_by = actor.id
    cart.separated_at = now
    await db.commit()
    return sep._ser_cart(cart)

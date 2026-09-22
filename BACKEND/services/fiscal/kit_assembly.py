"""Montagem (kitting) de KIT em remessa ao FULL — ADR-0023 §montagem.

Quando uma **remessa para o FULL** (`Invoice.purpose='remessa'`, saída) leva um produto **composto**
(kit), o kit é fisicamente montado a partir dos componentes: cada componente SAI do estoque local
("saída para transformação em KIT") e o KIT ENTRA (montado), indo ao FULL como unidade.

O `stock_quantity` real é dirigido pelo replay (`stock_calculator`: o componente é debitado pela
remessa; o kit fica líquido 0 localmente). Este módulo cuida do **extrato** — grava os
`stock_movements` que aparecem na tela de movimentação dos dois produtos. Idempotente: reexecutar
(reautorização ou backfill) não duplica.
"""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fiscal import Invoice, InvoiceItem
from models.product import CatalogProduct, CatalogProductComponent
from models.stock_movement import StockMovement

MT_ASSEMBLY_OUT = "kit_assembly_out"  # componente sai (transformação em KIT)
MT_ASSEMBLY_IN = "kit_assembly_in"    # KIT entra (montado)
MT_FULL_OUT = "kit_full_out"          # KIT sai do galpão PG (envio ao FULL)


async def _has_movement(db: AsyncSession, invoice_id: int, product_id: int, mt: str) -> bool:
    return (
        await db.execute(
            select(StockMovement.id).where(
                StockMovement.invoice_id == invoice_id,
                StockMovement.product_id == product_id,
                StockMovement.product_type == "pg",
                StockMovement.movement_type == mt,
            )
        )
    ).scalar_one_or_none() is not None


async def sync_kit_assembly_movements(db: AsyncSession, invoice: Invoice) -> dict:
    """Garante os movimentos de montagem para uma remessa-ao-FULL com item composto.

    Só age em `purpose='remessa'`, saída, autorizada/finalizada. Para cada item que é KIT (PG
    composto), grava (idempotente): `kit_assembly_in` no KIT (+qtd) e `kit_assembly_out` em cada
    componente (−qtd×composição). NÃO altera `stock_quantity` (isso é replay) — só o extrato.

    Retorna {'kits': n, 'movements_created': m}.
    """
    if (invoice.direction != "out" or invoice.purpose != "remessa"
            or invoice.status not in ("authorized", "finalized")):
        return {"kits": 0, "movements_created": 0}

    items = (
        await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
    ).scalars().all()

    kits = 0
    created = 0
    for it in items:
        if not it.catalog_product_id:
            continue
        kit = (
            await db.execute(
                select(CatalogProduct).where(CatalogProduct.id == it.catalog_product_id)
            )
        ).scalar_one_or_none()
        if not kit or not kit.is_composite:
            continue
        comps = (
            await db.execute(
                select(CatalogProductComponent).where(
                    CatalogProductComponent.composite_id == kit.id
                )
            )
        ).scalars().all()
        if not comps:
            continue
        kits += 1
        qtd_kit = int(it.quantity or 0)

        # Entrada do KIT (montagem) — no extrato do próprio kit.
        if not await _has_movement(db, invoice.id, kit.id, MT_ASSEMBLY_IN):
            db.add(StockMovement(
                product_type="pg", product_id=kit.id, invoice_id=invoice.id,
                movement_type=MT_ASSEMBLY_IN, qty=qtd_kit,
                field_affected="stock_quantity", delta=qtd_kit,
            ))
            created += 1

        # Saída do KIT do galpão PG: ENVIO AO FULL. Balanceia a montagem (+N montagem, −N envio ao
        # FULL = 0 no galpão PG), espelhando o `full_in` no CMIG. Ledger-only (o saldo é replay).
        if not await _has_movement(db, invoice.id, kit.id, MT_FULL_OUT):
            db.add(StockMovement(
                product_type="pg", product_id=kit.id, invoice_id=invoice.id,
                movement_type=MT_FULL_OUT, qty=qtd_kit,
                field_affected="stock_quantity", delta=-qtd_kit,
            ))
            created += 1

        # Saída de cada componente (transformação em KIT) — no extrato do componente.
        for c in comps:
            consumo = qtd_kit * int(c.quantity or 1)
            if not await _has_movement(db, invoice.id, c.component_id, MT_ASSEMBLY_OUT):
                db.add(StockMovement(
                    product_type="pg", product_id=c.component_id, invoice_id=invoice.id,
                    movement_type=MT_ASSEMBLY_OUT, qty=consumo,
                    field_affected="stock_quantity", delta=-consumo,
                ))
                created += 1

    return {"kits": kits, "movements_created": created}


async def backfill_all_kit_remessas(db: AsyncSession) -> dict:
    """Reprocessa TODAS as remessas ao FULL que contêm kit (a NFE 3087 e demais).

    Grava os movimentos de montagem faltantes (idempotente). Não recomputa estoque — o chamador
    roda o recompute em seguida. Retorna resumo.
    """
    inv_ids = (
        await db.execute(
            select(InvoiceItem.invoice_id)
            .join(CatalogProduct, CatalogProduct.id == InvoiceItem.catalog_product_id)
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(and_(
                Invoice.direction == "out",
                Invoice.purpose == "remessa",
                Invoice.status.in_(("authorized", "finalized")),
                CatalogProduct.is_composite == True,  # noqa: E712
            ))
            .distinct()
        )
    ).scalars().all()

    total_created = 0
    processed = 0
    for iid in inv_ids:
        inv = (await db.execute(select(Invoice).where(Invoice.id == iid))).scalar_one_or_none()
        if not inv:
            continue
        res = await sync_kit_assembly_movements(db, inv)
        total_created += res["movements_created"]
        processed += 1
    return {"invoices": processed, "movements_created": total_created}

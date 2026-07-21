"""
Background task: destrava pedidos ML presos em `nfe_status` 'pending'/'in_process'.

A emissão da NF-e no ML (Faturador) é ASSÍNCRONA: ao clicar "Emitir NF-e" o pedido vira
'pending' na hora e um fetch imediato tenta pegar o status. Se o ML ainda estava processando
naquele instante, o pedido ficava 'pending' **para sempre** — nada re-sincronizava depois (o
scheduler de pedidos não atualiza `nfe_status` de pedido existente) e o botão "Processando NF-e…"
fica desabilitado, sem como o usuário forçar o sync.

Este job re-consulta o ML para os pedidos em 'pending'/'in_process' e atualiza o status quando o
ML resolve (authorized/rejected/etc.), via `fetch_and_cache_order_invoices` (mesma função do
botão/tela Fiscal). Roda a cada 15 min. É a rede de segurança que garante que nenhum pedido fique
travado em "Processando NF-e".
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from database import task_db
from models.integration import MarketplaceAccount
from models.order import Order
from tasks._job_wrapper import tracked_job

# Só varre pedidos recentes: a nota do ML resolve em minutos/horas. Varrer o histórico inteiro
# seria caro e inútil — um 'pending' de semanas atrás é anomalia para tratamento manual.
_JANELA_DIAS = 30


async def sync_pending_nfe():
    async with tracked_job("sync_pending_nfe") as result:
        # lazy import: evita puxar routers.orders (pesado) no boot do scheduler
        from routers.orders import fetch_and_cache_order_invoices

        stats = {"checked": 0, "resolved": 0, "still_pending": 0, "errors": 0}
        desde = datetime.now(UTC) - timedelta(days=_JANELA_DIAS)

        async with task_db() as db:
            orders = list(
                (
                    await db.execute(
                        select(Order).where(
                            Order.platform == "mercadolivre",
                            Order.nfe_status.in_(("pending", "in_process")),
                            Order.status != "cancelled",
                            Order.created_at >= desde,
                        )
                    )
                )
                .scalars()
                .all()
            )
            stats["checked"] = len(orders)

            acc_cache: dict[int, MarketplaceAccount] = {}
            for order in orders:
                try:
                    acc = acc_cache.get(order.account_id)
                    if acc is None:
                        acc = (
                            await db.execute(
                                select(MarketplaceAccount).where(
                                    MarketplaceAccount.id == order.account_id
                                )
                            )
                        ).scalar_one_or_none()
                        if not acc or not acc.is_active or not acc.access_token:
                            continue
                        acc_cache[order.account_id] = acc

                    before = order.nfe_status
                    # Atualiza nfe_status/nfe_key/nfe_url a partir do ML (commita internamente).
                    await fetch_and_cache_order_invoices(db, order, acc)
                    if order.nfe_status != before:
                        stats["resolved"] += 1
                    else:
                        stats["still_pending"] += 1
                except Exception as e:  # noqa: BLE001 — um pedido não pode derrubar o job inteiro
                    stats["errors"] += 1
                    print(f"[sync_pending_nfe] order={order.id} error: {e}")

        result.set(stats)
        return stats

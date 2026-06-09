"""DRE (Demonstração do Resultado do Exercício) por CMIG.

Modelo de 3 camadas somadas por linha:
  1. Snapshot ML (dre_snapshots) — valores sincronizados do Mercado Livre
     (operacional via tabela orders + billing oficial + ADS), cacheados por mês.
  2. Lançamentos manuais (dre_entries) — entradas/custos digitados pelo usuário.
  3. Imposto estimado — derivado na leitura: faturamento * tax_estimate_pct.

A leitura (build_dre) só lê e soma — nunca chama o ML. O ML só é tocado em
sync_month, acionado pelo botão de sincronização de um mês na tela.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import task_db
from models.dre import DREEntry, DRESnapshot
from models.fiscal import CMIGFiscalConfig
from models.integration import MarketplaceAccount
from models.order import Order, OrderItem
from services import ml_auth, ml_service

logger = logging.getLogger(__name__)

# America/Sao_Paulo é -03:00 o ano todo (sem horário de verão desde 2019).
BR_TZ = timezone(timedelta(hours=-3))

MONTHS_PT = [
    "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
    "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
]

VALID_SALE_STATUSES_EXCLUDED = ("cancelled", "returned")


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """Retorna (início inclusivo, fim exclusivo) do mês — datetimes tz-aware em -03:00.

    Tz-aware é essencial: orders.created_at/paid_at são TIMESTAMP WITH TIME ZONE.
    Comparar com datetime naive deslocava as bordas do mês (bug do faturamento).
    """
    start = datetime(year, month, 1, tzinfo=BR_TZ)
    if month == 12:
        end_excl = datetime(year + 1, 1, 1, tzinfo=BR_TZ)
    else:
        end_excl = datetime(year, month + 1, 1, tzinfo=BR_TZ)
    return start, end_excl


def _d(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


# ─── Sincronização (ML → snapshot) ───────────────────────────────────────────


async def sync_month(cmig_id: int, year: int, month: int) -> dict:
    """Sincroniza um mês reconciliando 3 fontes (ordem crescente de autoridade):

      A) Banco (tabela orders) — baseline rápido, agregação SQL.
      B) Operacional ao vivo — /orders/search?order.status=paid (faturamento/tarifa/cancelados).
      C) Billing oficial — /billing (tarifa/frete/estorno realmente cobrados).

    Faturamento: B (ao vivo) > A (banco). Tarifa/frete: C (billing) > B > A.
    CMV (custo dos produtos) só existe no banco. Tolerante a falha parcial.

    IMPORTANTE (pool de conexões): a fase de rede ao ML pode levar dezenas de
    segundos. Por isso esta função NÃO recebe a sessão do request — ela usa
    sessões curtas (task_db) e LIBERA a conexão do pool durante as chamadas
    HTTP. Segurar a conexão durante a rede esgotava o QueuePool (size 5 +10).
    """
    start, end_excl = _month_range(year, month)

    # Intervalo em ISO-8601 com offset -03:00 para os endpoints do ML.
    date_from = start.isoformat(timespec="milliseconds")
    date_to = (end_excl - timedelta(milliseconds=1)).isoformat(timespec="milliseconds")
    date_from_d = start.strftime("%Y-%m-%d")
    date_to_d = end_excl.strftime("%Y-%m-%d")

    # ── Fase 1 (DB curto): baseline do banco + IDs das contas; conexão liberada ao sair ──
    async with task_db() as db:
        period_col = func.coalesce(Order.paid_at, Order.created_at)
        base = and_(Order.cmig_id == cmig_id, period_col >= start, period_col < end_excl)
        valid = and_(base, Order.status.notin_(VALID_SALE_STATUSES_EXCLUDED))

        fat_db = await _scalar(
            db, select(func.sum(Order.sale_amount)).where(valid, Order.payment_status == "paid")
        )
        canc_db = await _scalar(
            db, select(func.sum(Order.sale_amount)).where(base, Order.status == "cancelled")
        )
        tarifa_db = await _scalar(db, select(func.sum(Order.platform_fee)).where(valid))
        frete_db = await _scalar(db, select(func.sum(Order.seller_shipping_cost)).where(valid))
        custo_produtos = await _scalar(
            db,
            select(func.sum(OrderItem.unit_cost * OrderItem.quantity))
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .where(valid),
        )
        account_ids = (
            await db.execute(
                select(MarketplaceAccount.id).where(
                    MarketplaceAccount.cmig_id == cmig_id,
                    MarketplaceAccount.platform == "mercadolivre",
                )
            )
        ).scalars().all()

    gasto_ads = Decimal("0")
    # B) acumuladores do operacional ao vivo
    live_fat = Decimal("0")
    live_fat_total_amount = Decimal("0")
    live_tarifa = Decimal("0")
    live_canc = Decimal("0")
    live_paid_count = 0
    live_units = 0
    live_complete = bool(account_ids)  # só usa o ao vivo se TODAS as contas responderem
    # C) acumuladores do billing
    bill_tarifa = Decimal("0")
    bill_frete = Decimal("0")
    bill_estorno = Decimal("0")
    bill_any = False
    billing_payload: dict = {}

    for acc_id in account_ids:
        # Token + seller_id numa sessão curta (refresh é rápido). Conexão liberada antes da rede.
        token = None
        seller_id = None
        async with task_db() as tdb:
            acc = (
                await tdb.execute(
                    select(MarketplaceAccount).where(MarketplaceAccount.id == acc_id)
                )
            ).scalar_one_or_none()
            if acc is not None:
                try:
                    token = await ml_auth.get_valid_token(acc, tdb)
                    seller_id = await _ensure_seller_id(acc, token, tdb)
                except Exception as e:
                    logger.warning("[DRE] conta %s sem token válido: %s", acc_id, e)
                    token = None

        if not token:
            live_complete = False
            continue

        # ── Rede ao ML — SEM conexão de banco em mãos ──
        # B) Operacional ao vivo via /orders/search
        if seller_id:
            try:
                orders = await ml_service.search_orders_by_created(
                    token, str(seller_id), date_from, date_to
                )
                agg = _aggregate_live_orders(orders)
                live_fat += agg["faturamento"]
                live_fat_total_amount += agg["faturamento_total_amount"]
                live_tarifa += agg["tarifa"]
                live_canc += agg["cancelados"]
                live_paid_count += agg["paid_count"]
                live_units += agg["units"]
            except Exception as e:
                logger.warning("[DRE] orders/search conta %s falhou: %s", acc_id, e)
                live_complete = False
        else:
            live_complete = False

        # ADS
        try:
            advertisers = await ml_service.get_advertisers(token)
            for adv in advertisers:
                adv_id = adv.get("advertiser_id") or adv.get("id")
                if adv_id:
                    gasto_ads += _d(
                        await ml_service.get_ads_cost(token, str(adv_id), date_from_d, date_to_d)
                    )
        except Exception as e:
            logger.warning("[DRE] ADS conta %s falhou: %s", acc_id, e)

        # C) Billing — conciliação oficial
        try:
            billing = await _fetch_billing(token, year, month)
            if billing:
                bill_any = True
                billing_payload[str(acc_id)] = billing.get("raw", {})
                bill_tarifa += _d(billing.get("tarifa_venda"))
                bill_frete += _d(billing.get("frete_vendedor"))
                bill_estorno += _d(billing.get("devolucao_parcial"))
        except Exception as e:
            logger.warning("[DRE] billing conta %s falhou: %s", acc_id, e)

    # ── Reconciliação: escolhe a fonte mais autoritativa por linha ──
    faturamento = live_fat if live_complete else _d(fat_db)
    vendas_canceladas = live_canc if live_complete else _d(canc_db)

    if bill_any and bill_tarifa:
        tarifa_venda = bill_tarifa
    elif live_complete:
        tarifa_venda = live_tarifa
    else:
        tarifa_venda = _d(tarifa_db)

    frete_vendedor = bill_frete if (bill_any and bill_frete) else _d(frete_db)
    devolucao_parcial = bill_estorno

    # 'reconciled' quando o billing entrou na conta; senão 'operational' (banco ou ao vivo).
    source = "reconciled" if bill_any else "operational"

    # Auditoria: guarda as 3 fontes lado a lado para depurar divergências.
    recon = {
        "db": {
            "faturamento": float(_d(fat_db)),
            "vendas_canceladas": float(_d(canc_db)),
            "tarifa": float(_d(tarifa_db)),
            "frete": float(_d(frete_db)),
        },
        "live": {
            "complete": live_complete,
            "faturamento": float(live_fat),  # Σ unit_price*qty (usado na DRE)
            "faturamento_total_amount": float(live_fat_total_amount),  # auditoria
            "vendas_canceladas": float(live_canc),
            "tarifa": float(live_tarifa),
            "paid_count": live_paid_count,
            "units": live_units,
        },
        "billing": {
            "any": bill_any,
            "tarifa": float(bill_tarifa),
            "frete": float(bill_frete),
            "estorno": float(bill_estorno),
            "raw": billing_payload,
        },
    }

    # ── Fase 3 (DB curto): upsert do snapshot ──
    async with task_db() as db:
        snap = (
            await db.execute(
                select(DRESnapshot).where(
                    DRESnapshot.cmig_id == cmig_id,
                    DRESnapshot.ref_year == year,
                    DRESnapshot.ref_month == month,
                )
            )
        ).scalar_one_or_none()

        if not snap:
            snap = DRESnapshot(cmig_id=cmig_id, ref_year=year, ref_month=month)
            db.add(snap)

        snap.faturamento = _d(faturamento)
        snap.vendas_canceladas = _d(vendas_canceladas)
        snap.tarifa_venda = _d(tarifa_venda)
        snap.frete_vendedor = _d(frete_vendedor)
        snap.custo_produtos = _d(custo_produtos)
        snap.gasto_ads = gasto_ads
        snap.devolucao_parcial = devolucao_parcial
        snap.source = source
        snap.billing_json = json.dumps(recon, ensure_ascii=False)
        snap.last_synced_at = datetime.now(UTC)

        await db.commit()
        synced_at = snap.last_synced_at

    return {
        "source": source,
        "last_synced_at": synced_at.isoformat() if synced_at else None,
    }


async def _ensure_seller_id(acc: MarketplaceAccount, token: str, db: AsyncSession):
    """Retorna o seller_id (platform_user_id). Faz backfill via /users/me se faltar."""
    if acc.platform_user_id:
        return acc.platform_user_id
    try:
        info = await ml_service.get_user_info(token)
        uid = info.get("id")
        if uid:
            acc.platform_user_id = str(uid)
            await db.commit()
        return uid
    except Exception as e:
        logger.warning("[DRE] backfill seller_id conta %s falhou: %s", acc.id, e)
        return None


def _aggregate_live_orders(orders: list) -> dict:
    """Agrega pedidos do /orders/search em uma estrutura para reconciliação.

    Faturamento (= "Vendas brutas" do ML) é a RECEITA DE ITENS:
        Σ order_items[].unit_price * quantity   (33 un × R$130,21 = R$4.297)
    e NÃO o total_amount, que pode vir abaixo por cupom/desconto custeado pelo ML.

    Retorna ambas as formas para auditar divergências:
      - faturamento: Σ unit_price*qty (pagos)      ← usado na DRE
      - faturamento_total_amount: Σ total_amount (pagos)  ← só auditoria
      - tarifa: Σ sale_fee*qty (pagos)
      - cancelados: Σ unit_price*qty (cancelados)
      - paid_count / cancelled_count / units
    """
    fat_items = Decimal("0")
    fat_total_amount = Decimal("0")
    tarifa = Decimal("0")
    canc = Decimal("0")
    units = 0
    paid_count = 0
    cancelled_count = 0
    for o in orders or []:
        status = o.get("status")
        items_rev = Decimal("0")
        for it in o.get("order_items", []) or []:
            qty = _d(it.get("quantity") or 1)
            items_rev += _d(it.get("unit_price")) * qty
            if status == "paid":
                tarifa += _d(it.get("sale_fee")) * qty
                units += int(it.get("quantity") or 1)
        if status == "paid":
            fat_items += items_rev
            fat_total_amount += _d(
                o.get("total_amount") if o.get("total_amount") is not None else o.get("paid_amount")
            )
            paid_count += 1
        elif status == "cancelled":
            canc += items_rev
            cancelled_count += 1
    return {
        "faturamento": fat_items,
        "faturamento_total_amount": fat_total_amount,
        "tarifa": tarifa,
        "cancelados": canc,
        "paid_count": paid_count,
        "cancelled_count": cancelled_count,
        "units": units,
    }


async def _fetch_billing(token: str, year: int, month: int) -> dict | None:
    """Busca o período de billing do mês e tenta extrair tarifa/frete/estorno reais.

    O shape exato da resposta do ML varia; esta função é defensiva e guarda o
    bruto em 'raw' para auditoria. Pode precisar de ajuste contra conta real.
    """
    periods = await ml_service.get_billing_periods(token)
    key = _match_period_key(periods, year, month)
    if not key:
        return None

    summary = await ml_service.get_billing_summary(token, key)
    details = await ml_service.get_billing_details(token, key)

    tarifa = _sum_billing_by_keywords(details, ("tarifa", "fee", "comiss", "sale"))
    frete = _sum_billing_by_keywords(details, ("frete", "shipping", "envio", "ship"))
    estorno = _sum_billing_by_keywords(details, ("estorno", "refund", "devol", "cancel"))

    return {
        "tarifa_venda": tarifa if tarifa else None,
        "frete_vendedor": frete if frete else None,
        "devolucao_parcial": estorno if estorno else None,
        "raw": {"summary": summary, "details_count": len(details)},
    }


def _match_period_key(periods: list[dict], year: int, month: int) -> str | None:
    """Encontra a 'key' do período cujo intervalo cai no (year, month)."""
    target = f"{year:04d}-{month:02d}"
    for p in periods or []:
        key = p.get("key") or p.get("period_key") or p.get("id")
        # tenta casar por campos de data comuns
        for field in ("period", "date_from", "from", "start_date", "month"):
            val = str(p.get(field) or "")
            if val.startswith(target):
                return key
    return None


def _sum_billing_by_keywords(details: list[dict], keywords: tuple) -> Decimal:
    """Soma o valor das linhas de detalhe cujo conceito casa com alguma keyword."""
    total = Decimal("0")
    for row in details or []:
        concept = " ".join(
            str(row.get(f) or "")
            for f in ("detail", "concept", "charge_type", "description", "marketplace_concept")
        ).lower()
        if any(k in concept for k in keywords):
            amount = row.get("amount") or row.get("charge_amount") or row.get("value") or 0
            total += _d(amount).copy_abs()
    return total


async def _scalar(db: AsyncSession, stmt) -> Decimal:
    res = await db.execute(stmt)
    return _d(res.scalar())


# ─── Leitura (montagem da grade) ─────────────────────────────────────────────


async def build_dre(db: AsyncSession, cmig_id: int, year: int) -> dict:
    """Monta a grade da DRE (12 meses) combinando snapshots + lançamentos + imposto."""
    # Snapshots do ano
    snaps = (
        await db.execute(
            select(DRESnapshot).where(
                DRESnapshot.cmig_id == cmig_id, DRESnapshot.ref_year == year
            )
        )
    ).scalars().all()
    snap_by_month = {s.ref_month: s for s in snaps}

    # % de imposto da config fiscal
    cfg = (
        await db.execute(
            select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig_id)
        )
    ).scalar_one_or_none()
    tax_pct = _d(cfg.tax_estimate_pct) if cfg else Decimal("0")

    # Lançamentos manuais do ano
    entries = (
        await db.execute(
            select(DREEntry).where(DREEntry.cmig_id == cmig_id, DREEntry.ref_year == year)
        )
    ).scalars().all()

    z = lambda: [Decimal("0")] * 12  # noqa: E731

    # Linhas ML
    faturamento = z()
    vendas_canceladas = z()
    tarifa = z()
    devolucao = z()
    custo_prod = z()
    frete = z()
    ads = z()
    imposto = z()
    for m in range(1, 13):
        s = snap_by_month.get(m)
        if s:
            faturamento[m - 1] = _d(s.faturamento)
            vendas_canceladas[m - 1] = _d(s.vendas_canceladas)
            tarifa[m - 1] = _d(s.tarifa_venda)
            devolucao[m - 1] = _d(s.devolucao_parcial)
            custo_prod[m - 1] = _d(s.custo_produtos)
            frete[m - 1] = _d(s.frete_vendedor)
            ads[m - 1] = _d(s.gasto_ads)
        imposto[m - 1] = (faturamento[m - 1] * tax_pct / Decimal("100")).quantize(Decimal("0.01"))

    # Lançamentos manuais agrupados por (kind, rótulo)
    manual: dict[str, dict[str, list]] = {
        "entrada": {},
        "custo_operacional": {},
        "custo_fixo": {},
    }
    for e in entries:
        kind = e.category_kind
        if kind not in manual:
            continue
        label = e.category or e.description or "Outros"
        bucket = manual[kind].setdefault(label, z())
        if 1 <= (e.ref_month or 0) <= 12:
            bucket[e.ref_month - 1] += _d(e.amount)

    # Monta as linhas (rows) no formato do print
    rows: list[dict] = []

    # (+) TOTAL ENTRADA
    total_entrada = z()
    entrada_lines = [("Faturamento ML", faturamento)]
    for label, vals in manual["entrada"].items():
        entrada_lines.append((label, vals))
    for _, vals in entrada_lines:
        _acc(total_entrada, vals)
    rows.append(_row("total", "entrada", "(+) TOTAL ENTRADA", total_entrada))
    for label, vals in entrada_lines:
        rows.append(_row("line", "", label, vals))

    # (-) TOTAL CUSTO OPERACIONAL
    total_custo_op = z()
    custo_op_lines = [
        ("Vendas Canceladas ML", vendas_canceladas),
        ("Tarifa de Venda ML", tarifa),
        ("Devolução Parcial ML", devolucao),
        ("Custo dos Produtos ML", custo_prod),
        ("Imposto ML", imposto),
        ("Frete Vendedor ML", frete),
        ("Gasto em ADS ML", ads),
    ]
    for label, vals in manual["custo_operacional"].items():
        custo_op_lines.append((label, vals))
    for _, vals in custo_op_lines:
        _acc(total_custo_op, vals)
    rows.append(_row("total", "custo", "(-) TOTAL CUSTO OPERACIONAL", total_custo_op))
    for label, vals in custo_op_lines:
        rows.append(_row("line", "", label, vals))

    # (=) MARGEM DE CONTRIBUIÇÃO
    margem = [total_entrada[i] - total_custo_op[i] for i in range(12)]
    rows.append(_result_row("margem", "(=) MARGEM DE CONTRIBUIÇÃO", margem, total_entrada))

    # (-) TOTAL CUSTO FIXO
    total_custo_fixo = z()
    custo_fixo_lines = list(manual["custo_fixo"].items())
    for _, vals in custo_fixo_lines:
        _acc(total_custo_fixo, vals)
    rows.append(_row("total", "custo", "(-) TOTAL CUSTO FIXO", total_custo_fixo))
    for label, vals in custo_fixo_lines:
        rows.append(_row("line", "", label, vals))

    # (=) LUCRO LÍQUIDO
    lucro = [margem[i] - total_custo_fixo[i] for i in range(12)]
    rows.append(_result_row("lucro", "(=) LUCRO LÍQUIDO", lucro, total_entrada))

    synced = {
        m: (snap_by_month[m].last_synced_at.isoformat() if snap_by_month.get(m) and snap_by_month[m].last_synced_at else None)
        for m in range(1, 13)
    }

    return {
        "cmig_id": cmig_id,
        "year": year,
        "months": MONTHS_PT,
        "synced": synced,
        "tax_estimate_pct": float(tax_pct),
        "rows": rows,
    }


def _acc(target: list, vals: list) -> None:
    for i in range(12):
        target[i] += vals[i]


def _row(kind: str, variant: str, label: str, vals: list) -> dict:
    return {
        "kind": kind,
        "variant": variant,
        "label": label,
        "values": [float(v) for v in vals],
        "total": float(sum(vals)),
    }


def _result_row(variant: str, label: str, vals: list, base: list) -> dict:
    pct = []
    for i in range(12):
        pct.append(round(float(vals[i] / base[i] * 100), 2) if base[i] else 0.0)
    total_base = sum(base)
    pct_total = round(float(sum(vals) / total_base * 100), 2) if total_base else 0.0
    return {
        "kind": "result",
        "variant": variant,
        "label": label,
        "values": [float(v) for v in vals],
        "total": float(sum(vals)),
        "pct": pct,
        "pct_total": pct_total,
    }


# ─── CRUD de lançamentos manuais ─────────────────────────────────────────────


async def create_entry(db: AsyncSession, cmig_id: int, user_id: int, data: dict) -> list[DREEntry]:
    """Cria um lançamento. Se recorrente (installments > 1), gera N parcelas
    mensais a partir de (ref_year, ref_month) com o mesmo recurrence_group_id."""
    installments = int(data.get("installments") or 1)
    installments = max(1, installments)
    group_id = str(uuid.uuid4()) if installments > 1 else None

    created: list[DREEntry] = []
    year = int(data["ref_year"])
    month = int(data["ref_month"])
    for i in range(installments):
        e = DREEntry(
            cmig_id=cmig_id,
            created_by=user_id,
            category_kind=data["category_kind"],
            description=data.get("description"),
            category=data.get("category"),
            amount=_d(data["amount"]),
            ref_year=year,
            ref_month=month,
            recurrence_group_id=group_id,
            installment_no=(i + 1) if installments > 1 else None,
            total_installments=installments if installments > 1 else None,
        )
        db.add(e)
        created.append(e)
        # avança um mês
        month += 1
        if month > 12:
            month = 1
            year += 1

    await db.commit()
    for e in created:
        await db.refresh(e)
    return created


async def update_entry(
    db: AsyncSession, entry: DREEntry, data: dict, scope: str = "one"
) -> None:
    """Atualiza um lançamento. scope='future' aplica a esta e às parcelas futuras
    do mesmo recurrence_group_id."""
    fields = {
        k: data[k]
        for k in ("category_kind", "description", "category", "amount")
        if k in data and data[k] is not None
    }
    targets = [entry]
    if scope == "future" and entry.recurrence_group_id:
        rows = (
            await db.execute(
                select(DREEntry).where(
                    DREEntry.recurrence_group_id == entry.recurrence_group_id,
                    DREEntry.installment_no >= (entry.installment_no or 0),
                )
            )
        ).scalars().all()
        targets = rows or [entry]

    for t in targets:
        for k, v in fields.items():
            setattr(t, k, _d(v) if k == "amount" else v)
    await db.commit()


async def delete_entry(db: AsyncSession, entry: DREEntry, scope: str = "one") -> None:
    """Exclui um lançamento. scope='future' exclui esta e as parcelas futuras."""
    targets = [entry]
    if scope == "future" and entry.recurrence_group_id:
        rows = (
            await db.execute(
                select(DREEntry).where(
                    DREEntry.recurrence_group_id == entry.recurrence_group_id,
                    DREEntry.installment_no >= (entry.installment_no or 0),
                )
            )
        ).scalars().all()
        targets = rows or [entry]
    for t in targets:
        db.delete(t)
    await db.commit()


async def list_entries(db: AsyncSession, cmig_id: int, year: int, month: int | None = None) -> list[dict]:
    stmt = select(DREEntry).where(DREEntry.cmig_id == cmig_id, DREEntry.ref_year == year)
    if month:
        stmt = stmt.where(DREEntry.ref_month == month)
    stmt = stmt.order_by(DREEntry.ref_month, DREEntry.id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_serialize_entry(e) for e in rows]


def _serialize_entry(e: DREEntry) -> dict:
    return {
        "id": e.id,
        "cmig_id": e.cmig_id,
        "category_kind": e.category_kind,
        "description": e.description,
        "category": e.category,
        "amount": float(_d(e.amount)),
        "ref_year": e.ref_year,
        "ref_month": e.ref_month,
        "recurrence_group_id": e.recurrence_group_id,
        "installment_no": e.installment_no,
        "total_installments": e.total_installments,
    }

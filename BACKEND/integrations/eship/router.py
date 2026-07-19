"""Endpoints do módulo eShip: /api/v1/integrations/eship/*

- Config por galpão (admin).
- Envio manual e sincronização de status de um pedido.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import require_role
from models.cmig import CMIG, CMIGAdministrator
from models.order import Order
from models.user import User
from models.warehouse import Warehouse

from . import export, service
from .client import EShipError
from .config import EShipConfig, get_config
from .schemas import EShipConfigIn

router = APIRouter()


async def _assert_cmig_access(db: AsyncSession, cmig: CMIG, user: User) -> None:
    """Garante que o usuário pode acessar a CMIG (mesmo critério de routers.cmigs).

    admin → tudo; ugo → CMIG do seu galpão; ac → CMIG que administra.
    """
    if user.role == "admin":
        return
    if user.role == "ugo":
        # warehouse_id nulo (ugo sem galpão / CMIG órfã) NÃO concede acesso.
        if not user.warehouse_id or cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        return
    if user.role == "ac":
        adm = (
            await db.execute(
                select(CMIGAdministrator).where(
                    and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig.id)
                )
            )
        ).scalar_one_or_none()
        if not adm:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        return
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


async def _accessible_cmig_ids(db: AsyncSession, user: User) -> set[int] | None:
    """IDs de CMIG que o usuário pode ver. None = todas (admin)."""
    if user.role == "admin":
        return None
    if user.role == "ugo":
        if not user.warehouse_id:
            return set()  # ugo sem galpão não vê nenhuma CMIG
        rows = (
            await db.execute(select(CMIG.id).where(CMIG.warehouse_id == user.warehouse_id))
        ).all()
        return {r[0] for r in rows}
    rows = (
        await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
    ).all()
    return {r[0] for r in rows}


def _serialize(wh: Warehouse, cfg: EShipConfig | None) -> dict:
    return {
        "warehouse_id": wh.id,
        "warehouse_name": wh.name,
        "base_url": cfg.base_url if cfg else "",
        "api_key_set": bool(cfg and cfg.api_key),  # nunca devolve a key
        "is_active": bool(cfg and cfg.is_active),
        "updated_at": cfg.updated_at.isoformat() if (cfg and cfg.updated_at) else None,
    }


@router.get("/enabled")
async def eship_enabled(
    current_user: User = Depends(require_role("admin", "ugo", "go", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Indica se há eShip ativo (alguma CMIG ou galpão), para a UI decidir mostrar ações."""
    cmig_row = (
        await db.execute(
            select(CMIG.id).where(CMIG.eship_active == 1).limit(1)
        )
    ).first()
    if cmig_row is not None:
        return {"enabled": True}
    wh_row = (
        await db.execute(
            select(EShipConfig.id).where(EShipConfig.is_active == True).limit(1)  # noqa: E712
        )
    ).first()
    return {"enabled": wh_row is not None}


@router.get("/cmigs")
async def list_cmig_integrations(
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Lista CMIGs ACESSÍVEIS ao usuário com o status da integração eShip (apikey nunca exposta)."""
    allowed = await _accessible_cmig_ids(db, current_user)
    cmigs = (await db.execute(select(CMIG).order_by(CMIG.company_name))).scalars().all()
    if allowed is not None:
        cmigs = [c for c in cmigs if c.id in allowed]
    return [
        {
            "cmig_id": c.id,
            "company_name": c.company_name,
            "cnpj": c.cnpj,
            "cpf": c.cpf,
            "eship_active": bool(getattr(c, "eship_active", 0)),
            "eship_configured": bool(c.eship_base_url and c.eship_api_key),
            "eship_base_url": c.eship_base_url or "",
            "eship_warehouse_code": c.eship_warehouse_code or "",
        }
        for c in cmigs
    ]


def _num_origem_key(o: Order) -> str:
    """Chave canônica de conciliação = numeroOrigem enviado ao eShip.

    É o MESMO valor que o service usa ao criar/consultar a ordem no WMS
    (`platform_order_id or str(id)`) — pedidos manuais não têm `platform_order_id`.
    """
    return str(o.platform_order_id or o.id).strip()


@router.get("/cmigs/{cmig_id}/reconciliacao")
async def eship_reconciliation(
    cmig_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Concilia, para uma CMIG, os pedidos que o SISTEMA enviou ao eShip com as ordens que estão
    DE FATO no WMS (consulta ao vivo). Alimenta a tela "Armazenaki" (menu Separação).

    Grupos por `numero_origem` (= platform_order_id, ou `id` no pedido manual):
    - **conciliados** — presentes nos dois lados;
    - **só no sistema** — o sistema marcou como enviado mas a ordem não está no WMS (falha real,
      ou removida via DeleteOrdem); cancelados NÃO entram aqui (o Delete tira do WMS de propósito);
    - **só no eShip** — no WMS sem registro de envio local (raro — ordem criada por fora).

    O WMS é multi-tenant e pode vir `parcial`/`truncado`; nesse caso "só no sistema" é indicativo,
    não definitivo (a tela avisa), pois uma varredura incompleta gera divergência fantasma.
    """
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)

    # LOCAL: definição canônica de "enviado ao eShip" (mesma de service.order_was_pushed /
    # orders.eship_enviada): tem eship_order_id OU status sent/partial. Inclui 'cancelled'
    # (rótulo próprio, não é divergência) e 'failed' (falha de envio — pode ter criado a
    # ordem no WMS mesmo sem devolver id; sem isto viraria falso "só no eShip").
    local_orders = (
        await db.execute(
            select(Order).where(
                Order.cmig_id == cmig_id,
                or_(
                    Order.eship_order_id.isnot(None),
                    Order.eship_dispatch_status.in_(["sent", "partial", "cancelled", "failed"]),
                ),
            ).order_by(Order.eship_dispatch_at.desc().nullslast(), Order.id.desc())
        )
    ).scalars().all()
    local = [
        {
            "order_id": o.id,
            "numero_origem": _num_origem_key(o),
            "data": o.created_at.isoformat() if o.created_at else None,
            "eship_order_id": o.eship_order_id,
            "dispatch_status": o.eship_dispatch_status,
            "cancelado": o.eship_dispatch_status == "cancelled",
            "falhou": o.eship_dispatch_status == "failed" and not o.eship_order_id,
            "nfe_attached": bool(o.eship_nfe_attached),
            "label_attached": bool(o.eship_label_attached),
            "dispatch_error": o.eship_dispatch_error,
            "buyer_name": o.buyer_name,
            "platform": o.platform,
        }
        for o in local_orders
    ]

    # WMS (ao vivo). Best-effort: se o eShip falhar, a tela ainda mostra o lado local.
    wms: list = []
    wms_meta: dict = {}
    wms_error = None
    try:
        res = await service.list_eship_orders(db, cmig_id)
        wms = res.pop("ordens", [])
        wms_meta = res
    except EShipError as e:
        wms_error = str(e)

    # Confiabilidade da varredura do WMS: se caiu, o escopo é indefinido (sem CNPJ/CPF) ou a
    # varredura veio parcial/truncada, "não está no WMS" é INDETERMINADO, não divergência real.
    wms_confiavel = not wms_error and not wms_meta.get("escopo_indefinido") \
        and not wms_meta.get("parcial") and not wms_meta.get("truncado")

    # Conciliação por numero_origem (ambos os lados já são str). Marca cada linha LOCAL e cada
    # ordem do WMS como conciliada (presente nos dois lados) ou não.
    wms_by_num = {w["numero_origem"]: w for w in wms if w.get("numero_origem")}
    local_nums = {x["numero_origem"] for x in local}
    for x in local:
        w = wms_by_num.get(x["numero_origem"])
        x["conciliado"] = w is not None
        x["wms_status"] = w.get("status_desc") if w else None
        x["wms_status_id"] = w.get("status_id") if w else None
    for w in wms:
        w["conciliado"] = w.get("numero_origem") in local_nums

    # LGPD/isolação: o filtro do WMS é por CNPJ/CPF do remetente — se o MESMO documento estiver
    # em duas CMIGs (galpões distintos), as órfãs (sem pedido nesta CMIG) poderiam trazer ordens
    # (e o nome do comprador) de uma CMIG-irmã. Remove das ÓRFÃS qualquer numeroOrigem que resolva
    # para um pedido de OUTRA CMIG (as conciliadas já são desta CMIG; genuinamente externas ficam).
    orfas = [w for w in wms if w.get("numero_origem") and not w["conciliado"]]
    other = set()
    if orfas:
        nums = [w["numero_origem"] for w in orfas]
        by_pid = (
            await db.execute(
                select(Order.platform_order_id).where(
                    Order.platform_order_id.in_(nums), Order.cmig_id != cmig_id
                )
            )
        ).all()
        other.update(r[0] for r in by_pid if r[0])
        int_nums = [int(n) for n in nums if n.isdigit()]
        if int_nums:  # pedidos manuais: numeroOrigem == str(order.id)
            by_id = (
                await db.execute(
                    select(Order.id).where(Order.id.in_(int_nums), Order.cmig_id != cmig_id)
                )
            ).all()
            other.update(str(r[0]) for r in by_id)

    # Lista COMPLETA das ordens do WMS (conciliadas + órfãs desta CMIG), marcadas — é a "lista de
    # todos que estão no eShip". so_eship = só as órfãs (para o contador).
    wms_ordens = [w for w in wms if w["conciliado"] or w["numero_origem"] not in other]
    so_eship = [w for w in wms_ordens if not w["conciliado"]]

    conciliados = [x for x in local if x["conciliado"]]
    # Divergência real só quando o WMS é confiável; cancelado/falhou-sem-id têm rótulo próprio.
    so_sistema = [
        x for x in local
        if not x["conciliado"] and not x["cancelado"] and not x["falhou"] and wms_confiavel
    ]
    cancelados = [x for x in local if x["cancelado"]]
    return {
        "cmig": {"cmig_id": cmig.id, "company_name": cmig.company_name,
                 "eship_active": bool(getattr(cmig, "eship_active", 0))},
        "local": local,
        "wms_ordens": wms_ordens,
        "so_eship": so_eship,
        "wms_confiavel": wms_confiavel,
        "conciliados_count": len(conciliados),
        "so_sistema_count": len(so_sistema),
        "so_eship_count": len(so_eship),
        "cancelados_count": len(cancelados),
        "enviados_count": len([x for x in local if not x["cancelado"]]),
        "wms_count": len(wms_ordens),
        "wms_meta": wms_meta,
        "wms_error": wms_error,
    }


@router.get("/reconciliacao")
async def eship_reconciliation_all(
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Conciliação CONSOLIDADA: todos os pedidos enviados ao eShip × ordens no WMS, de TODAS as
    CMIGs acessíveis ao usuário, numa listagem só. Alimenta o modo "Todas as CMIGs" da Armazenaki.

    Varre o WMS UMA vez por endpoint (base_url+api_key): várias CMIGs podem ser o mesmo lojista
    (mesmo idTipo) — não duplica. Cada linha traz `cmig_id`/`cmig_name`. A conciliação é dirigida
    pelo lado LOCAL (autoritativo: `Order.cmig_id`); o WMS enriquece o status. A confiabilidade do
    WMS é POR GRUPO (uma CMIG cujo grupo veio parcial/truncado não gera divergência-fantasma).
    O filtro por CMIG e por status é aplicado no cliente sobre este payload.
    """
    allowed = await _accessible_cmig_ids(db, current_user)  # None = admin (todas)
    q = select(CMIG)
    if allowed is not None:
        if not allowed:
            return {"cmigs": [], "local": [], "so_eship": [], "conciliados_count": 0,
                    "so_sistema_count": 0, "so_eship_count": 0, "cancelados_count": 0,
                    "enviados_count": 0, "wms_count": 0, "wms_errors": [], "consolidado": True}
        q = q.where(CMIG.id.in_(allowed))
    cmigs = (await db.execute(q.order_by(CMIG.company_name))).scalars().all()
    cmig_by_id = {c.id: c for c in cmigs}
    accessible_ids = set(cmig_by_id)

    # LOCAL: pedidos com marca eShip de TODAS as CMIGs acessíveis (mesmo filtro canônico do
    # per-CMIG). Cada linha carrega o cmig_id/cmig_name reais (Order.cmig_id é autoritativo).
    local_orders = (
        await db.execute(
            select(Order).where(
                Order.cmig_id.in_(accessible_ids),
                or_(
                    Order.eship_order_id.isnot(None),
                    Order.eship_dispatch_status.in_(["sent", "partial", "cancelled", "failed"]),
                ),
            ).order_by(Order.eship_dispatch_at.desc().nullslast(), Order.id.desc())
        )
    ).scalars().all()
    local = [
        {
            "order_id": o.id,
            "cmig_id": o.cmig_id,
            "cmig_name": cmig_by_id[o.cmig_id].company_name if o.cmig_id in cmig_by_id else None,
            "numero_origem": _num_origem_key(o),
            "data": o.created_at.isoformat() if o.created_at else None,
            "eship_order_id": o.eship_order_id,
            "dispatch_status": o.eship_dispatch_status,
            "cancelado": o.eship_dispatch_status == "cancelled",
            "falhou": o.eship_dispatch_status == "failed" and not o.eship_order_id,
            "nfe_attached": bool(o.eship_nfe_attached),
            "label_attached": bool(o.eship_label_attached),
            "dispatch_error": o.eship_dispatch_error,
            "buyer_name": o.buyer_name,
            "platform": o.platform,
        }
        for o in local_orders
    ]

    # WMS (ao vivo, uma varredura por endpoint). Best-effort: erros agregados por grupo.
    res = await service.list_eship_orders_multi(db, cmigs)
    wms = res["ordens"]
    by_cmig = res["by_cmig"]
    wms_errors = res["errors"]

    wms_by_num = {w["numero_origem"]: w for w in wms if w.get("numero_origem")}
    local_nums = {x["numero_origem"] for x in local}
    for x in local:
        w = wms_by_num.get(x["numero_origem"])
        x["conciliado"] = w is not None
        x["wms_status"] = w.get("status_desc") if w else None
        x["wms_status_id"] = w.get("status_id") if w else None
        # Confiabilidade do WMS do GRUPO desta CMIG (não um flag global).
        x["wms_confiavel"] = bool(by_cmig.get(x["cmig_id"], {}).get("confiavel"))

    for w in wms:
        w["conciliado"] = w.get("numero_origem") in local_nums
    # Órfãs: ordens no WMS sem pedido local NAS CMIGs acessíveis.
    orfas = [w for w in wms if w.get("numero_origem") and not w["conciliado"]]
    # LGPD/isolação: remove das órfãs qualquer numeroOrigem que pertença a um pedido de CMIG FORA
    # do escopo do usuário (mesmo lojista/idTipo pode trazer ordem de galpão vizinho).
    fora = set()
    if orfas:
        nums = [w["numero_origem"] for w in orfas]
        by_pid = (
            await db.execute(
                select(Order.platform_order_id, Order.cmig_id).where(
                    Order.platform_order_id.in_(nums)
                )
            )
        ).all()
        for pid, cid in by_pid:
            if pid and cid not in accessible_ids:
                fora.add(pid)
        int_nums = [int(n) for n in nums if n.isdigit()]
        if int_nums:
            by_id = (
                await db.execute(
                    select(Order.id, Order.cmig_id).where(Order.id.in_(int_nums))
                )
            ).all()
            for oid, cid in by_id:
                if cid not in accessible_ids:
                    fora.add(str(oid))

    # Lista COMPLETA das ordens do WMS (conciliadas + órfãs), marcadas. so_eship = só as órfãs.
    wms_ordens = [w for w in wms if w["conciliado"] or w["numero_origem"] not in fora]
    so_eship = [w for w in wms_ordens if not w["conciliado"]]

    conciliados = [x for x in local if x["conciliado"]]
    # Divergência real só quando o WMS do grupo daquela CMIG é confiável.
    so_sistema = [
        x for x in local
        if not x["conciliado"] and not x["cancelado"] and not x["falhou"] and x["wms_confiavel"]
    ]
    cancelados = [x for x in local if x["cancelado"]]
    return {
        "cmigs": [
            {"cmig_id": c.id, "company_name": c.company_name,
             "eship_active": bool(getattr(c, "eship_active", 0))}
            for c in cmigs
        ],
        "local": local,
        "wms_ordens": wms_ordens,
        "so_eship": so_eship,
        "conciliados_count": len(conciliados),
        "so_sistema_count": len(so_sistema),
        "so_eship_count": len(so_eship),
        "cancelados_count": len(cancelados),
        "enviados_count": len([x for x in local if not x["cancelado"]]),
        "wms_count": len(wms_ordens),
        "wms_errors": wms_errors,
        "consolidado": True,
    }


@router.get("/cmigs/{cmig_id}/produtos")
async def list_eship_products_endpoint(
    cmig_id: int,
    page: int = 1,
    all: bool = False,
    refresh: bool = False,
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Lista os produtos cadastrados no eShip (WMS) com info + estoque.

    `all=true`: busca o catálogo inteiro (todas as páginas) para ordenar/filtrar na
    tela (cacheado; `refresh=true` recarrega). Caso contrário, retorna a página `page`.
    """
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        if all:
            return await service.list_all_eship_products(db, cmig_id, force=refresh)
        return await service.list_eship_products(db, cmig_id, page)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/cmigs/{cmig_id}/produtos/export")
async def export_eship_products_endpoint(
    cmig_id: int,
    format: str = Query("pdf", pattern="^(pdf|xlsx)$"),
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Exporta os produtos da empresa (com estoque) em PDF ou Excel."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        data = await service.list_all_eship_products(db, cmig_id)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if data.get("escopo_indefinido"):
        raise HTTPException(
            status_code=400,
            detail="Cadastre o CNPJ/CPF desta empresa para listar/exportar os produtos dela.",
        )
    label = cmig.company_name or f"CMIG #{cmig_id}"
    fname = f"produtos-eship-cmig-{cmig_id}"
    if format == "xlsx":
        return Response(
            content=export.build_xlsx(data, label),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'},
        )
    return Response(
        content=export.build_pdf(data, label),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
    )


@router.get("/cmigs/{cmig_id}/saldo")
async def get_saldo(
    cmig_id: int,
    sku: str | None = None,
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta o saldo de estoque no eShip (WMS = fonte de verdade do físico)."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        return await service.get_saldo_estoque(db, cmig_id, sku)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/cmigs/{cmig_id}/push-products")
async def push_cmig_products_endpoint(
    cmig_id: int,
    current_user: User = Depends(require_role("admin", "ugo", "ac")),
    db: AsyncSession = Depends(get_db),
):
    """Cadastra/atualiza em lote o catálogo da CMIG no eShip (WMS). Idempotente por SKU."""
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    await _assert_cmig_access(db, cmig, current_user)
    try:
        result = await service.push_cmig_products(db, cmig_id)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Produtos enviados ao eShip", **result}


@router.get("/configs")
async def list_configs(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os galpões com a respectiva config eShip (key mascarada)."""
    warehouses = (await db.execute(select(Warehouse).order_by(Warehouse.name))).scalars().all()
    cfgs = (await db.execute(select(EShipConfig))).scalars().all()
    by_wh = {c.warehouse_id: c for c in cfgs}
    return [_serialize(wh, by_wh.get(wh.id)) for wh in warehouses]


@router.put("/configs/{warehouse_id}")
async def upsert_config(
    warehouse_id: int,
    body: EShipConfigIn,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    wh = (
        await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    ).scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    cfg = await get_config(db, warehouse_id)
    if not cfg:
        cfg = EShipConfig(warehouse_id=warehouse_id)
        db.add(cfg)

    if body.base_url is not None:
        cfg.base_url = body.base_url.strip()
    if body.api_key:  # só atualiza se vier preenchida
        cfg.api_key = body.api_key.strip()
    cfg.is_active = body.is_active

    await db.commit()
    await db.refresh(cfg)
    return _serialize(wh, cfg)


async def _load_order(db: AsyncSession, order_id: int, user: User) -> Order:
    """Carrega o pedido e valida que o usuário tem acesso à CMIG dona dele."""
    order = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if user.role != "admin":
        cmig = None
        if order.cmig_id:
            cmig = (
                await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))
            ).scalar_one_or_none()
        if not cmig:
            raise HTTPException(status_code=403, detail="Pedido sem CMIG acessível")
        await _assert_cmig_access(db, cmig, user)
    return order


@router.get("/orders/{order_id}/preview-ordem")
async def preview_ordem_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Prévia (debug) do webServicePostOrdem que o envio faria — payload + curl, sem executar."""
    order = await _load_order(db, order_id, current_user)
    try:
        return await service.preview_ordem(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/orders/{order_id}/eship-ordem")
async def get_eship_ordem(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe da ordem GRAVADA no eShip — alimenta o modal de conferência do pedido.

    Devolve o código da ordem (o que o usuário confere no painel do WMS), o `numeroOrigem`
    (por onde TODAS as operações endereçam a ordem), o estado do despacho, o motivo do último
    erro e a resposta CRUA do WMS. A resposta crua é pesada, por isso fica neste endpoint e
    não na serialização da lista de pedidos.
    """
    order = await _load_order(db, order_id, current_user)
    return {
        "order_id": order.id,
        "enviada": service.order_was_pushed(order),
        "eship_order_id": order.eship_order_id,
        "numero_origem": order.platform_order_id or str(order.id),
        "dispatch_status": order.eship_dispatch_status,
        "dispatch_error": order.eship_dispatch_error,
        "dispatch_attempts": order.eship_dispatch_attempts or 0,
        "nfe_attached": bool(order.eship_nfe_attached),
        "label_attached": bool(order.eship_label_attached),
        "last_response": order.eship_last_response,
    }


@router.get("/orders/{order_id}/eship-anexos")
async def get_eship_anexos(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Arquivos ANEXADOS na ordem, consultados no eShip (webServiceGetAnexosOrdem).

    É a conferência que fecha o ciclo: mostra o que o WMS realmente recebeu (XML da NF-e, DANFE,
    etiqueta), em vez de confiar no selo local.
    """
    order = await _load_order(db, order_id, current_user)
    try:
        return {"anexos": await service.get_anexos(db, order)}
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/orders/{order_id}/send")
async def send_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Envio completo ao eShip: Ordem + NF-e (XML) + Etiqueta (ZPL e PDF).

    Idempotente e tolerante a parcial — reenviar completa só o que ficou pendente.
    """
    order = await _load_order(db, order_id, current_user)
    try:
        result = await service.send_order_full(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "message": "Envio ao eShip processado",
        **result,
        "eship_order_id": order.eship_order_id,
        "nfe_attached": bool(order.eship_nfe_attached),
        "label_attached": bool(order.eship_label_attached),
        "dispatch_status": order.eship_dispatch_status,
    }


@router.post("/orders/{order_id}/sync")
async def sync_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Sincroniza o status de um pedido específico com o eShip."""
    order = await _load_order(db, order_id, current_user)
    try:
        changed = await service.sync_order_status(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Status sincronizado", "changed": changed, "status": order.shipment_status}


@router.post("/orders/{order_id}/cancel")
async def cancel_order_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Cancela a ordem no eShip."""
    order = await _load_order(db, order_id, current_user)
    try:
        resp = await service.cancel_order(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"message": "Cancelamento enviado ao eShip", "response": resp}


@router.get("/orders/{order_id}/falhas")
async def order_falhas_endpoint(
    order_id: int,
    current_user: User = Depends(require_role("admin", "ugo")),
    db: AsyncSession = Depends(get_db),
):
    """Consulta falhas de processamento da ordem no eShip."""
    order = await _load_order(db, order_id, current_user)
    try:
        resp = await service.get_falhas(db, order)
    except EShipError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"falhas": resp}

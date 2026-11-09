"""Importação de catálogo do Bling → CMIG ou PG (ADR-0040 Fase 2).

Direção LEITURA Bling→sistema. Importa categorias/produtos/kits; **estoque NÃO é importado**
(SSOT local, ADR-0004/0019 → stock_quantity=0). Imagens são BAIXADAS (as URLs S3 do Bling são
assinadas e EXPIRAM). Dedup/re-sync por `bling_product_id` (senão por SKU). Upsert: on_conflict
`skip` (não sobrescreve) | `update` (atualiza in-place).

Job ASSÍNCRONO (molde competitor_analysis / ADR-0011): `asyncio.create_task` + `task_db()` por
worker (NUNCA o `db` do request) + progresso/contadores persistidos por produto. O worker CAPTURA
toda exceção (o `bling_service.request` levanta HTTPException em 4xx/5xx — num task isso mata em
silêncio) e grava `status='error'`.

Reusos: `services.product_import` (norm_ncm/norm_cest/resolve_or_create_category_id),
`services.image_upload` (sniff_image_ext/save_image/MAX_IMAGE_BYTES), `services.bling_service.request`
(throttle 3req/s + 401→refresh→replay), `services.product_mode.assert_product_group_allowed`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import func, select

from database import task_db
from models.bling import BlingImportJob
from models.cmig import CMIG, CMIGProduct, CMIGProductComponent, CMIGProductImage
from models.product import CatalogProduct, CatalogProductComponent, CatalogProductImage
from services import bling_service as bling
from services.image_upload import MAX_IMAGE_BYTES, save_image, sniff_image_ext
from services.product_import import norm_cest, norm_ncm, resolve_or_create_category_id

logger = logging.getLogger(__name__)

PAGE_LIMIT = 100
MAX_PAGES = 100                       # teto de segurança (até 10k itens)
IMG_DIR = "static/uploads/bling-import"
_BG: set = set()


# ── Leitura (síncrona — preview) ────────────────────────────────────────────────

async def list_categories(db, cmig_id: int) -> list[dict]:
    out: list[dict] = []
    pagina = 1
    while pagina <= MAX_PAGES:
        data = await bling.request(db, cmig_id, "GET", "/categorias/produtos",
                                   params={"pagina": pagina, "limite": PAGE_LIMIT})
        items = (data or {}).get("data") or []
        for c in items:
            out.append({"id": c.get("id"), "descricao": c.get("descricao"),
                        "pai": (c.get("categoriaPai") or {}).get("id") or 0})
        if len(items) < PAGE_LIMIT:
            break
        pagina += 1
    return out


async def list_products(db, cmig_id: int, pagina: int = 1, limite: int = PAGE_LIMIT,
                        id_categoria: int | None = None) -> dict:
    params: dict = {"pagina": max(1, pagina), "limite": min(max(1, limite), PAGE_LIMIT)}
    if id_categoria:
        params["idCategoria"] = id_categoria
    data = await bling.request(db, cmig_id, "GET", "/produtos", params=params)
    items = (data or {}).get("data") or []
    produtos = [{
        "id": p.get("id"), "nome": p.get("nome"), "codigo": p.get("codigo"),
        "preco": p.get("preco"), "formato": p.get("formato"), "situacao": p.get("situacao"),
        "idProdutoPai": p.get("idProdutoPai"), "imagemURL": p.get("imagemURL"),
    } for p in items]
    return {"pagina": params["pagina"], "itens": produtos, "tem_mais": len(items) >= params["limite"]}


async def get_detail(db, cmig_id: int, bling_id) -> dict:
    data = await bling.request(db, cmig_id, "GET", f"/produtos/{bling_id}")
    return (data or {}).get("data") or {}


# ── Mapeamento Bling → campos do sistema ────────────────────────────────────────

def _dec(v):
    try:
        d = Decimal(str(v))
        return d if d != 0 else d
    except (InvalidOperation, TypeError, ValueError):
        return None


def _common_fields(detail: dict) -> dict:
    """Campos agnósticos de destino (CMIG/PG) a partir do DETALHE do produto Bling."""
    trib = detail.get("tributacao") or {}
    dim = detail.get("dimensoes") or {}
    desc = (detail.get("descricaoCurta") or detail.get("descricaoComplementar") or "") or None
    origem = trib.get("origem")
    try:
        origin = int(origem) if origem not in (None, "") else 0
        if origin < 0 or origin > 8:
            origin = 0
    except (TypeError, ValueError):
        origin = 0
    return {
        "sku": (detail.get("codigo") or "").strip() or None,
        "title": (detail.get("nome") or "").strip()[:255] or "(sem nome)",
        "description": (desc[:4000] if desc else None),
        "brand": (detail.get("marca") or "").strip()[:100] or None,
        "ean": (detail.get("gtin") or "").strip()[:14] or None,
        "cost_price": _dec(detail.get("precoCusto")) or Decimal("0"),
        "suggested_price": _dec(detail.get("preco")),
        "weight_kg": _dec(detail.get("pesoBruto")) or _dec(detail.get("pesoLiquido")),
        "height_cm": _dec(dim.get("altura")),
        "width_cm": _dec(dim.get("largura")),
        "length_cm": _dec(dim.get("profundidade")),
        "ncm": _safe_norm(norm_ncm, trib.get("ncm")),
        "cest": _safe_norm(norm_cest, trib.get("cest")),
        "origin": origin,
        "_categoria": detail.get("categoria") or {},     # {id, descricao}
        "_bling_id": str(detail.get("id")) if detail.get("id") is not None else None,
    }


def _safe_norm(fn, v):
    try:
        return fn(v)
    except Exception:  # noqa: BLE001 — NCM/CEST fora do padrão não derruba a linha; fica nulo
        return None


def _image_links(detail: dict) -> list[str]:
    midia = detail.get("midia") or {}
    imgs = midia.get("imagens") or {}
    out: list[str] = []
    for grupo in ("internas", "externas"):
        for it in (imgs.get(grupo) or []):
            link = it.get("link") if isinstance(it, dict) else None
            if link:
                out.append(link)
    return out


def _bling_qty(detail: dict) -> int | None:
    """Quantidade de estoque do Bling (p/ baseline). Prefere saldo FÍSICO; cai no virtual. Devolve
    **None quando NÃO há campo de saldo** no detalhe — "sem dado" ≠ "zero": como o baseline reseta o
    saldo, zerar por campo ausente apagaria estoque real. None → o produto é pulado do baseline."""
    est = detail.get("estoque") or {}
    for k in ("saldoFisicoTotal", "saldoVirtualTotal", "saldoFisico", "saldoVirtual", "saldo"):
        v = est.get(k)
        if v is not None:
            try:
                return max(0, int(float(v)))
            except (TypeError, ValueError):
                pass
    return None


def _kit_components(detail: dict) -> list[dict]:
    """[{bling_id, qty}] a partir de estrutura.componentes (shape tolerante)."""
    est = detail.get("estrutura") or {}
    comps = est.get("componentes") or []
    out: list[dict] = []
    for c in comps:
        if not isinstance(c, dict):
            continue
        prod = c.get("produto") or {}
        bid = prod.get("id") if isinstance(prod, dict) else None
        bid = bid or c.get("idProduto") or c.get("id")
        if bid is None:
            continue
        try:
            qty = int(c.get("quantidade") or c.get("qtd") or 1)
        except (TypeError, ValueError):
            qty = 1
        out.append({"bling_id": str(bid), "qty": max(1, qty)})
    return out


# ── Download de imagem (baixa no import; URL S3 do Bling expira) ─────────────────

async def _url_host_publico(link: str) -> bool:
    """Anti-SSRF: True só se o host resolve para IP PÚBLICO (recusa loopback/privado/link-local/IMDS).
    Defesa em profundidade — a fonte é o ERP do próprio dono (OAuth), mas um link/redirect malicioso
    não pode fazer o worker bater em serviço interno do servidor."""
    import ipaddress
    from urllib.parse import urlparse
    try:
        u = urlparse(link)
    except Exception:  # noqa: BLE001
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        infos = await asyncio.get_event_loop().getaddrinfo(u.hostname, None)
    except Exception:  # noqa: BLE001 — DNS falhou → não baixa
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


async def _download_images(links: list[str]) -> list[str]:
    urls: list[str] = []
    if not links:
        return urls
    # follow_redirects=False: um 302 p/ IP interno NÃO é seguido (anti-SSRF via redirect).
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as c:
        for link in links[:12]:                       # teto por produto
            try:
                if not await _url_host_publico(link):  # host interno/privado → pula
                    continue
                r = await c.get(link)
                if r.status_code != 200:               # inclui 3xx (não seguimos redirect)
                    continue
                data = r.content
                if not data or len(data) > MAX_IMAGE_BYTES:
                    continue
                ext = sniff_image_ext(data)             # valida por magic byte (ignora content-type)
                if not ext:
                    continue
                urls.append(save_image(data, IMG_DIR, ext))
            except Exception as e:  # noqa: BLE001 — imagem que falha não derruba o produto
                logger.warning("[bling-import] imagem falhou: %s", e)
    return urls


# ── Upsert do produto ───────────────────────────────────────────────────────────

async def _find_existing(db, target: str, cmig_id: int, warehouse_id, bling_id, sku):
    Model = CMIGProduct if target == "cmig" else CatalogProduct

    def _scope(q):
        # ESCOPO obrigatório (ADR-0026): CMIG por cmig_id; PG por warehouse_id — nunca casar/atualizar
        # produto de outra CMIG/galpão por um bling_product_id numericamente igual.
        if target == "cmig":
            return q.where(CMIGProduct.cmig_id == cmig_id)
        return q.where(CatalogProduct.warehouse_id == warehouse_id)

    if bling_id:
        row = (await db.execute(_scope(select(Model).where(Model.bling_product_id == bling_id)))).scalars().first()
        if row:
            return row
    if sku:
        col = Model.sku_cmig if target == "cmig" else Model.sku
        row = (await db.execute(_scope(select(Model).where(func.lower(col) == sku.lower())))).scalars().first()
        if row:
            return row
    return None


async def _upsert_product(db, *, target, cmig_id, warehouse_id, detail, on_conflict, want_images):
    """Cria/atualiza UM produto. Retorna ('created'|'updated'|'skipped', obj|None)."""
    f = _common_fields(detail)
    if not f["sku"]:
        return "skipped", None                          # produto sem código não entra
    existing = await _find_existing(db, target, cmig_id, warehouse_id, f["_bling_id"], f["sku"])
    if existing is not None and on_conflict == "skip":
        return "skipped", existing
    created = existing is None

    # categoria interna (reusa helper warehouse-scoped)
    cat = f["_categoria"]
    cat_id = None
    if cat and cat.get("descricao"):
        cat_id, _ = await resolve_or_create_category_id(db, cat.get("descricao"), warehouse_id)

    if target == "cmig":
        obj = existing or CMIGProduct(cmig_id=cmig_id)
        obj.sku_cmig = f["sku"]
    else:
        obj = existing or CatalogProduct(warehouse_id=warehouse_id)
        obj.sku = f["sku"]
    obj.title = f["title"]
    obj.description = f["description"]
    obj.brand = f["brand"]
    obj.ean = f["ean"]
    obj.cost_price = f["cost_price"]
    obj.suggested_price = f["suggested_price"]
    obj.weight_kg = f["weight_kg"]
    obj.height_cm = f["height_cm"]
    obj.width_cm = f["width_cm"]
    obj.length_cm = f["length_cm"]
    obj.ncm = f["ncm"]
    obj.cest = f["cest"]
    obj.origin = f["origin"]
    if cat_id:
        obj.category_id = cat_id
    obj.bling_product_id = f["_bling_id"]
    if created:
        obj.stock_quantity = 0          # estoque NÃO importado (SSOT local). SÓ no create: no update,
        db.add(obj)                      # NUNCA zera o saldo REAL de um produto que já existe.
    await db.flush()

    # imagens (só quando criando, ou atualizando sem imagem ainda — não duplica)
    if want_images:
        ImgModel = CMIGProductImage if target == "cmig" else CatalogProductImage
        # FK da tabela de imagem: CMIGProductImage.cmig_product_id × CatalogProductImage.PRODUCT_ID
        # (nomes diferentes! usar 'catalog_product_id' aqui estourava AttributeError e derrubava TODO
        # produto PG com imagem).
        fk = "cmig_product_id" if target == "cmig" else "product_id"
        has_img = (await db.execute(
            select(func.count()).select_from(ImgModel).where(getattr(ImgModel, fk) == obj.id)
        )).scalar() or 0
        if not has_img:
            urls = await _download_images(_image_links(detail))
            for i, u in enumerate(urls):
                db.add(ImgModel(**{fk: obj.id, "url": u, "sort_order": i, "is_primary": i == 0}))
            await db.flush()

    return ("created" if created else "updated"), obj


# ── Job assíncrono ──────────────────────────────────────────────────────────────

async def start_import(db, *, cmig_id: int, target: str, on_conflict: str, options: dict,
                       user_id: int | None) -> BlingImportJob:
    """Valida (escopo+product_mode) e agenda o job. target='cmig'|'pg'; on_conflict='skip'|'update'."""
    if target not in ("cmig", "pg"):
        raise ValueError("target deve ser 'cmig' ou 'pg'")
    if on_conflict not in ("skip", "update"):
        raise ValueError("on_conflict deve ser 'skip' ou 'update'")
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise ValueError("CMIG não encontrada")
    # Enforcement product_mode/work_type (ADR-0024/0029) — ponto único, fail-loud.
    from models.warehouse import Warehouse
    from services.product_mode import assert_product_group_allowed
    wh = None
    if cmig.warehouse_id:
        wh = (await db.execute(select(Warehouse).where(Warehouse.id == cmig.warehouse_id))).scalar_one_or_none()
    assert_product_group_allowed(cmig, wh, is_pg=(target == "pg"), is_cmig=(target == "cmig"))

    job = BlingImportJob(cmig_id=cmig_id, target=target, on_conflict=on_conflict,
                         options_json=json.dumps(options or {}), requested_by=user_id, status="running")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    t = asyncio.create_task(_run(job.id))
    _BG.add(t)
    t.add_done_callback(_BG.discard)
    return job


async def _progress(job_id: int, step: str, **counts) -> None:
    async with task_db() as db:
        job = (await db.execute(select(BlingImportJob).where(BlingImportJob.id == job_id))).scalar_one_or_none()
        if job:
            job.progress_step = step[:200]
            for k, v in counts.items():
                setattr(job, k, v)
            await db.commit()


async def _run(job_id: int) -> None:
    created = updated = skipped = failed = 0
    errors: list[dict] = []
    try:
        async with task_db() as db:
            job = (await db.execute(select(BlingImportJob).where(BlingImportJob.id == job_id))).scalar_one_or_none()
            if not job:
                return
            cmig_id, target, on_conflict = job.cmig_id, job.target, job.on_conflict
            user_id = job.requested_by
            opts = json.loads(job.options_json or "{}")
            cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
            warehouse_id = cmig.warehouse_id if cmig else None

        want_images = bool(opts.get("images", True))
        want_kits = bool(opts.get("kits", True))
        want_stock = bool(opts.get("import_stock", False))   # importar estoque = evento baseline (opt-in)
        stock_counts: dict[int, int] = {}
        # Seleção: lista de ids do Bling (preview marcou) OU 'tudo' (varre as páginas).
        selected = opts.get("product_ids")

        # Coleta os ids a importar (se não veio seleção, varre /produtos).
        async with task_db() as db:
            if selected:
                ids = [str(x) for x in selected]
            else:
                ids = []
                pagina = 1
                while pagina <= MAX_PAGES:
                    page = await list_products(db, cmig_id, pagina=pagina, limite=PAGE_LIMIT)
                    ids += [str(p["id"]) for p in page["itens"] if p.get("id") is not None]
                    if not page["tem_mais"]:
                        break
                    pagina += 1
        await _progress(job_id, f"Encontrados {len(ids)} produtos", total=len(ids))

        # 2 PASSADAS: 1ª simples/variação; 2ª kits (componentes precisam existir antes).
        kit_ids: list[str] = []
        for idx, bid in enumerate(ids, 1):
            try:
                async with task_db() as db:
                    detail = await get_detail(db, cmig_id, bid)
                    if not detail:
                        failed += 1
                        errors.append({"bling_id": bid, "motivo": "detalhe vazio"})
                        continue
                    comps = _kit_components(detail)
                    outcome, _obj = await _upsert_product(
                        db, target=target, cmig_id=cmig_id, warehouse_id=warehouse_id,
                        detail=detail, on_conflict=on_conflict, want_images=want_images)
                    pid = _obj.id if _obj is not None else None   # capturado dentro do bloco (atachado)
                    await db.commit()
                # coleta o estoque Bling (não-kit, não-pulado) p/ o inventário baseline no fim.
                # None = Bling não informou saldo → NÃO reseta (não vira item de baseline).
                if want_stock and pid and outcome != "skipped" and not comps:
                    _q = _bling_qty(detail)
                    if _q is not None:
                        stock_counts[pid] = _q
                # só liga componentes de kit que foi criado/atualizado (pular = não mexer no existente)
                if comps and want_kits and outcome != "skipped":
                    kit_ids.append(bid)
                if outcome == "created":
                    created += 1
                elif outcome == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:  # noqa: BLE001 — erro de 1 produto não derruba o lote
                failed += 1
                errors.append({"bling_id": bid, "motivo": str(e)[:200]})
                logger.warning("[bling-import %s] produto %s falhou: %s", job_id, bid, e)
            if idx % 5 == 0 or idx == len(ids):
                await _progress(job_id, f"Produtos {idx}/{len(ids)}",
                                created_count=created, updated_count=updated,
                                skipped_count=skipped, failed_count=failed)

        # 2ª passada: componentes dos kits (resolve por bling_product_id dentro do destino/escopo)
        for bid in (kit_ids if want_kits else []):
            try:
                async with task_db() as db:
                    detail = await get_detail(db, cmig_id, bid)
                    res = await _link_kit(db, target, cmig_id, bid, _kit_components(detail),
                                          warehouse_id=warehouse_id)
                    await db.commit()
                # Falha alto (PG): kit cujo(s) componente(s) não foram importados fica chapado — reporta.
                if res and res.get("missing"):
                    errors.append({"bling_id": bid,
                                   "motivo": f"kit não vinculado: componente(s) ausente(s) no galpão: {res['missing']}"})
            except Exception as e:  # noqa: BLE001
                errors.append({"bling_id": bid, "motivo": f"kit: {str(e)[:150]}"})
                logger.warning("[bling-import %s] kit %s falhou: %s", job_id, bid, e)

        # ESTOQUE (opt-in): cria UM inventário BASELINE finalizado resetando o saldo = qtd Bling
        # (SSOT-correto, ADR-0004/0019 — não escreve stock_quantity direto). Kits excluídos (ADR-0023).
        if want_stock and stock_counts:
            await _progress(job_id, "Aplicando estoque (inventário baseline)…")
            try:
                async with task_db() as db:
                    from services.inventory_service import import_stock_baseline
                    await import_stock_baseline(db, target=target, cmig_id=cmig_id,
                                                warehouse_id=warehouse_id, counts=stock_counts, user_id=user_id)
            except Exception as e:  # noqa: BLE001 — falha do estoque não invalida o catálogo já importado
                errors.append({"estoque": f"falha ao aplicar inventário baseline: {str(e)[:200]}"})
                logger.exception("[bling-import %s] inventário baseline falhou", job_id)

        async with task_db() as db:
            job = (await db.execute(select(BlingImportJob).where(BlingImportJob.id == job_id))).scalar_one_or_none()
            if job:
                job.status = "done"
                job.created_count, job.updated_count = created, updated
                job.skipped_count, job.failed_count = skipped, failed
                job.progress_step = "Concluído"
                job.result_json = json.dumps({"errors": errors[:200]})
                from datetime import UTC, datetime
                job.finished_at = datetime.now(UTC)
                await db.commit()
    except Exception as e:  # noqa: BLE001 — qualquer coisa inesperada vira status=error (nunca morre calado)
        logger.exception("[bling-import %s] falhou", job_id)
        try:
            async with task_db() as db:
                job = (await db.execute(select(BlingImportJob).where(BlingImportJob.id == job_id))).scalar_one_or_none()
                if job:
                    from datetime import UTC, datetime
                    job.status = "error"
                    job.error = str(e)[:2000]
                    job.finished_at = datetime.now(UTC)
                    await db.commit()
        except Exception:  # noqa: BLE001
            pass


async def _link_kit(db, target, cmig_id, kit_bling_id, components, *, warehouse_id=None):
    """Liga os componentes ao kit (ADR-0023 — o composto vive no produto, estoque derivado na leitura).

    - **CMIG** → `CMIGProductComponent`, escopo `cmig_id` (comportamento histórico intocado).
    - **PG** → `CatalogProductComponent`, escopo **`warehouse_id`** (PG é global, sem cmig_id, e
      `bling_product_id` NÃO é único cross-galpão — resolver só pelo bling_id colaria componente do
      galpão errado).

    No ramo PG **falha alto**: se QUALQUER componente não existir no galpão, NÃO marca o kit como
    composto (deixa chapado) e devolve-o em `missing` — um kit meio-ligado calcularia `composite_stock`
    ERRADO (ele ignora componente não resolvido e reportaria montável maior que o real). Guard
    `child.id != kit.id` (auto-referência de dado sujo). Retorna `{'linked': bool, 'missing': [bling_id]}`
    no ramo PG; `None` no ramo CMIG (compat)."""
    if not components:
        return None

    if target == "cmig":
        kit = (await db.execute(
            select(CMIGProduct).where(CMIGProduct.cmig_id == cmig_id,
                                      CMIGProduct.bling_product_id == str(kit_bling_id))
        )).scalars().first()
        if not kit:
            return None
        kit.is_composite = True
        kit.stock_quantity = 0                                # kit = estoque derivado (ADR-0023)
        # limpa componentes antigos (re-sync) e recria
        for old in (await db.execute(
            select(CMIGProductComponent).where(CMIGProductComponent.composite_id == kit.id)
        )).scalars().all():
            db.delete(old)
        await db.flush()
        for comp in components:
            child = (await db.execute(
                select(CMIGProduct).where(CMIGProduct.cmig_id == cmig_id,
                                          CMIGProduct.bling_product_id == comp["bling_id"])
            )).scalars().first()
            if child and child.id != kit.id:
                db.add(CMIGProductComponent(composite_id=kit.id, cmig_product_id=child.id, quantity=comp["qty"]))
        await db.flush()
        return None

    if target == "pg":
        kit = (await db.execute(
            select(CatalogProduct).where(CatalogProduct.warehouse_id == warehouse_id,
                                         CatalogProduct.bling_product_id == str(kit_bling_id))
        )).scalars().first()
        if not kit:
            return {"linked": False, "missing": []}
        # resolve TODOS os componentes ANTES de decidir — só marca composto se todos existirem.
        resolved: list[tuple[int, int]] = []
        missing: list[str] = []
        for comp in components:
            child = (await db.execute(
                select(CatalogProduct).where(CatalogProduct.warehouse_id == warehouse_id,
                                             CatalogProduct.bling_product_id == str(comp["bling_id"]))
            )).scalars().first()
            if child and child.id != kit.id:
                resolved.append((child.id, comp["qty"]))
            else:
                missing.append(str(comp["bling_id"]))
        # limpa componentes antigos (re-sync) sempre, antes de decidir o estado final
        for old in (await db.execute(
            select(CatalogProductComponent).where(CatalogProductComponent.composite_id == kit.id)
        )).scalars().all():
            db.delete(old)
        await db.flush()
        if missing:
            kit.is_composite = False   # falha alto: kit com componente faltando NÃO vira composto
            await db.flush()
            return {"linked": False, "missing": missing}
        for child_id, qty in resolved:
            db.add(CatalogProductComponent(composite_id=kit.id, component_id=child_id, quantity=qty))
        kit.is_composite = True
        kit.stock_quantity = 0                                # kit = estoque derivado (ADR-0023)
        await db.flush()
        return {"linked": True, "missing": []}

    return None

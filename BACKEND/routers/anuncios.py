"""
Gestão de Anúncios — fluxo AC-centrado.
Cada anúncio (ProductListing) pode estar vinculado a CMIGProduct OU CatalogProduct OU sem vínculo.
"""

import json as _json
import logging
import os as _os
import shutil as _shutil
import uuid as _uuid_mod
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database import get_db
from dependencies import get_current_user
from models.cmig import CMIGAdministrator, CMIGProduct, CMIGProductImage, CMIGProductVariant
from models.integration import MarketplaceAccount
from models.product import CatalogProduct, ProductListing
from models.user import User
from services import ml_service


def _is_valid_ean13(s: str | None) -> bool:
    """True se `s` é um EAN-13 válido (13 dígitos numéricos + checksum mod-10 correto).

    Algoritmo idêntico ao do `FRONTEND/src/utils/ean.js:ean13Checksum`:
    soma posições pares × 1 e ímpares × 3 (índice 0-based), dígito verificador
    = (10 − soma mod 10) mod 10.
    """
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) != 13 or not s.isdigit():
        return False
    sum_ = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(s[:12]))
    return (10 - (sum_ % 10)) % 10 == int(s[12])


def _absolutize_image_url(url: str) -> str:
    """Converte URL relativa de imagem (/static/...) em URL absoluta usando
    PUBLIC_BASE_URL. Necessário para enviar pro ML/Shopee que precisam baixar a imagem.
    Se já é absoluta (http/https) ou se PUBLIC_BASE_URL não está configurado,
    retorna a URL original.
    """
    if not url or not isinstance(url, str):
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = (get_settings().PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        return url  # dev sem PUBLIC_BASE_URL — ML rejeitará, mas é esperado em dev
    if not url.startswith("/"):
        url = "/" + url
    return f"{base}{url}"

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload-image")
async def upload_anuncio_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload de imagem para usar em anúncios. Retorna URL pública."""
    ext = _os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(
            status_code=400, detail="Tipo de arquivo não permitido. Use JPG, PNG, WEBP ou GIF."
        )
    filename = f"{_uuid_mod.uuid4().hex}{ext}"
    dest_dir = "static/uploads/anuncio-images"
    _os.makedirs(dest_dir, exist_ok=True)
    with open(f"{dest_dir}/{filename}", "wb") as out:
        _shutil.copyfileobj(file.file, out)
    return {"url": f"/static/uploads/anuncio-images/{filename}"}


# ── helpers ────────────────────────────────────────────────────────────────────


def _is_processing_placeholder_url(url: str | None) -> bool:
    """True se a URL é o placeholder do ML enquanto a imagem é processada
    (`statics/processing-image/...`). Acontece logo após o POST e some quando
    o ML termina o processing — pode demorar de segundos a minutos."""
    if not url:
        return False
    return "processing-image" in url.lower()


def _pictures_to_json(ml_pictures: list | None, fallback_urls: list[str] | None) -> str | None:
    """Normaliza pictures vindas da resposta do ML para o formato {id, url} salvo em pictures_json.

    Why: o ML devolve pictures: [{id, url, secure_url}] ao criar/buscar item, mas o
    create do listing antes não persistia isso — o grid de fotos da tela de gestão
    consome pictures_json, então sem persistir a tela ficava em branco.

    Gotcha: logo após POST /items, o ML retorna pictures com URLs do placeholder
    `statics/processing-image/1.0.0/O-PT.jpg` (todas iguais, sem a imagem real).
    Detectamos isso e usamos `fallback_urls` (URLs originais que o vendedor mandou)
    como fonte alternativa, mantendo os `id`s do ML — quando o usuário clicar em
    "Atualizar fotos", refazemos GET /items/{id} e gravamos URLs reais.
    """
    pics: list[dict] = []
    all_processing = True
    for pic in ml_pictures or []:
        url = (pic.get("secure_url") or pic.get("url") or "").replace("http://", "https://")
        if url:
            pics.append({"id": pic.get("id", ""), "url": url})
            if not _is_processing_placeholder_url(url):
                all_processing = False

    # Se o ML devolveu pictures mas TODAS são placeholders de processing,
    # preferimos as fallback_urls (URLs reais que o vendedor enviou).
    # Mantemos os `id`s do ML alinhando por posição quando possível.
    if pics and all_processing and fallback_urls:
        merged: list[dict] = []
        for i, u in enumerate(fallback_urls):
            if not u:
                continue
            pid = pics[i]["id"] if i < len(pics) else ""
            merged.append({"id": pid, "url": u})
        if merged:
            pics = merged

    if not pics and fallback_urls:
        pics = [{"id": "", "url": u} for u in fallback_urls if u]
    return _json.dumps(pics, ensure_ascii=False) if pics else None


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity entre palavras de dois títulos (case-insensitive)."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _build_fiscal_payload_from_product(
    product, sku: str, cmig_crt: int | None, fiscal_overrides: dict | None = None
) -> dict | None:
    """Monta o payload de fiscal_information a partir do produto + overrides do fiscal_json.

    Retorna None se não houver dados fiscais mínimos para cadastrar (sem NCM,
    o ML rejeita com `tax_information.ncm is required` — error_code 10027).
    """
    overrides = fiscal_overrides or {}

    ncm = overrides.get("ncm") or getattr(product, "ncm", None)
    if not ncm:
        return None  # sem NCM o ML rejeita — não tenta

    csosn = overrides.get("csosn") or getattr(product, "csosn", None)
    if not csosn and cmig_crt in (1, 2):
        csosn = "102"  # default Simples Nacional

    return ml_service.build_fiscal_information_payload(
        sku=sku,
        title=product.title or "",
        cost=float(product.cost_price) if getattr(product, "cost_price", None) else 0.0,
        is_composite=getattr(product, "is_composite", False),
        measurement_unit="UN",
        ncm=ncm,
        cest=overrides.get("cest") or getattr(product, "cest", None),
        ean=overrides.get("ean") or overrides.get("gtin") or getattr(product, "ean", None),
        origin=overrides.get("origin") if "origin" in overrides else getattr(product, "origin", None),
        csosn=csosn,
        weight_kg=float(product.weight_kg) if getattr(product, "weight_kg", None) else None,
    )


def _parse_fiscal_json(raw) -> dict:
    """Aceita string JSON ou dict; retorna dict (vazio em erro)."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return _json.loads(raw) or {}
        except Exception:
            return {}
    return {}


async def _resolve_cmig_crt(account: MarketplaceAccount, db: AsyncSession) -> int | None:
    """Retorna o CRT (regime tributário) da CMIG vinculada à conta, ou None.

    Usado como fallback do CSOSN no envio fiscal ao ML quando o produto não tem
    csosn explícito. CRT 1/2 (Simples Nacional) → CSOSN 102; CRT 3 (Normal) → CST.
    """
    if not getattr(account, "cmig_id", None):
        return None
    from models.fiscal import CMIGFiscalConfig

    cfg = (
        await db.execute(
            select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == account.cmig_id)
        )
    ).scalar_one_or_none()
    return cfg.crt if cfg else None


async def _get_account_or_403(account_id: int, user: User, db: AsyncSession) -> MarketplaceAccount:
    result = await db.execute(
        select(MarketplaceAccount)
        .options(selectinload(MarketplaceAccount.administrators))
        .where(MarketplaceAccount.id == account_id, MarketplaceAccount.is_active == True)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")
    if user.role not in ("admin", "ugo"):
        admin_ids = {a.user_id for a in account.administrators}
        if user.id not in admin_ids:
            # Fallback: colaborador CMIG tem acesso a contas vinculadas à sua CMIG
            has_cmig_access = False
            if account.cmig_id:
                r = await db.execute(
                    select(CMIGAdministrator).where(
                        CMIGAdministrator.user_id == user.id,
                        CMIGAdministrator.cmig_id == account.cmig_id,
                    )
                )
                has_cmig_access = r.scalar_one_or_none() is not None
            if not has_cmig_access:
                raise HTTPException(status_code=403, detail="Sem acesso a esta conta de marketplace")
    return account


async def _get_listing_or_404(listing_id: int, user: User, db: AsyncSession) -> ProductListing:
    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.account).selectinload(MarketplaceAccount.administrators),
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(ProductListing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
    if user.role not in ("admin", "ugo"):
        admin_ids = {a.user_id for a in listing.account.administrators}
        if user.id not in admin_ids:
            # Fallback: colaborador CMIG tem acesso a anúncios de contas vinculadas à sua CMIG
            has_cmig_access = False
            if listing.account.cmig_id:
                r = await db.execute(
                    select(CMIGAdministrator).where(
                        CMIGAdministrator.user_id == user.id,
                        CMIGAdministrator.cmig_id == listing.account.cmig_id,
                    )
                )
                has_cmig_access = r.scalar_one_or_none() is not None
            if not has_cmig_access:
                raise HTTPException(status_code=403, detail="Sem acesso a este anúncio")
    return listing


def _build_ml_payload(
    product, form: dict, *, use_family_name: bool = False, for_update: bool = False
) -> dict:
    """Build full ML item payload from a product (CMIGProduct or CatalogProduct) + form data.

    use_family_name=True → categorias de catálogo ML: usa family_name em vez de title.
    for_update=True      → omite campos imutáveis após criação (ex: shipping.dimensions).
    """
    title = (form.get("title_override") or product.title or "")[:60]
    payload: dict = {
        "price": float(form["sale_price"]),
        "currency_id": "BRL",
        "available_quantity": int(form.get("available_quantity") or 1),
        "buying_mode": "buy_it_now",
        "listing_type_id": form.get("listing_type") or "gold_special",
        "condition": form.get("item_condition") or "new",
    }

    has_family_name = bool(form.get("family_name"))
    use_fn = use_family_name or has_family_name
    if use_fn:
        payload["family_name"] = (form.get("family_name") or title)[:60]
    else:
        payload["title"] = title

    if form.get("category_id"):
        payload["category_id"] = form["category_id"]

    # Pictures — ML precisa baixar pela URL, então absolutizamos qualquer caminho relativo.
    images = form.get("pictures") or []
    if not images and hasattr(product, "images"):
        images = [img.url for img in (product.images or [])]
    if images:
        payload["pictures"] = [
            {"source": _absolutize_image_url(url)} for url in images[:12]
        ]

    # Attributes — list of {"id": "BRAND", "value_name": "Nike"}
    attributes = list(form.get("attributes") or [])
    if not any(a.get("id") == "BRAND" for a in attributes) and getattr(product, "brand", None):
        attributes.append({"id": "BRAND", "value_name": product.brand})

    # Package dimensions (obrigatórios em várias categorias ML)
    existing_ids = {a.get("id", "").upper() for a in attributes}

    # SELLER_SKU — código de identificação interno do vendedor.
    # Ordem de preferência: form.sku → product.sku_cmig → product.sku
    sku_value = (
        form.get("sku")
        or getattr(product, "sku_cmig", None)
        or getattr(product, "sku", None)
    )
    if sku_value and "SELLER_SKU" not in existing_ids:
        attributes.append({"id": "SELLER_SKU", "value_name": str(sku_value)})
        existing_ids.add("SELLER_SKU")

    # Modelo (obrigatório em várias categorias ML)
    model = form.get("model") or getattr(product, "model", None)
    if model and "MODEL" not in existing_ids:
        attributes.append({"id": "MODEL", "value_name": str(model)})

    # Atributos fiscais (NCM, CEST, GTIN, ORIGIN) — necessários pro Faturador ML emitir NFe
    # sem retornar "Sku not found" (error_code 10316). Prioridade:
    # attributes manuais > form.fiscal_json > campo fiscal do produto.
    fiscal = {}
    raw_fiscal = form.get("fiscal_json")
    if isinstance(raw_fiscal, str) and raw_fiscal.strip():
        try:
            fiscal = _json.loads(raw_fiscal) or {}
        except Exception:
            fiscal = {}
    elif isinstance(raw_fiscal, dict):
        fiscal = raw_fiscal

    def _fiscal_str(*keys, prod_attr: str | None = None) -> str | None:
        """Retorna primeira chave não-vazia em fiscal (case-insensitive) ou prod.<prod_attr>."""
        for k in keys:
            v = fiscal.get(k) or fiscal.get(k.upper()) or fiscal.get(k.lower())
            if v not in (None, ""):
                return str(v).strip() or None
        if prod_attr:
            v = getattr(product, prod_attr, None)
            if v not in (None, ""):
                return str(v).strip() or None
        return None

    ncm_val = _fiscal_str("ncm", prod_attr="ncm")
    if ncm_val:
        ncm_val = ncm_val.replace(".", "").replace("-", "")[:8] or None
    if ncm_val and "NCM" not in existing_ids and "FISCAL_CLASSIFICATION" not in existing_ids:
        attributes.append({"id": "NCM", "value_name": ncm_val})
        existing_ids.add("NCM")

    cest_val = _fiscal_str("cest", prod_attr="cest")
    if cest_val:
        cest_val = cest_val.replace(".", "").replace("-", "")[:7] or None
    if cest_val and "CEST" not in existing_ids:
        attributes.append({"id": "CEST", "value_name": cest_val})
        existing_ids.add("CEST")

    # NOTA: CSOSN NÃO é atributo de item ML — o ML droppou silenciosamente quando
    # tentamos enviar como `ICMS_CSOSN` em PUT /items. CSOSN é gravado via endpoint
    # dedicado `POST /items/fiscal_information` chamado depois pelo Faturador
    # (ver ml_service.register_or_update_fiscal_information). Aqui só atributos de
    # categoria do item ML (NCM/CEST/GTIN/ORIGIN já estão acima).

    # EAN e GTIN são equivalentes pro ML — usamos GTIN como id canônico.
    # Validamos checksum EAN-13 antes de enviar: GTIN inválido derrubaria todo o
    # PUT /items com 400 (item.attribute.product_identifier.invalid_format), e
    # com isso NCM/CEST/ORIGIN também não salvariam. Skip silencioso é melhor UX.
    gtin_val = _fiscal_str("gtin", "ean", prod_attr="ean")
    if gtin_val and "GTIN" not in existing_ids and "EAN" not in existing_ids:
        if _is_valid_ean13(gtin_val):
            attributes.append({"id": "GTIN", "value_name": gtin_val})
            existing_ids.add("GTIN")
        else:
            logging.getLogger(__name__).warning(
                "GTIN '%s' com checksum EAN-13 inválido — skip envio ao ML", gtin_val
            )

    # Origin é numérico (0-8); fiscal_json raramente tem, então caímos no product.origin
    origin_val = fiscal.get("origin")
    if origin_val in (None, ""):
        origin_val = getattr(product, "origin", None)
    if origin_val not in (None, "") and "ORIGIN" not in existing_ids:
        attributes.append({"id": "ORIGIN", "value_name": str(origin_val)})
        existing_ids.add("ORIGIN")

    for field, attr_id in [
        ("height_cm", "SELLER_PACKAGE_HEIGHT"),
        ("width_cm", "SELLER_PACKAGE_WIDTH"),
        ("length_cm", "SELLER_PACKAGE_LENGTH"),
    ]:
        val = form.get(field)
        if val in (None, ""):
            val = getattr(product, field, None)
        if val not in (None, "") and attr_id not in existing_ids:
            attributes.append({"id": attr_id, "value_name": f"{int(float(val))} cm"})
    weight = form.get("weight_kg")
    if weight in (None, ""):
        weight = getattr(product, "weight_kg", None)
    if weight not in (None, "") and "SELLER_PACKAGE_WEIGHT" not in existing_ids:
        attributes.append(
            {"id": "SELLER_PACKAGE_WEIGHT", "value_name": f"{int(float(weight) * 1000)} g"}
        )

    if attributes:
        payload["attributes"] = attributes

    # Warranty via sale_terms
    warranty_type = form.get("warranty_type")
    warranty_time = form.get("warranty_time")
    if warranty_type:
        payload["sale_terms"] = [{"id": "WARRANTY_TYPE", "value_name": warranty_type}]
        if warranty_time:
            payload["sale_terms"].append({"id": "WARRANTY_TIME", "value_name": warranty_time})

    shipping_payload: dict = {
        "mode": form.get("shipping_mode") or "me2",
        "free_shipping": bool(form.get("free_shipping", False)),
    }
    # Note: Flex (logistic_type=self_service) NÃO é controlado por anúncio. O ML resolve
    # automaticamente a partir de (a) conta tem Flex habilitado, (b) categoria aceita,
    # (c) produto tem atributos exigidos. Não enviamos shipping.tags — o ML rejeita
    # field_not_updatable em itens existentes e ignora silenciosamente em criação.

    # Dimensões do pacote para cálculo de frete ME2 — somente na criação (imutável após)
    if not for_update:
        _h = form.get("height_cm") or getattr(product, "height_cm", None)
        _w = form.get("width_cm") or getattr(product, "width_cm", None)
        _l = form.get("length_cm") or getattr(product, "length_cm", None)
        _kg = form.get("weight_kg") or getattr(product, "weight_kg", None)
        if _h and _w and _l and _kg:
            shipping_payload["dimensions"] = (
                f"{int(float(_h))}x{int(float(_w))}x{int(float(_l))},{int(float(_kg) * 1000)}"
            )

    payload["shipping"] = shipping_payload

    # Variações: quando presentes, o ML não aceita available_quantity no root
    variations = form.get("variations")
    if variations:
        payload.pop("available_quantity", None)
        payload["variations"] = variations

    return payload


def _ml_requires_family_name(error_body: dict) -> bool:
    """Retorna True se o erro do ML indica que family_name é obrigatório.

    Detecta dois formatos que o ML usa:
      1. cause[] com objetos contendo "family_name" no code/message.
      2. error/message de topo indicando que "title" é inválido para a chamada
         (ex: {"error": "The fields [title] are invalid for requested call."})
         — significa que a categoria exige family_name em vez de title.
    """
    for cause in ml_service._cause_list(error_body):
        code = cause.get("code", "")
        msg = cause.get("message", "")
        if "family_name" in msg or "family_name" in code:
            return True

    # ML retornou cause:[] mas o erro de topo indica que title é inválido
    top_error = (error_body.get("error") or "").lower()
    top_msg   = (error_body.get("message") or "").lower()
    if "title" in top_error and "invalid" in top_error:
        return True
    if "title" in top_msg and "invalid" in top_msg:
        return True

    return False


async def _create_ml_item_with_retry(access_token: str, prod, ml_form: dict) -> dict:
    """Tenta criar item ML; se a categoria exigir family_name, retenta sem title."""
    import httpx

    ML_API_BASE = "https://api.mercadolibre.com"

    # 1ª tentativa: payload normal com title
    payload = _build_ml_payload(prod, ml_form, use_family_name=False)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ML_API_BASE}/items",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )

    if resp.status_code in (200, 201):
        return resp.json()

    # Se ML exigiu family_name → retenta com family_name (sem title)
    try:
        err = resp.json()
    except Exception:
        err = {}

    if resp.status_code == 400 and _ml_requires_family_name(err):
        payload2 = _build_ml_payload(prod, ml_form, use_family_name=True)
        async with httpx.AsyncClient() as client:
            resp2 = await client.post(
                f"{ML_API_BASE}/items",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload2,
            )
        if resp2.status_code in (200, 201):
            return resp2.json()
        raise HTTPException(status_code=400, detail=f"Erro ao criar anúncio ML: {resp2.text}")

    raise HTTPException(status_code=400, detail=f"Erro ao criar anúncio ML: {resp.text}")


def _serialize_listing(
    listing: ProductListing,
    full_per_account_map: dict | None = None,
) -> dict:
    """Serializa um listing.

    `full_per_account_map`: opcional, formato {(product_type, product_id): {account_id: {qty, reserved_qty}}}.
    Quando fornecido, expõe campos LIVE de FULL (`full_physical_live`, `full_reserved_live`,
    `full_available_live`); caso contrário, esses campos ficam como None (UI cai no
    snapshot `qty_full` legado).
    """
    cmig_product = None
    if listing.cmig_product:
        cmig_product = {
            "id": listing.cmig_product.id,
            "cmig_id": listing.cmig_product.cmig_id,
            "sku_cmig": listing.cmig_product.sku_cmig,
            "sku": listing.cmig_product.sku_cmig,  # alias pra compatibilidade
            "title": listing.cmig_product.title,
            "brand": listing.cmig_product.brand,
            "model": listing.cmig_product.model,
            "pg_product_id": listing.cmig_product.pg_product_id,
            "images": [
                {"url": img.url, "sort_order": img.sort_order}
                for img in sorted(
                    (listing.cmig_product.images or []),
                    key=lambda i: (i.sort_order or 0),
                )
            ],
        }
    catalog_product = None
    if listing.catalog_product:
        catalog_product = {
            "id": listing.catalog_product.id,
            "sku": listing.catalog_product.sku,
            "title": listing.catalog_product.title,
            "brand": listing.catalog_product.brand,
            "model": listing.catalog_product.model,
            "images": [
                {"url": img.url, "sort_order": img.sort_order}
                for img in sorted(
                    (listing.catalog_product.images or []),
                    key=lambda i: (i.sort_order or 0),
                )
            ],
        }
    return {
        "id": listing.id,
        "account_id": listing.account_id,
        "platform_item_id": listing.platform_item_id,
        "permalink": listing.permalink,
        "thumbnail": listing.thumbnail,
        "sku": listing.sku,
        "title_override": listing.title_override,
        "sale_price": float(listing.sale_price) if listing.sale_price else None,
        "status": listing.status,
        "listing_type": listing.listing_type,
        "category_id": listing.category_id,
        "category_name": listing.category_name,
        "category_path_json": listing.category_path_json,
        "is_full": bool(listing.is_full) if listing.is_full is not None else False,
        "is_flex": (listing.logistic_type or "").lower() == "self_service",
        "logistic_type": listing.logistic_type
        or ("fulfillment" if listing.is_full else "cross_docking"),
        "ml_catalog_id": listing.ml_catalog_id,
        "catalog_listing": bool(listing.catalog_listing)
        if listing.catalog_listing is not None
        else False,
        "available_quantity": listing.available_quantity,
        "stock_mode": listing.stock_mode or "product",
        "fixed_quantity": listing.fixed_quantity or 1,
        "keep_stock_fixed": bool(listing.keep_stock_fixed)
        if listing.keep_stock_fixed is not None
        else False,
        "sold_quantity": listing.sold_quantity or 0,
        "visits_7d": listing.visits_7d or 0,
        "item_condition": listing.item_condition,
        "weight_kg": float(listing.weight_kg) if listing.weight_kg else None,
        "height_cm": float(listing.height_cm) if listing.height_cm else None,
        "width_cm": float(listing.width_cm) if listing.width_cm else None,
        "length_cm": float(listing.length_cm) if listing.length_cm else None,
        "pictures_json": listing.pictures_json,
        "fiscal_json": listing.fiscal_json,
        "variations_json": listing.variations_json,
        "published_at": listing.published_at.isoformat() if listing.published_at else None,
        "last_sync_at": listing.last_sync_at.isoformat() if listing.last_sync_at else None,
        "description_override": listing.description_override,
        "attributes_json": listing.attributes_json,
        "warranty_type": listing.warranty_type,
        "warranty_time": listing.warranty_time,
        "shipping_mode": listing.shipping_mode,
        "free_shipping": listing.free_shipping,
        "video_id": listing.video_id,
        # Cached cost fields
        "commission_pct": float(listing.commission_pct)
        if listing.commission_pct is not None
        else None,
        "commission_amount": float(listing.commission_amount)
        if listing.commission_amount is not None
        else None,
        "shipping_cost": float(listing.shipping_cost)
        if listing.shipping_cost is not None
        else None,
        "net_revenue": float(listing.net_revenue) if listing.net_revenue is not None else None,
        "margin_pct": float(listing.margin_pct) if listing.margin_pct is not None else None,
        "costs_cached_at": listing.costs_cached_at.isoformat() if listing.costs_cached_at else None,
        # Stock by type — qty_full/qty_local são snapshots do último sync ML (cache).
        # Para EXIBIR estoque na UI, preferir *_stock_* (live, calculados do produto vinculado).
        "qty_full": listing.qty_full or 0,
        "qty_local": listing.qty_local or 0,
        # Seller warehouse stock (live): físico, reservado e DISPONÍVEL.
        # Fonte da verdade: CMIGProduct/CatalogProduct vinculado.
        **(lambda p: {
            "local_stock_physical": int(p.stock_quantity or 0) if p else None,
            "local_stock_reserved": int(p.reserved_quantity or 0) if p else None,
            "local_stock_available": (
                max(0, int(p.stock_quantity or 0) - int(p.reserved_quantity or 0))
                if p else None
            ),
            # Alias legado mantido para compatibilidade com código antigo.
            "product_stock": int(p.stock_quantity or 0) if p else None,
        })(listing.cmig_product or listing.catalog_product),
        # FULL stock LIVE (Fase 1): físico, reservado e disponível no Fulfillment ML
        # para a CONTA deste listing. Fonte: FullStock (canônica). None quando
        # full_per_account_map não foi fornecido pelo caller.
        **(lambda: (
            (lambda d: {
                "full_stock_physical": int(d.get("qty", 0) or 0),
                "full_stock_reserved": int(d.get("reserved_qty", 0) or 0),
                "full_stock_available": max(
                    0, int(d.get("qty", 0) or 0) - int(d.get("reserved_qty", 0) or 0)
                ),
            })(
                (full_per_account_map or {})
                .get(
                    ("cmig", listing.cmig_product_id) if listing.cmig_product_id
                    else (("pg", listing.catalog_product_id) if listing.catalog_product_id else (None, None)),
                    {},
                )
                .get(listing.account_id, {})
            )
            if full_per_account_map is not None
            and (listing.cmig_product_id or listing.catalog_product_id)
            else {
                "full_stock_physical": None,
                "full_stock_reserved": None,
                "full_stock_available": None,
            }
        ))(),
        # Promotion fields
        "regular_price": float(listing.regular_price)
        if listing.regular_price is not None
        else None,
        "promo_type": listing.promo_type,
        "promo_discount_pct": float(listing.promo_discount_pct)
        if listing.promo_discount_pct is not None
        else None,
        "has_auto_price_adj": bool(listing.has_auto_price_adj)
        if listing.has_auto_price_adj is not None
        else False,
        # Agrupamento de variações (User Products)
        "variation_group_id": listing.variation_group_id,
        "family_name_ml": listing.family_name_ml,
        "is_variation_grouped": bool(listing.variation_group_id),
        "cmig_product": cmig_product,
        "catalog_product": catalog_product,
        "is_linked": cmig_product is not None or catalog_product is not None,
    }


async def _get_valid_token(account: MarketplaceAccount, db: AsyncSession) -> str:
    """Retorna o access_token da conta; tenta refresh se expirado."""
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Importação automática disponível apenas para Mercado Livre"
        )

    now = datetime.now(UTC)
    expires = account.token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)

    token_expired = expires and expires <= now

    if token_expired:
        if not account.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Token do Mercado Livre expirado. Reconecte a conta em Integrações → editar conta.",
            )
        from datetime import timedelta

        try:
            token_data = await ml_service.refresh_ml_token(account.refresh_token)
        except HTTPException as exc:
            # ML revogou o refresh_token (invalid_grant) → marca pra UI mostrar alerta
            # de reconexão imediatamente, sem esperar o job sync_tokens (1h).
            if exc.status_code == 401 and "invalid_grant" in (exc.detail or "").lower():
                account.requires_reauth = True
                await db.commit()
            raise
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data.get("refresh_token", account.refresh_token)
        account.token_expires_at = now + timedelta(seconds=token_data.get("expires_in", 21600))
        await db.commit()

    if not account.access_token:
        raise HTTPException(
            status_code=401,
            detail="Conta sem token de acesso. Conecte a conta do Mercado Livre em Integrações.",
        )

    return account.access_token


async def _cache_costs(
    listing: ProductListing, access_token: str, seller_id: str, db: AsyncSession
) -> None:
    """Calcula e salva custos + promoção ML em cache no listing (sem commit — chame db.commit() externamente)."""
    try:
        real_price = float(listing.sale_price or 0)

        # 1. Preço real atual do ML (promo ou regular) + detecção de automação — em paralelo
        if listing.platform_item_id:
            try:
                import asyncio as _aio

                promo, auto_info = await _aio.gather(
                    ml_service.get_sale_price_info(access_token, listing.platform_item_id),
                    ml_service.get_item_auto_pricing(access_token, listing.platform_item_id),
                )
                current_price = promo.get("sale_price")
                if current_price and float(current_price) > 0:
                    real_price = float(current_price)
                    listing.sale_price = real_price
                promo_type_val = promo.get("promotion_type") if promo.get("has_promotion") else None
                if promo.get("has_promotion"):
                    listing.regular_price = promo.get("regular_price")
                    listing.promo_type = promo_type_val
                    listing.promo_discount_pct = promo.get("discount_pct")
                else:
                    listing.regular_price = None
                    listing.promo_type = None
                    listing.promo_discount_pct = None
                # Detecção via /items/{id}/prices e tags — fonte correta para automação de preço
                listing.has_auto_price_adj = auto_info["is_auto"]
            except Exception:
                pass

        # 2. Custos com o preço real (pode ser o preço promocional)
        # Resolve logistic_type real do listing — fallback para is_full legado
        lt = (listing.logistic_type or "").strip().lower()
        if not lt:
            lt = "fulfillment" if listing.is_full else "cross_docking"

        costs = await ml_service.get_listing_costs(
            access_token=access_token,
            seller_id=seller_id,
            price=real_price,
            category_id=listing.category_id or "",
            listing_type=listing.listing_type or "gold_special",
            shipping_mode=listing.shipping_mode or "me2",
            logistic_type=lt,
            weight_kg=float(listing.weight_kg) if listing.weight_kg else None,
            height_cm=float(listing.height_cm) if listing.height_cm else None,
            width_cm=float(listing.width_cm) if listing.width_cm else None,
            length_cm=float(listing.length_cm) if listing.length_cm else None,
            free_shipping=bool(listing.free_shipping),
        )
        shipping_cost_calc = float(costs.get("shipping_cost") or 0)

        # Para Full: /shipping_options/free retorna o custo correto quando chamado com os
        # parâmetros adequados (free_shipping, condition, verbose). A tabela local é fallback
        # para quando a API não retornar valor (timeout, dimensões ausentes, erro).
        if (
            lt == "fulfillment"
            and shipping_cost_calc == 0
            and listing.weight_kg
            and listing.height_cm
            and listing.width_cm
            and listing.length_cm
        ):
            from services.ml_service import _calc_billable_weight, reputation_tier_for_account

            wb = _calc_billable_weight(
                float(listing.weight_kg),
                float(listing.height_cm),
                float(listing.width_cm),
                float(listing.length_cm),
            )
            tier = reputation_tier_for_account(listing.account)
            full_tariff = await ml_service.get_full_shipping_cost(
                wb["billable_kg"],
                real_price,
                tier,
                db,
                free_shipping=bool(listing.free_shipping),
            )
            shipping_cost_calc = full_tariff

        # Recalcula receita líquida e margem com o frete ajustado
        commission = float(costs.get("commission_amount") or 0)
        fixed_fee = float(costs.get("fixed_fee") or 0)
        financing = float(costs.get("financing_fee") or 0)
        total_cost = commission + shipping_cost_calc + fixed_fee + financing
        net_revenue = real_price - total_cost
        margin_pct = round((net_revenue / real_price) * 100, 2) if real_price > 0 else 0.0

        listing.commission_pct = costs.get("commission_pct")
        listing.commission_amount = commission
        listing.shipping_cost = round(shipping_cost_calc, 2)
        listing.net_revenue = round(net_revenue, 2)
        listing.margin_pct = margin_pct
        listing.costs_cached_at = datetime.now(UTC)
    except Exception:
        pass


async def _validate_token_owner(account: MarketplaceAccount, access_token: str) -> str:
    """Confirma que o token pertence ao vendedor registrado na conta. Retorna seller_id."""
    user_info = await ml_service.get_user_info(access_token)
    seller_id = str(user_info.get("id", ""))
    if not seller_id:
        raise HTTPException(
            status_code=400, detail="Não foi possível obter o ID do vendedor no Mercado Livre"
        )

    token_email = (user_info.get("email") or "").lower().strip()
    account_email = (account.email or "").lower().strip()

    if account.platform_user_id and account.platform_user_id != seller_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conta incorreta: o token conectado pertence ao vendedor ID '{seller_id}' "
                f"(e-mail: {token_email or 'desconhecido'}), mas a conta selecionada está "
                f"registrada para o vendedor ID '{account.platform_user_id}'. "
                "Reconecte a conta correta em Integrações."
            ),
        )

    if account_email and token_email and account_email != token_email:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conta incorreta: o token conectado pertence à conta '{token_email}', "
                f"mas a conta selecionada está registrada para '{account_email}'. "
                "Reconecte a conta correta em Integrações."
            ),
        )

    return seller_id


# ── endpoints ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_anuncios(
    account_id: int,
    vinculo: str = "all",  # all | linked | unlinked
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista anúncios de uma conta de marketplace do AC."""
    await _get_account_or_403(account_id, current_user, db)

    q = (
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(ProductListing.account_id == account_id)
    )
    if status:
        q = q.where(ProductListing.status == status)

    result = await db.execute(q.order_by(ProductListing.created_at.desc()))
    listings = result.scalars().all()

    # 1 query agregada: quantas variações de cada listing já foram importadas como CMIGProduct
    listing_ids = [l.id for l in listings]
    imported_counts: dict[int, int] = {}
    if listing_ids:
        from sqlalchemy import func as _func
        r2 = await db.execute(
            select(CMIGProduct.source_listing_id, _func.count(CMIGProduct.id))
            .where(CMIGProduct.source_listing_id.in_(listing_ids))
            .group_by(CMIGProduct.source_listing_id)
        )
        imported_counts = {row[0]: row[1] for row in r2.all()}

    # Pré-carrega FULL stock LIVE (Fase 1 SSOT) em batch para todos os listings da conta.
    from services.stock_view import load_full_per_account_map
    full_per_account_map = await load_full_per_account_map(
        db,
        cmig_ids=[l.cmig_product_id for l in listings if l.cmig_product_id],
        pg_ids=[l.catalog_product_id for l in listings if l.catalog_product_id and not l.cmig_product_id],
        account_ids=[account_id],
    )

    serialized = []
    for l in listings:
        item = _serialize_listing(l, full_per_account_map=full_per_account_map)
        # Conta variações no JSON local (independente do ML)
        total_vars = 0
        if l.variations_json:
            try:
                total_vars = len(_json.loads(l.variations_json) or [])
            except Exception:
                total_vars = 0
        imp = imported_counts.get(l.id, 0)
        item["variations_total"] = total_vars
        item["variations_imported_count"] = imp
        item["all_variations_imported"] = bool(total_vars > 0 and imp >= total_vars)
        serialized.append(item)

    if vinculo == "linked":
        serialized = [l for l in serialized if l["is_linked"]]
    elif vinculo == "unlinked":
        serialized = [l for l in serialized if not l["is_linked"]]

    return serialized


@router.get("/{listing_id}")
async def get_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna um anúncio individual com produto vinculado e variações parseadas."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    return _serialize_listing(listing)


@router.post("/import/{account_id}")
async def import_anuncios(
    account_id: int,
    statuses: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Importa anúncios do marketplace e faz auto-match por similaridade de título.

    `statuses`: lista separada por vírgula de status ML a importar.
    - omitido (default) → importa active/paused/closed/under_review do body
    - 'all' ou 'tudo'   → importa TODOS (inclui under_review com sub_status
                          suspended_for_prevention, paused com sub_status raros, etc.)
    - 'active,paused'   → filtra apenas esses status (no body do item, não no params)

    A busca no ML usa search_type=scan SEM filtro de status (mais confiável —
    o filtro `?status=X` da search retorna 0 em casos onde deveria retornar
    resultados, visto em testes com tokens reais).
    """
    account = await _get_account_or_403(account_id, current_user, db)
    access_token = await _get_valid_token(account, db)
    seller_id = await _validate_token_owner(account, access_token)

    # Filtragem por status: aplicada no body retornado, NÃO no params da search
    status_filter: set[str] | None = None
    if statuses and statuses.lower() not in ("all", "tudo", "*"):
        status_filter = {s.strip() for s in statuses.split(",") if s.strip()}
    elif not statuses:
        status_filter = set(ml_service.DEFAULT_IMPORT_STATUSES)
    # statuses == 'all' → status_filter fica None = sem filtro

    diagnostics: list = []
    item_ids = await ml_service.get_seller_item_ids(
        access_token, seller_id, statuses=list(status_filter or []), diagnostics=diagnostics
    )
    items = await ml_service.get_items_bulk(access_token, item_ids)

    # Conta status real visto no ML antes do filtro
    status_counts_before_filter: dict[str, int] = {}
    for it in items:
        st = (it.get("status") or "unknown").lower()
        status_counts_before_filter[st] = status_counts_before_filter.get(st, 0) + 1

    # Aplica filtro pelo body
    total_from_ml = len(items)
    if status_filter is not None:
        items = [it for it in items if (it.get("status") or "").lower() in status_filter]

    # Anexa diagnostics resumido — devolvido no response final pra UI exibir
    diagnostics.append({
        "phase": "filter",
        "total_from_ml": total_from_ml,
        "after_filter": len(items),
        "status_filter": sorted(status_filter) if status_filter else "all",
        "status_counts_in_ml": status_counts_before_filter,
    })

    # Busca descrições em paralelo para todos os itens
    descriptions: dict[str, str] = {}
    if item_ids:
        descriptions = await ml_service.get_items_descriptions(access_token, item_ids)

    # Busca nomes, paths de categorias e visitas 7d em paralelo
    unique_category_ids = list(
        {item.get("category_id") for item in items if item.get("category_id")}
    )
    category_names: dict[str, str] = {}
    category_paths_map: dict[str, list] = {}
    per_item_visits: dict[str, int] = {}
    import asyncio as _asyncio

    async def _fetch_extra():
        nonlocal category_names, category_paths_map, per_item_visits
        tasks = []
        if unique_category_ids:
            tasks.append(ml_service.get_categories_bulk(unique_category_ids))
            tasks.append(ml_service.get_categories_with_paths(unique_category_ids))
        tasks.append(ml_service.get_items_visit_stats(access_token, item_ids))
        results = await _asyncio.gather(*tasks, return_exceptions=True)
        idx = 0
        if unique_category_ids:
            if not isinstance(results[idx], Exception):
                category_names = results[idx]
            idx += 1
            if not isinstance(results[idx], Exception):
                category_paths_map = results[idx]
            idx += 1
        if not isinstance(results[idx], Exception):
            per_item_visits = results[idx]

    await _fetch_extra()

    imported = updated = auto_matched = unlinked = 0
    failed = 0
    saved_listings: list[ProductListing] = []
    item_errors: list[dict] = []  # erros não-fatais coletados durante o loop

    # Carrega produtos CMIG da CMIG vinculada à conta (para auto-match)
    cmig_products: list[CMIGProduct] = []
    if account.cmig_id:
        cp_result = await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.cmig_id == account.cmig_id, CMIGProduct.is_active == True
            )
        )
        cmig_products = cp_result.scalars().all()

    for item in items:
        platform_item_id = item.get("id", "")
        if not platform_item_id:
            failed += 1
            item_errors.append({
                "platform_item_id": None,
                "title": None,
                "error": "Item sem ID retornado pelo ML",
            })
            continue

        # Bulk API retorna price=preço atual e original_price=preço sem desconto (se houver promoção)
        price = float(item.get("price") or 0)
        _original = float(item.get("original_price") or 0)

        if _original > 0 and price > 0 and _original > price * 1.01:
            regular_price = _original
            promo_type_val = None  # tipo exato vem via _cache_costs → get_sale_price_info
            promo_disc_pct = round((_original - price) / _original * 100, 1)
        else:
            regular_price = None
            promo_type_val = None
            promo_disc_pct = None

        # Detecta automação de preço pelas tags do item (já disponíveis na bulk API — sem custo extra)
        _item_tags = [t.lower() for t in (item.get("tags") or [])]
        _AUTO_TAGS = ml_service._AUTO_PRICE_TAGS
        has_auto_price_adj_sync = any(
            t in _AUTO_TAGS or "automat" in t or "smart_pric" in t for t in _item_tags
        )
        title = item.get("title", "")
        permalink = item.get("permalink", "") or ""
        sku = item.get("seller_custom_field") or ""
        _ml_status = item.get("status", "active")
        item_status = {
            "active": "published",
            "paused": "paused",
            "closed": "paused",
            "under_review": "draft",
            "inactive": "paused",
        }.get(_ml_status, "published")
        # Preserva estoque 0 — antes `or 1` transformava "sem estoque" em "1 unidade"
        _aq = item.get("available_quantity")
        if _aq is None:
            _aq = item.get("initial_quantity")
        available_qty = int(_aq) if _aq is not None else 0
        sold_qty = item.get("sold_quantity") or 0
        item_condition = item.get("condition") or "new"
        listing_type = item.get("listing_type_id") or ""
        category_id = item.get("category_id") or ""
        category_name = category_names.get(category_id, "") if category_id else ""
        cat_path = category_paths_map.get(category_id, []) if category_id else []
        cat_path_json = _json.dumps(cat_path, ensure_ascii=False) if cat_path else None
        shipping = item.get("shipping") or {}
        shipping_mode = shipping.get("mode") or "me2"
        free_shipping = bool(shipping.get("free_shipping", False))
        shipping_tags = set(shipping.get("tags") or [])
        # Captura logistic_type real do ML (cross_docking|drop_off|xd_drop_off|self_service|fulfillment)
        logistic_type_raw = (shipping.get("logistic_type") or "cross_docking").lower()
        # self_service_in em tags é o indicador confiável de Flex — normaliza se logistic_type ainda não reflete
        if "self_service_in" in shipping_tags and logistic_type_raw not in ("fulfillment", "self_service"):
            logistic_type_raw = "self_service"
        is_full = logistic_type_raw == "fulfillment"
        qty_full = available_qty if is_full else 0
        qty_local = 0 if is_full else available_qty
        ml_catalog_id = item.get("catalog_product_id") or ""
        catalog_listing = bool(item.get("catalog_listing", False))
        visits_7d = per_item_visits.get(str(platform_item_id), 0)

        # Fotos — todas as pictures com URL HTTPS
        _DIMENSIONAL_IDS = {
            "WEIGHT",
            "NET_WEIGHT",
            "GROSS_WEIGHT",
            "PACKAGE_WEIGHT",
            "PACKAGE_NET_WEIGHT",
            "HEIGHT",
            "WIDTH",
            "LENGTH",
            "DEPTH",
            "PACKAGE_HEIGHT",
            "PACKAGE_WIDTH",
            "PACKAGE_LENGTH",
            "PACKAGE_DEPTH",
        }
        _FISCAL_IDS = {"GTIN", "EAN", "NCM", "CEST", "FISCAL_CLASSIFICATION"}

        pics_list = []
        for pic in item.get("pictures", []):
            url = pic.get("secure_url") or pic.get("url", "")
            if url:
                pics_list.append(
                    {"id": pic.get("id", ""), "url": url.replace("http://", "https://")}
                )

        thumbnail = item.get("thumbnail", "") or ""
        if not thumbnail and pics_list:
            thumbnail = pics_list[0]["url"]
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")

        # Descrição (buscada em paralelo antes do loop)
        description_text = descriptions.get(str(platform_item_id), "") or ""

        # Separação de atributos: dimensional, fiscal, ficha técnica
        dim: dict = {}
        fiscal: dict = {}
        tech: list = []
        for attr in item.get("attributes", []):
            attr_id = (attr.get("id") or "").upper()
            val_name = attr.get("value_name")
            val_struct = attr.get("value_struct") or {}
            val_num = val_struct.get("number")
            unit = val_struct.get("unit") or ""
            # When val_struct is absent, try to parse val_name for dimensional attrs
            if val_num is None and attr_id in _DIMENSIONAL_IDS and val_name:
                import re as _re

                _m = _re.match(r"([\d.,]+)\s*(.*)", val_name.strip())
                if _m:
                    try:
                        val_num = float(_m.group(1).replace(",", "."))
                        if not unit:
                            unit = _m.group(2).strip()
                    except ValueError:
                        pass
            val = val_name or val_num
            if attr_id in _DIMENSIONAL_IDS:
                dim[attr_id] = {"value": val_num, "unit": unit, "text": val_name}
            elif attr_id in _FISCAL_IDS:
                # value_id como fallback quando value_name é None (catálogo ML)
                fiscal_val = val_name or attr.get("value_id")
                if fiscal_val is not None:
                    fiscal[attr_id.lower()] = str(fiscal_val)
            elif val is not None:
                tech.append({"id": attr_id, "name": attr.get("name"), "value": val_name})

        # sale_terms: fonte adicional de GTIN/EAN (comum no ML Brasil)
        for term in item.get("sale_terms", []):
            term_id = (term.get("id") or "").upper()
            if term_id in _FISCAL_IDS:
                term_val = term.get("value_name") or term.get("value_id")
                if term_val and not fiscal.get(term_id.lower()):
                    fiscal[term_id.lower()] = str(term_val)

        # Fallback de SKU pelo atributo SELLER_SKU
        if not sku:
            _sku_attr = next(
                (
                    a
                    for a in item.get("attributes", [])
                    if (a.get("id") or "").upper() == "SELLER_SKU"
                ),
                None,
            )
            if _sku_attr:
                sku = _sku_attr.get("value_name") or ""

        def _to_kg(key, dim=dim):
            """Converte valor dimensional para kg respeitando a unidade retornada pelo ML."""
            d = dim.get(key, {})
            v = d.get("value")
            if v is None:
                return None
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            u = (d.get("unit") or "").lower()
            if u in ("g", "gr", "grams", "gramas"):
                return round(v / 1000, 3)
            if u in ("mg", "milligrams"):
                return round(v / 1_000_000, 3)
            return round(v, 3)  # assume kg

        def _to_cm(key, dim=dim):
            """Converte valor dimensional para cm respeitando a unidade retornada pelo ML."""
            d = dim.get(key, {})
            v = d.get("value")
            if v is None:
                return None
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            u = (d.get("unit") or "").lower()
            if u in ("mm", "millimeters", "milímetros"):
                return round(v / 10, 2)
            if u in ("m", "meters", "metros"):
                return round(v * 100, 2)
            return round(v, 2)  # assume cm

        weight_kg = (
            _to_kg("WEIGHT")
            or _to_kg("NET_WEIGHT")
            or _to_kg("GROSS_WEIGHT")
            or _to_kg("PACKAGE_WEIGHT")
            or _to_kg("PACKAGE_NET_WEIGHT")
        )
        height_cm = _to_cm("HEIGHT") or _to_cm("PACKAGE_HEIGHT")
        width_cm = _to_cm("WIDTH") or _to_cm("PACKAGE_WIDTH")
        length_cm = (
            _to_cm("LENGTH")
            or _to_cm("DEPTH")
            or _to_cm("PACKAGE_LENGTH")
            or _to_cm("PACKAGE_DEPTH")
        )

        # Fallback: parse shipping.dimensions string ("HxWxL,weight_g") for missing values
        _dims_str = (shipping.get("dimensions") or "").strip()
        if _dims_str:
            try:
                _parts = _dims_str.split(",")
                _size_parts = _parts[0].strip().lower().split("x")
                if len(_size_parts) == 3:
                    _h, _w, _l = [float(s.strip()) for s in _size_parts]
                    if height_cm is None:
                        height_cm = _h
                    if width_cm is None:
                        width_cm = _w
                    if length_cm is None:
                        length_cm = _l
                if len(_parts) >= 2 and weight_kg is None:
                    weight_kg = round(float(_parts[1].strip()) / 1000, 3)
            except (ValueError, IndexError):
                pass

        # Variações
        variations_list = []
        for var in item.get("variations", []):
            variations_list.append(
                {
                    "id": var.get("id"),
                    "price": var.get("price"),
                    "available_quantity": var.get("available_quantity"),
                    "sold_quantity": var.get("sold_quantity"),
                    "attributes": [
                        {"id": a.get("id"), "name": a.get("name"), "value": a.get("value_name")}
                        for a in var.get("attribute_combinations", [])
                    ],
                    "picture_ids": var.get("picture_ids", []),
                }
            )

        pictures_json = _json.dumps(pics_list, ensure_ascii=False) if pics_list else None
        fiscal_json = _json.dumps(fiscal, ensure_ascii=False) if fiscal else None
        variations_json = (
            _json.dumps(variations_list, ensure_ascii=False) if variations_list else None
        )
        attributes_json = _json.dumps(tech, ensure_ascii=False) if tech else None

        # Upsert
        existing_result = await db.execute(
            select(ProductListing).where(
                ProductListing.account_id == account_id,
                ProductListing.platform_item_id == platform_item_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.title_override = title
            existing.sale_price = price
            existing.status = item_status
            existing.category_id = category_id or existing.category_id
            if category_name:
                existing.category_name = category_name
            if cat_path_json:
                existing.category_path_json = cat_path_json
            existing.listing_type = listing_type or existing.listing_type
            existing.is_full = is_full
            existing.logistic_type = logistic_type_raw
            existing.ml_catalog_id = ml_catalog_id or existing.ml_catalog_id
            existing.catalog_listing = catalog_listing
            existing.available_quantity = available_qty
            existing.sold_quantity = sold_qty
            existing.visits_7d = visits_7d
            existing.item_condition = item_condition
            existing.shipping_mode = shipping_mode
            existing.free_shipping = free_shipping
            if thumbnail:
                existing.thumbnail = thumbnail
            if permalink:
                existing.permalink = permalink
            if sku:
                existing.sku = sku
            if description_text:
                existing.description_override = description_text
            # Só sobrescreve dimensões quando o ML retornou valor — evita
            # zerar cadastro local quando o anúncio no ML não tem essas infos.
            if weight_kg is not None:
                existing.weight_kg = weight_kg
            if height_cm is not None:
                existing.height_cm = height_cm
            if width_cm is not None:
                existing.width_cm = width_cm
            if length_cm is not None:
                existing.length_cm = length_cm
            if pictures_json:
                existing.pictures_json = pictures_json
            if fiscal_json:
                existing.fiscal_json = fiscal_json
            if variations_json:
                existing.variations_json = variations_json
            if attributes_json:
                existing.attributes_json = attributes_json
            existing.qty_full = qty_full
            existing.qty_local = qty_local
            if regular_price is not None:
                existing.regular_price = regular_price
                existing.promo_type = promo_type_val
                existing.promo_discount_pct = promo_disc_pct
            elif (
                existing.regular_price is not None
                and price >= float(existing.regular_price or 0) * 0.99
            ):
                # promoção acabou — limpa os campos
                existing.regular_price = None
                existing.promo_type = None
                existing.promo_discount_pct = None
            existing.has_auto_price_adj = has_auto_price_adj_sync
            existing.last_sync_at = datetime.now(UTC)
            updated += 1
            listing = existing
        else:
            listing = ProductListing(
                account_id=account_id,
                platform_item_id=platform_item_id,
                title_override=title,
                thumbnail=thumbnail,
                permalink=permalink,
                sku=sku,
                description_override=description_text or None,
                sale_price=price,
                status=item_status,
                category_id=category_id,
                category_name=category_name or None,
                category_path_json=cat_path_json,
                listing_type=listing_type,
                is_full=is_full,
                logistic_type=logistic_type_raw,
                ml_catalog_id=ml_catalog_id or None,
                catalog_listing=catalog_listing,
                available_quantity=available_qty,
                sold_quantity=sold_qty,
                visits_7d=visits_7d,
                item_condition=item_condition,
                shipping_mode=shipping_mode,
                free_shipping=free_shipping,
                weight_kg=weight_kg,
                height_cm=height_cm,
                width_cm=width_cm,
                length_cm=length_cm,
                pictures_json=pictures_json,
                fiscal_json=fiscal_json,
                variations_json=variations_json,
                attributes_json=attributes_json,
                qty_full=qty_full,
                qty_local=qty_local,
                regular_price=regular_price,
                promo_type=promo_type_val,
                promo_discount_pct=promo_disc_pct,
                has_auto_price_adj=has_auto_price_adj_sync,
                published_at=datetime.now(UTC),
                last_sync_at=datetime.now(UTC),
            )
            db.add(listing)
            imported += 1

        # Auto-match por similaridade (só se ainda sem vínculo)
        if not listing.cmig_product_id and not listing.catalog_product_id and cmig_products:
            best = max(cmig_products, key=lambda p: _title_similarity(title, p.title))
            sim = _title_similarity(title, best.title)
            if sim >= 0.6:
                listing.cmig_product_id = best.id
                auto_matched += 1
            else:
                unlinked += 1
        elif not listing.cmig_product_id and not listing.catalog_product_id:
            unlinked += 1

        saved_listings.append(listing)

    # Cache de custos ML com concorrência 5
    import asyncio as _aio

    _sem = _aio.Semaphore(5)

    async def _cache_one(lst):
        async with _sem:
            await _cache_costs(lst, access_token, seller_id, db)

    await _aio.gather(*[_cache_one(l) for l in saved_listings])

    await db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "auto_matched": auto_matched,
        "unlinked": unlinked,
        "failed": failed,
        "item_errors": item_errors[:50],  # cap pra não inflar response
        "total_seen_in_ml": len(items) + failed,
        "diagnostics": diagnostics,
    }


@router.post("/{listing_id}/refresh-costs", status_code=200)
async def refresh_listing_costs(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalcula custos ML + promoção e salva no BD."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""
    await _cache_costs(listing, access_token, seller_id, db)
    await db.commit()
    return {
        "ok": True,
        "costs_cached_at": listing.costs_cached_at.isoformat() if listing.costs_cached_at else None,
    }


@router.post("/{listing_id}/refresh-pictures", status_code=200)
async def refresh_listing_pictures(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rebusca as fotos do item no ML e atualiza pictures_json + thumbnail.

    Útil quando o item foi publicado enquanto o ML ainda estava processando as
    imagens — o pictures_json original ficou com URLs de placeholder
    (`statics/processing-image/...`) e agora as URLs reais já estão disponíveis.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")
    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=422, detail="Refresh de fotos só para Mercado Livre")

    access_token = await _get_valid_token(listing.account, db)
    ml_item = await ml_service.get_item(access_token, listing.platform_item_id)

    ml_pictures = ml_item.get("pictures") or []
    # Atualiza thumbnail se a versão atual ainda é placeholder ou se o ML tem nova
    new_thumb = ml_item.get("secure_thumbnail") or ml_item.get("thumbnail")
    if new_thumb:
        new_thumb = new_thumb.replace("http://", "https://")
        if not _is_processing_placeholder_url(new_thumb):
            listing.thumbnail = new_thumb

    pics: list[dict] = []
    still_processing = False
    for pic in ml_pictures:
        url = (pic.get("secure_url") or pic.get("url") or "").replace("http://", "https://")
        if url:
            pics.append({"id": pic.get("id", ""), "url": url})
            if _is_processing_placeholder_url(url):
                still_processing = True

    if pics:
        listing.pictures_json = _json.dumps(pics, ensure_ascii=False)
        listing.last_sync_at = datetime.now(UTC)
        await db.commit()

    return {
        "ok": True,
        "pictures_count": len(pics),
        "still_processing": still_processing,
        "thumbnail": listing.thumbnail,
    }


@router.get("/{listing_id}/sale-price")
async def get_anuncio_sale_price(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna dados de preço/promoção do item no ML (leve — sem cálculo de custos)."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")
    access_token = await _get_valid_token(listing.account, db)
    return await ml_service.get_sale_price_info(access_token, listing.platform_item_id)


@router.get("/{listing_id}/suggest")
async def suggest_products(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna top 5 sugestões de CMIGProduct e CatalogProduct por similaridade de título."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    title = listing.title_override or ""

    # CMIGProducts da CMIG vinculada à conta
    cmig_suggestions = []
    if listing.account.cmig_id:
        cp_result = await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.cmig_id == listing.account.cmig_id,
                CMIGProduct.is_active == True,
            )
        )
        products = cp_result.scalars().all()
        scored = sorted(products, key=lambda p: _title_similarity(title, p.title), reverse=True)
        cmig_suggestions = [
            {
                "id": p.id,
                "sku": p.sku_cmig,
                "title": p.title,
                "similarity": round(_title_similarity(title, p.title), 2),
            }
            for p in scored[:5]
        ]

    # CatalogProducts do warehouse do AC
    pg_suggestions = []
    if current_user.warehouse_id:
        pg_result = await db.execute(
            select(CatalogProduct).where(
                CatalogProduct.warehouse_id == current_user.warehouse_id,
                CatalogProduct.is_active == True,
            )
        )
        pg_products = pg_result.scalars().all()
        pg_scored = sorted(
            pg_products, key=lambda p: _title_similarity(title, p.title), reverse=True
        )
        pg_suggestions = [
            {
                "id": p.id,
                "sku": p.sku,
                "title": p.title,
                "similarity": round(_title_similarity(title, p.title), 2),
            }
            for p in pg_scored[:5]
        ]

    return {"cmig_suggestions": cmig_suggestions, "pg_suggestions": pg_suggestions}


@router.post("/{listing_id}/link")
async def link_product(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vincula listing a CMIGProduct ou CatalogProduct."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    cmig_product_id = body.get("cmig_product_id")
    catalog_product_id = body.get("catalog_product_id")

    if not cmig_product_id and not catalog_product_id:
        raise HTTPException(status_code=400, detail="Informe cmig_product_id ou catalog_product_id")

    if cmig_product_id:
        # Valida que o produto pertence à CMIG da conta
        r = await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
        product = r.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
        if listing.account.cmig_id and product.cmig_id != listing.account.cmig_id:
            raise HTTPException(status_code=403, detail="Produto não pertence à CMIG desta conta")
        listing.cmig_product_id = cmig_product_id
        listing.catalog_product_id = None

    elif catalog_product_id:
        # Valida que o produto PG pertence ao warehouse do AC
        r = await db.execute(select(CatalogProduct).where(CatalogProduct.id == catalog_product_id))
        product = r.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Produto PG não encontrado")
        if product.warehouse_id and product.warehouse_id != current_user.warehouse_id:
            raise HTTPException(status_code=403, detail="Produto não pertence ao seu galpão")
        listing.catalog_product_id = catalog_product_id
        listing.cmig_product_id = None

    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/unlink")
async def unlink_product(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove o vínculo do listing com qualquer produto."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    listing.cmig_product_id = None
    listing.catalog_product_id = None
    await db.commit()
    return _serialize_listing(listing)


@router.get("/{listing_id}/variation-import-status")
async def get_variation_import_status(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista as variações do anúncio + status de importação de cada uma.

    Retorna `{ has_variations: bool, all_imported: bool, variations: [...] }`
    onde cada item da lista tem:
      - id (variation_id do ML)
      - sku (SELLER_SKU da variação)
      - price, available_quantity
      - attributes_label (ex: "Cor: Vermelho · Tamanho: M")
      - imported: bool
      - cmig_product (se imported): { id, sku_cmig, title }
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)

    variations = []
    if listing.variations_json:
        try:
            variations = _json.loads(listing.variations_json) or []
        except Exception:
            variations = []

    if not variations:
        return {"has_variations": False, "all_imported": False, "variations": []}

    # Carrega CMIGProducts já importados deste listing
    r = await db.execute(
        select(CMIGProduct).where(CMIGProduct.source_listing_id == listing_id)
    )
    imported_by_var: dict[str, CMIGProduct] = {}
    for cp in r.scalars().all():
        if cp.source_variation_id:
            imported_by_var[str(cp.source_variation_id)] = cp

    out = []
    for v in variations:
        var_id = str(v.get("id") or "")
        attrs = v.get("attributes") or v.get("attribute_combinations") or []
        sku = next((a.get("value") or a.get("value_name") for a in attrs if (a.get("id") or "").upper() == "SELLER_SKU"), None)
        # Label dos diferenciadores (cor, tamanho, etc) — pula SELLER_SKU
        diff = [
            f"{a.get('name') or a.get('id')}: {a.get('value') or a.get('value_name')}"
            for a in attrs
            if (a.get("id") or "").upper() != "SELLER_SKU"
            and (a.get("value") or a.get("value_name"))
        ]
        cmig_prod = imported_by_var.get(var_id)
        out.append({
            "id": var_id,
            "sku": sku,
            "price": v.get("price"),
            "available_quantity": v.get("available_quantity"),
            "attributes_label": " · ".join(diff) if diff else "(sem diferenciador)",
            "picture_ids": v.get("picture_ids") or [],
            "imported": cmig_prod is not None,
            "cmig_product": (
                {"id": cmig_prod.id, "sku_cmig": cmig_prod.sku_cmig, "title": cmig_prod.title}
                if cmig_prod else None
            ),
        })

    all_imported = all(x["imported"] for x in out) if out else False
    return {
        "has_variations": True,
        "all_imported": all_imported,
        "variations": out,
    }


@router.post("/{listing_id}/create-cmig-product")
async def create_cmig_product_from_listing(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria um CMIGProduct a partir dos dados do anúncio e vincula automaticamente.

    Se `body.variation_id` for fornecido, cria um CMIGProduct para AQUELA variação
    específica (1 produto por variação, com SKU/EAN/estoque/fotos da variação).
    Caso contrário, comportamento legado: cria 1 produto pai + N CMIGProductVariant.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)

    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=400, detail="cmig_id é obrigatório")

    # Valida acesso à CMIG
    if current_user.role not in ("admin", "ugo"):
        r = await db.execute(
            select(CMIGAdministrator).where(
                CMIGAdministrator.user_id == current_user.id,
                CMIGAdministrator.cmig_id == cmig_id,
            )
        )
        if not r.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Sem acesso a esta CMIG")

    # ─── Modo importação por variação ──────────────────────────────────────
    # Quando o anúncio tem variations_json e o caller passa `variation_id`,
    # criamos 1 CMIGProduct específico daquela variação (SKU/EAN/estoque/fotos
    # vindos da variação, não do nível-pai do anúncio).
    variation_id = body.get("variation_id")
    chosen_variation: dict | None = None
    variation_picture_urls: list[str] = []
    if variation_id and listing.variations_json:
        try:
            all_vars = _json.loads(listing.variations_json) or []
        except Exception:
            all_vars = []
        chosen_variation = next(
            (v for v in all_vars if str(v.get("id")) == str(variation_id)), None
        )
        if not chosen_variation:
            raise HTTPException(
                status_code=404,
                detail=f"Variação {variation_id} não encontrada no anúncio",
            )
        # Bloqueia duplicação — não pode importar a mesma variação 2x
        dup = (await db.execute(
            select(CMIGProduct).where(
                CMIGProduct.source_listing_id == listing_id,
                CMIGProduct.source_variation_id == str(variation_id),
            )
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Variação já importada como CMIGProduct #{dup.id} ({dup.sku_cmig})",
            )
        # Resolve picture_ids → URLs via pictures_json do listing pai
        try:
            pj = _json.loads(listing.pictures_json or "[]")
            url_by_id = {str(p.get("id")): p.get("url") for p in pj if p.get("id") and p.get("url")}
        except Exception:
            url_by_id = {}
        variation_picture_urls = [url_by_id[str(pid)] for pid in (chosen_variation.get("picture_ids") or []) if str(pid) in url_by_id]

    # SKU: prioridade body → SELLER_SKU da variação → sku do listing
    var_seller_sku = None
    if chosen_variation:
        for a in (chosen_variation.get("attributes") or []):
            if (a.get("id") or "").upper() == "SELLER_SKU":
                var_seller_sku = a.get("value") or a.get("value_name")
                break

    sku_cmig = (body.get("sku_cmig") or "").strip() or (var_seller_sku or "").strip() or (listing.sku or "").strip()
    if not sku_cmig:
        raise HTTPException(status_code=400, detail="sku_cmig é obrigatório")

    # Extrai campos fiscais do fiscal_json do anúncio
    fiscal_dict = {}
    if listing.fiscal_json:
        try:
            fiscal_dict = _json.loads(listing.fiscal_json)
        except Exception:
            pass

    # Fallback: busca em attributes_json itens com IDs fiscais e marca
    # (cobre listings importados antes do fiscal_json ou com atributo com ID diferente)
    brand_from_attrs = None
    model_from_attrs = None
    if listing.attributes_json:
        _FISCAL_MAP = {
            "NCM": "ncm",
            "CEST": "cest",
            "GTIN": "gtin",
            "EAN": "ean",
            "FISCAL_CLASSIFICATION": "fiscal_classification",
        }
        try:
            for a in _json.loads(listing.attributes_json):
                aid = (a.get("id") or "").upper()
                key = _FISCAL_MAP.get(aid)
                if key and not fiscal_dict.get(key) and a.get("value"):
                    fiscal_dict[key] = str(a["value"])
                if aid == "BRAND" and a.get("value") and brand_from_attrs is None:
                    brand_from_attrs = str(a["value"])
                if aid == "MODEL" and a.get("value") and model_from_attrs is None:
                    model_from_attrs = str(a["value"])
        except Exception:
            pass

    def _norm_ncm(v):
        """Remove pontos/hífens do NCM; limita a 8 chars."""
        return v.replace(".", "").replace("-", "")[:8] if v else v

    def _norm_cest(v):
        """Remove pontos/hífens do CEST; limita a 7 chars."""
        return v.replace(".", "").replace("-", "")[:7] if v else v

    ncm = _norm_ncm(body.get("ncm") or fiscal_dict.get("ncm"))
    cest = _norm_cest(body.get("cest") or fiscal_dict.get("cest"))
    ean = body.get("ean") or fiscal_dict.get("ean") or fiscal_dict.get("gtin")
    csosn = body.get("csosn") or fiscal_dict.get("csosn")

    # Quando vem por variação, ean/estoque/preço da variação tem prioridade
    if chosen_variation:
        var_ean = next(
            (a.get("value") or a.get("value_name") for a in (chosen_variation.get("attributes") or [])
             if (a.get("id") or "").upper() in ("GTIN", "EAN")),
            None,
        )
        if not body.get("ean") and var_ean:
            ean = var_ean
        var_stock = chosen_variation.get("available_quantity")
        var_price = chosen_variation.get("price")
        # Título: adiciona o diferenciador da variação ao título do listing (ex: " - Vermelho M")
        diff_label = " · ".join(
            f"{a.get('name') or a.get('id')}: {a.get('value') or a.get('value_name')}"
            for a in (chosen_variation.get("attributes") or [])
            if (a.get("id") or "").upper() != "SELLER_SKU"
            and (a.get("value") or a.get("value_name"))
        )
        base_title = body.get("title") or listing.title_override or ""
        product_title = base_title if diff_label and diff_label.lower() in base_title.lower() else (
            f"{base_title} - {diff_label}" if diff_label else base_title
        )
    else:
        var_stock = None
        var_price = None
        product_title = body.get("title") or listing.title_override or ""

    product = CMIGProduct(
        cmig_id=cmig_id,
        sku_cmig=sku_cmig,
        title=product_title[:255],
        description=body.get("description") or listing.description_override,
        brand=body.get("brand") or brand_from_attrs,
        model=body.get("model") or model_from_attrs,
        cost_price=body.get("cost_price"),
        stock_quantity=(var_stock if var_stock is not None else (listing.available_quantity or 0)),
        weight_kg=body.get("weight_kg") or listing.weight_kg,
        height_cm=body.get("height_cm") or listing.height_cm,
        width_cm=body.get("width_cm") or listing.width_cm,
        length_cm=body.get("length_cm") or listing.length_cm,
        ncm=ncm,
        cest=cest,
        ean=ean,
        origin=body.get("origin", 0),
        csosn=csosn,
        suggested_price=body.get("suggested_price") or body.get("sale_price") or var_price or listing.sale_price,
        video_id=body.get("video_id") or listing.video_id,
        attributes_json=listing.attributes_json,
        fiscal_json=listing.fiscal_json,
        source_listing_id=listing_id,
        source_variation_id=str(variation_id) if variation_id else None,
    )
    db.add(product)
    await db.flush()  # gera o ID

    # Importar fotos — variação tem suas próprias fotos (resolved acima); senão usa do listing-pai
    pic_source: list = []
    if chosen_variation and variation_picture_urls:
        pic_source = [{"url": u} for u in variation_picture_urls]
    elif listing.pictures_json:
        try:
            pic_source = _json.loads(listing.pictures_json) or []
        except Exception:
            pic_source = []

    for i, pic in enumerate(pic_source):
        url = pic.get("url") if isinstance(pic, dict) else str(pic)
        if url:
            db.add(
                CMIGProductImage(
                    cmig_product_id=product.id,
                    url=url,
                    sort_order=i,
                    is_primary=(i == 0),
                )
            )

    # Cria CMIGProductVariant legado SOMENTE no fluxo antigo
    # (sem variation_id explícito + listing com variations_json).
    # Quando o caller passa variation_id, cada variação ML vira UM CMIGProduct
    # separado — não criamos variants internas.
    variants_created = 0
    if not chosen_variation and listing.variations_json:
        try:
            variations = _json.loads(listing.variations_json)
            for idx, var in enumerate(variations):
                attrs = var.get("attributes", [])

                var_sku = (
                    next(
                        (a["value"] for a in attrs if a.get("id") == "SELLER_SKU"),
                        None,
                    )
                    or f"{sku_cmig}_{idx + 1}"
                )

                var_attrs = [
                    {"name": a["name"], "value": a["value"]}
                    for a in attrs
                    if a.get("id") != "SELLER_SKU"
                ]

                variant = CMIGProductVariant(
                    cmig_product_id=product.id,
                    sku=var_sku,
                    stock_quantity=var.get("available_quantity", 0),
                    sale_price=var.get("price"),
                    attributes_json=_json.dumps(var_attrs, ensure_ascii=False),
                )
                db.add(variant)
                variants_created += 1
        except Exception:
            pass

    # Vínculo do listing: só faz sentido no fluxo legado (1 listing = 1 produto).
    # Em fluxo por variação (N variações → N CMIGProducts) o listing-pai não tem
    # 1 produto único; o vínculo é por variação via source_listing_id + source_variation_id.
    if not chosen_variation:
        listing.cmig_product_id = product.id
        listing.catalog_product_id = None
    await db.commit()
    await db.refresh(product)

    return {
        "product": {
            "id": product.id,
            "sku_cmig": product.sku_cmig,
            "title": product.title,
            "cmig_id": product.cmig_id,
            "variants_created": variants_created,
            "source_variation_id": product.source_variation_id,
        },
        "listing": _serialize_listing(listing),
    }


# ── Anúncios com Variações ────────────────────────────────────────────────────


def _normalize_combination_key(combination: list[dict]) -> tuple:
    """Chave canônica de uma combinação para detectar duplicatas (ordem-invariante)."""
    items = []
    for c in combination or []:
        key = c.get("id") or c.get("name") or ""
        val = c.get("value_id") or c.get("value_name") or ""
        items.append((str(key), str(val)))
    return tuple(sorted(items))


def _combination_attr_ids(combination: list[dict]) -> set[str]:
    return {str(c.get("id") or c.get("name") or "") for c in (combination or [])}


def _validate_variations_input(source: str, variations: list[dict]) -> None:
    """Valida regras estruturais de variações antes de qualquer chamada externa."""
    if source not in ("pg", "cmig"):
        raise HTTPException(status_code=422, detail="source deve ser 'pg' ou 'cmig'")
    if not variations or not isinstance(variations, list):
        raise HTTPException(status_code=422, detail="variations não pode ser vazio")
    if len(variations) > 100:
        raise HTTPException(
            status_code=422, detail="Máximo de 100 variações por anúncio (limite ML)"
        )

    seen_keys: set[tuple] = set()
    reference_attr_ids: set[str] | None = None

    for idx, var in enumerate(variations, start=1):
        comb = var.get("attribute_combinations") or []
        if not comb:
            raise HTTPException(
                status_code=422,
                detail=f"Variação #{idx}: attribute_combinations não pode ser vazio",
            )
        attr_ids = _combination_attr_ids(comb)
        if reference_attr_ids is None:
            reference_attr_ids = attr_ids
        elif attr_ids != reference_attr_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Variação #{idx}: combinação usa atributos {sorted(attr_ids)} "
                    f"mas a primeira variação usa {sorted(reference_attr_ids)}. "
                    "Todas as variações devem declarar os mesmos atributos."
                ),
            )
        key = _normalize_combination_key(comb)
        if key in seen_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Variação #{idx}: combinação de valores repetida",
            )
        seen_keys.add(key)

        if source == "pg":
            if not var.get("catalog_product_id"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Variação #{idx}: catalog_product_id é obrigatório (source=pg)",
                )
            if var.get("cmig_product_id"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Variação #{idx}: não misture cmig_product_id quando source=pg",
                )
        else:
            if not var.get("cmig_product_id"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Variação #{idx}: cmig_product_id é obrigatório (source=cmig)",
                )
            if var.get("catalog_product_id"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Variação #{idx}: não misture catalog_product_id quando source=cmig",
                )


async def _refresh_product_stock(prod, db: AsyncSession) -> int:
    """Recalcula o cache `stock_quantity` do produto antes de uma publicação.

    O cache event-sourced pode estar stale (pedido recente, NFe finalizada não
    propagada, etc.). Publicar um anúncio é ponto crítico — vale gastar 1 round-trip
    extra para garantir que o ML receba o estoque real.

    Retorna o novo stock_quantity calculado (já gravado no prod via mutação).
    """
    from services.fiscal.stock_calculator import (
        recompute_cmig_product_stock,
        recompute_pg_product_stock,
    )

    if isinstance(prod, CMIGProduct):
        new_stock = await recompute_cmig_product_stock(prod.id, db)
    elif isinstance(prod, CatalogProduct):
        new_stock = await recompute_pg_product_stock(prod.id, db)
    else:
        return int(getattr(prod, "stock_quantity", 0) or 0)

    if new_stock is not None:
        prod.stock_quantity = new_stock
    return int(prod.stock_quantity or 0)


async def _load_variation_product(
    source: str,
    var: dict,
    db: AsyncSession,
    account: MarketplaceAccount,
    user: User,
) -> dict:
    """Carrega o produto (PG ou CMIG) referenciado pela variação e devolve dict normalizado."""
    if source == "pg":
        pid = var["catalog_product_id"]
        r = await db.execute(
            select(CatalogProduct)
            .options(selectinload(CatalogProduct.images))
            .where(CatalogProduct.id == pid)
        )
        prod = r.scalar_one_or_none()
        if not prod:
            raise HTTPException(status_code=404, detail=f"Produto PG #{pid} não encontrado")
        if prod.is_composite:
            raise HTTPException(
                status_code=422,
                detail=f"Produto PG #{pid} é um KIT — variações exigem produtos simples",
            )
        if user.role not in ("admin", "ugo") and user.warehouse_id and prod.warehouse_id and prod.warehouse_id != user.warehouse_id:
            raise HTTPException(
                status_code=403, detail=f"Produto PG #{pid} não pertence ao seu galpão"
            )
        images_sorted = sorted(prod.images or [], key=lambda i: i.sort_order or 0)
        fresh_stock = await _refresh_product_stock(prod, db)
        return {
            "id": prod.id,
            "sku": prod.sku,
            "ean": prod.ean,
            "stock": fresh_stock,
            "price_default": float(prod.suggested_price) if prod.suggested_price else (
                float(prod.cost_price) if prod.cost_price else None
            ),
            "images": [img.url for img in images_sorted if img.url],
        }

    pid = var["cmig_product_id"]
    r = await db.execute(
        select(CMIGProduct)
        .options(selectinload(CMIGProduct.images))
        .where(CMIGProduct.id == pid)
    )
    prod = r.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail=f"Produto CMIG #{pid} não encontrado")
    if prod.is_composite:
        raise HTTPException(
            status_code=422,
            detail=f"Produto CMIG #{pid} é um KIT — variações exigem produtos simples",
        )
    if not account.cmig_id or prod.cmig_id != account.cmig_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Produto CMIG #{pid} pertence à CMIG {prod.cmig_id}, mas a conta "
                f"selecionada está vinculada à CMIG {account.cmig_id}"
            ),
        )
    images_sorted = sorted(prod.images or [], key=lambda i: i.sort_order or 0)
    fresh_stock = await _refresh_product_stock(prod, db)
    return {
        "id": prod.id,
        "sku": prod.sku_cmig,
        "ean": prod.ean,
        "stock": fresh_stock,
        "price_default": float(prod.suggested_price) if prod.suggested_price else (
            float(prod.cost_price) if prod.cost_price else None
        ),
        "images": [img.url for img in images_sorted if img.url],
    }


def _build_ml_variation_obj(
    var_input: dict, loaded: dict, *, include_id: bool = False
) -> dict:
    """Monta o objeto de variação para o payload ML.

    `include_id`: True quando estamos atualizando uma variação que já tem ml_id.
    """
    attrs_var: list[dict] = []
    if loaded.get("sku"):
        attrs_var.append({"id": "SELLER_SKU", "value_name": str(loaded["sku"])})
    ean = loaded.get("ean")
    if ean and _is_valid_ean13(ean):
        attrs_var.append({"id": "GTIN", "value_name": str(ean)})

    price = var_input.get("price_override")
    if price in (None, ""):
        price = loaded.get("price_default")
    if price in (None, ""):
        raise HTTPException(
            status_code=422,
            detail="Preço não informado e produto não tem preço sugerido.",
        )

    stock = max(int(loaded.get("stock") or 0), 0)

    obj: dict = {
        "attribute_combinations": var_input["attribute_combinations"],
        "attributes": attrs_var,
        "price": float(price),
        "available_quantity": stock,
    }
    if include_id and var_input.get("_ml_variation_id"):
        obj["id"] = var_input["_ml_variation_id"]
    return obj


def _consolidate_unique_pictures(parent_urls: list[str], variations_urls: list[list[str]]) -> list[str]:
    """Une URLs preservando ordem (parent primeiro), sem duplicar."""
    seen: set[str] = set()
    result: list[str] = []
    for u in parent_urls or []:
        if u and u not in seen:
            seen.add(u)
            result.append(u)
    for var_pics in variations_urls or []:
        for u in var_pics or []:
            if u and u not in seen:
                seen.add(u)
                result.append(u)
    return result[:12]  # ML aceita até 12 fotos por item


def _build_url_to_pic_id_map(ml_pictures: list[dict] | None) -> dict[str, str]:
    """Mapeia URL → picture_id a partir da resposta do ML (que pode trazer http/https/secure_url)."""
    m: dict[str, str] = {}
    for p in ml_pictures or []:
        pid = p.get("id") or ""
        if not pid:
            continue
        for key in ("url", "secure_url"):
            u = p.get(key)
            if u:
                m[u] = pid
                m[u.replace("http://", "https://")] = pid
                m[u.replace("https://", "http://")] = pid
    return m


def _resolve_picture_ids_for_variation(
    var_pics_urls: list[str], url_to_id: dict[str, str]
) -> list[str]:
    """Resolve URLs de uma variação para picture_ids do ML, mantendo ordem e dedup."""
    out: list[str] = []
    seen: set[str] = set()
    for u in var_pics_urls or []:
        candidates = [
            u,
            _absolutize_image_url(u),
            u.replace("http://", "https://"),
            u.replace("https://", "http://"),
        ]
        pid = next((url_to_id[c] for c in candidates if c in url_to_id), None)
        if pid and pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


async def _prepare_variations_for_ml(
    source: str,
    variations_input: list[dict],
    db: AsyncSession,
    account: MarketplaceAccount,
    user: User,
) -> tuple[list[dict], list[dict], list[list[str]]]:
    """Carrega produtos, valida estoque mínimo e devolve (loaded, ml_var_objects, var_urls_lists)."""
    loaded_list: list[dict] = []
    ml_vars: list[dict] = []
    pics_per_var: list[list[str]] = []
    total_stock = 0

    for var in variations_input:
        loaded = await _load_variation_product(source, var, db, account, user)
        loaded_list.append(loaded)
        ml_vars.append(_build_ml_variation_obj(var, loaded))
        # Fotos: override > do produto
        override = var.get("picture_urls_override")
        var_pics = override if isinstance(override, list) and override else loaded.get("images") or []
        pics_per_var.append(list(var_pics))
        total_stock += max(int(loaded.get("stock") or 0), 0)

    if total_stock <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "Nenhuma variação tem estoque disponível — o ML exige ao menos uma "
                "unidade para publicar. Reabasteça pelo menos um produto antes."
            ),
        )

    return loaded_list, ml_vars, pics_per_var


def _enrich_variations_json(
    ml_variations_returned: list[dict],
    variations_input: list[dict],
    pics_per_var: list[list[str]],
    source: str,
) -> str:
    """Monta o variations_json a salvar — anota _source, _catalog_product_id/_cmig_product_id,
    _pictures_urls e mantém o id ML para sync futuro."""
    enriched: list[dict] = []
    for i, var_ret in enumerate(ml_variations_returned or []):
        original = variations_input[i] if i < len(variations_input) else {}
        # Combinação salva: prefer o que o ML devolveu (já normalizado), caindo no input
        comb = var_ret.get("attribute_combinations") or original.get("attribute_combinations") or []
        attrs_var = var_ret.get("attributes") or []
        enriched.append({
            "id": var_ret.get("id"),
            "attribute_combinations": comb,
            "attributes": attrs_var,
            "price": var_ret.get("price"),
            "available_quantity": var_ret.get("available_quantity"),
            "picture_ids": var_ret.get("picture_ids", []),
            "_source": source,
            "_catalog_product_id": original.get("catalog_product_id"),
            "_cmig_product_id": original.get("cmig_product_id"),
            "_pictures_urls": pics_per_var[i] if i < len(pics_per_var) else [],
        })
    return _json.dumps(enriched, ensure_ascii=False)


@router.post("/publish-with-variations")
async def publish_anuncio_with_variations(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria um anúncio ML com variações vinculadas a produtos PG OU CMIG (origem única)."""
    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")

    account = await _get_account_or_403(account_id, current_user, db)
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=422,
            detail="Anúncios com variações só estão disponíveis para Mercado Livre",
        )
    access_token = await _get_valid_token(account, db)
    await _validate_token_owner(account, access_token)

    source = body.get("source")
    variations_input = body.get("variations") or []
    _validate_variations_input(source, variations_input)

    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title é obrigatório")
    category_id = body.get("category_id")
    if not category_id:
        raise HTTPException(status_code=422, detail="category_id é obrigatório")

    # Confirma que a categoria aceita variações (server-side guard)
    cat_support = await get_category_variation_support(category_id, current_user)
    if not cat_support.get("supports_variations"):
        raise HTTPException(
            status_code=422,
            detail=f"Categoria {category_id} não aceita variações",
        )
    max_vars = cat_support.get("max_variations_allowed")
    if max_vars and len(variations_input) > max_vars:
        raise HTTPException(
            status_code=422,
            detail=f"Categoria aceita no máximo {max_vars} variações (recebido {len(variations_input)})",
        )

    listing_type = body.get("listing_type", "gold_special")
    free_shipping = bool(body.get("free_shipping", False))
    parent_pictures = list(body.get("pictures") or [])
    parent_attributes = list(body.get("attributes") or [])
    model = body.get("model")
    warranty_type = body.get("warranty_type")
    warranty_time = body.get("warranty_time")

    loaded_list, ml_vars, pics_per_var = await _prepare_variations_for_ml(
        source, variations_input, db, account, current_user
    )

    # Fotos consolidadas no nível-pai (capa primeiro, depois únicas das variações)
    all_pics = _consolidate_unique_pictures(parent_pictures, pics_per_var)

    # Atributos do item-pai: MODEL se informado + atributos manuais do formulário
    parent_attrs_out = list(parent_attributes)
    parent_ids = {a.get("id", "").upper() for a in parent_attrs_out}
    if model and "MODEL" not in parent_ids:
        parent_attrs_out.append({"id": "MODEL", "value_name": str(model)})

    # Dimensões: tira do primeiro produto carregado (todos da mesma família via variação)

    ml_payload: dict = {
        "title": title[:60],
        "category_id": category_id,
        "currency_id": "BRL",
        "buying_mode": "buy_it_now",
        "condition": body.get("item_condition") or "new",
        "listing_type_id": listing_type,
        "pictures": [{"source": _absolutize_image_url(u)} for u in all_pics],
        "attributes": parent_attrs_out or [],
        "variations": ml_vars,
        "shipping": {
            "mode": body.get("shipping_mode") or "me2",
            "free_shipping": free_shipping,
        },
    }
    if warranty_type:
        ml_payload["sale_terms"] = [{"id": "WARRANTY_TYPE", "value_name": warranty_type}]
        if warranty_time:
            ml_payload["sale_terms"].append({"id": "WARRANTY_TIME", "value_name": warranty_time})

    # Dimensões do pacote (imutáveis após criação)
    _h = body.get("height_cm")
    _w = body.get("width_cm")
    _l = body.get("length_cm")
    _kg = body.get("weight_kg")
    if _h and _w and _l and _kg:
        ml_payload["shipping"]["dimensions"] = (
            f"{int(float(_h))}x{int(float(_w))}x{int(float(_l))},{int(float(_kg) * 1000)}"
        )

    # 1) POST /items
    ml_item = await ml_service.create_item(access_token, ml_payload)
    platform_item_id = ml_item.get("id")
    ml_pictures = ml_item.get("pictures") or []
    url_to_id = _build_url_to_pic_id_map(ml_pictures)
    ml_vars_returned = list(ml_item.get("variations") or [])

    # 2) PUT /items/{id} para associar picture_ids a cada variação
    need_pictures_update = False
    pictures_update_payload: list[dict] = []
    for i, var_ret in enumerate(ml_vars_returned):
        pic_urls = pics_per_var[i] if i < len(pics_per_var) else []
        pic_ids = _resolve_picture_ids_for_variation(pic_urls, url_to_id)
        if pic_ids and pic_ids != (var_ret.get("picture_ids") or []):
            need_pictures_update = True
        pictures_update_payload.append(
            {
                "id": var_ret.get("id"),
                "attribute_combinations": var_ret.get("attribute_combinations"),
                "attributes": var_ret.get("attributes"),
                "price": var_ret.get("price"),
                "available_quantity": var_ret.get("available_quantity"),
                "picture_ids": pic_ids,
            }
        )

    if need_pictures_update and platform_item_id:
        try:
            updated = await ml_service.update_item_variations(
                access_token, platform_item_id, pictures_update_payload
            )
            ml_vars_returned = list(updated.get("variations") or ml_vars_returned)
        except HTTPException as exc:
            logger.warning(
                "Falha ao associar picture_ids às variações do item %s: %s",
                platform_item_id, exc.detail,
            )

    # 3) Persiste ProductListing
    thumbnail = ml_item.get("secure_thumbnail") or ml_item.get("thumbnail") or (
        all_pics[0] if all_pics else None
    )
    if thumbnail:
        thumbnail = thumbnail.replace("http://", "https://")
    pictures_json = _pictures_to_json(ml_pictures, all_pics)
    variations_json = _enrich_variations_json(
        ml_vars_returned, variations_input, pics_per_var, source
    )

    total_stock = sum(max(int(l.get("stock") or 0), 0) for l in loaded_list)

    listing = ProductListing(
        account_id=account_id,
        cmig_product_id=None,
        catalog_product_id=None,
        platform_item_id=platform_item_id,
        permalink=ml_item.get("permalink") or "",
        thumbnail=thumbnail,
        title_override=title[:60],
        category_id=category_id,
        category_name=cat_support.get("category_name") or "",
        listing_type=listing_type,
        sale_price=float(ml_item.get("price") or ml_vars_returned[0].get("price") or 0),
        available_quantity=total_stock,
        stock_mode="product",
        fixed_quantity=1,
        keep_stock_fixed=False,
        item_condition=body.get("item_condition") or "new",
        warranty_type=warranty_type,
        warranty_time=warranty_time,
        shipping_mode=body.get("shipping_mode") or "me2",
        free_shipping=free_shipping,
        weight_kg=float(_kg) if _kg else None,
        height_cm=float(_h) if _h else None,
        width_cm=float(_w) if _w else None,
        length_cm=float(_l) if _l else None,
        status="published",
        published_at=datetime.now(UTC),
        last_sync_at=datetime.now(UTC),
        pictures_json=pictures_json,
        variations_json=variations_json,
        attributes_json=_json.dumps(parent_attrs_out, ensure_ascii=False) if parent_attrs_out else None,
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    return _serialize_listing(listing)


@router.put("/{listing_id}/variations")
async def update_anuncio_variations(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edita um anúncio com variações: title/model/frete/fotos do nível-pai e o array completo de variações.

    Regra ML: o PUT envia a lista COMPLETA. Variações cujo `_ml_variation_id` não vier
    no body serão removidas do anúncio no ML.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")
    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=422, detail="Edição de variações só para Mercado Livre")

    access_token = await _get_valid_token(listing.account, db)

    source = body.get("source")
    variations_input = body.get("variations") or []
    _validate_variations_input(source, variations_input)

    loaded_list, ml_vars, pics_per_var = await _prepare_variations_for_ml(
        source, variations_input, db, listing.account, current_user
    )

    # Mantém id ML das variações que já existem
    for i, var in enumerate(variations_input):
        if var.get("_ml_variation_id"):
            ml_vars[i]["id"] = var["_ml_variation_id"]

    parent_pictures = list(body.get("pictures") or [])
    all_pics = _consolidate_unique_pictures(parent_pictures, pics_per_var)

    # Etapa 1: PUT atualizando título/fotos do nível-pai + variações sem picture_ids
    update_payload: dict = {"variations": ml_vars}

    title_new = (body.get("title") or "").strip()
    if title_new:
        update_payload["title"] = title_new[:60]

    if all_pics:
        update_payload["pictures"] = [{"source": _absolutize_image_url(u)} for u in all_pics]

    if "free_shipping" in body:
        update_payload["shipping"] = {
            "mode": listing.shipping_mode or "me2",
            "free_shipping": bool(body.get("free_shipping")),
        }

    if "listing_type" in body and body["listing_type"]:
        update_payload["listing_type_id"] = body["listing_type"]

    parent_attributes = list(body.get("attributes") or [])
    model = body.get("model")
    if model:
        ids = {a.get("id", "").upper() for a in parent_attributes}
        if "MODEL" not in ids:
            parent_attributes.append({"id": "MODEL", "value_name": str(model)})
    if parent_attributes:
        update_payload["attributes"] = parent_attributes

    ml_updated = await ml_service.update_item(
        access_token, listing.platform_item_id, update_payload
    )

    # Etapa 2: resolver picture_ids por variação a partir do array `pictures` retornado
    ml_pictures = ml_updated.get("pictures") or []
    url_to_id = _build_url_to_pic_id_map(ml_pictures)
    ml_vars_returned = list(ml_updated.get("variations") or [])

    need_pics_put = False
    pics_payload: list[dict] = []
    for i, var_ret in enumerate(ml_vars_returned):
        pic_urls = pics_per_var[i] if i < len(pics_per_var) else []
        pic_ids = _resolve_picture_ids_for_variation(pic_urls, url_to_id)
        if pic_ids and pic_ids != (var_ret.get("picture_ids") or []):
            need_pics_put = True
        pics_payload.append({
            "id": var_ret.get("id"),
            "picture_ids": pic_ids,
        })

    if need_pics_put:
        try:
            ml_updated = await ml_service.update_item_variations(
                access_token, listing.platform_item_id, pics_payload
            )
            ml_vars_returned = list(ml_updated.get("variations") or ml_vars_returned)
        except HTTPException as exc:
            logger.warning(
                "Falha ao atualizar picture_ids em variações do item %s: %s",
                listing.platform_item_id, exc.detail,
            )

    # Persiste no listing
    if title_new:
        listing.title_override = title_new[:60]
    if "free_shipping" in body:
        listing.free_shipping = bool(body.get("free_shipping"))
    if "listing_type" in body and body["listing_type"]:
        listing.listing_type = body["listing_type"]
    if parent_attributes:
        listing.attributes_json = _json.dumps(parent_attributes, ensure_ascii=False)

    listing.pictures_json = _pictures_to_json(ml_pictures, all_pics)
    listing.variations_json = _enrich_variations_json(
        ml_vars_returned, variations_input, pics_per_var, source
    )
    listing.available_quantity = sum(max(int(l.get("stock") or 0), 0) for l in loaded_list)
    listing.last_sync_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(listing)
    return _serialize_listing(listing)


# ── Grupos de Variação (User Products) ────────────────────────────────────────
# Fluxo: o usuário publica cada cor/tamanho como anúncio individual normal e
# depois cria um "grupo" agrupando os N anúncios via mesma family_name. O ML
# (em categorias User Products) renderiza eles como variações na VIP do produto.


async def _load_listings_for_group(
    listing_ids: list[int], user: User, db: AsyncSession
) -> list[ProductListing]:
    """Carrega N ProductListings garantindo acesso do usuário a todos eles."""
    if not listing_ids:
        raise HTTPException(status_code=422, detail="listing_ids não pode ser vazio")
    seen = set()
    unique_ids = []
    for lid in listing_ids:
        if lid not in seen:
            seen.add(lid)
            unique_ids.append(lid)

    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.account).selectinload(MarketplaceAccount.administrators),
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(ProductListing.id.in_(unique_ids))
    )
    listings = result.scalars().all()
    found_ids = {l.id for l in listings}
    missing = [lid for lid in unique_ids if lid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404, detail=f"Anúncios não encontrados: {missing}"
        )

    # Valida acesso para cada listing — replica regra de _get_listing_or_404
    for listing in listings:
        if user.role in ("admin", "ugo"):
            continue
        admin_ids = {a.user_id for a in listing.account.administrators}
        if user.id in admin_ids:
            continue
        if listing.account.cmig_id:
            r = await db.execute(
                select(CMIGAdministrator).where(
                    CMIGAdministrator.user_id == user.id,
                    CMIGAdministrator.cmig_id == listing.account.cmig_id,
                )
            )
            if r.scalar_one_or_none():
                continue
        raise HTTPException(
            status_code=403, detail=f"Sem acesso ao anúncio #{listing.id}"
        )

    return listings


def _validate_grouping_compatibility(listings: list[ProductListing]) -> None:
    """Valida que os listings podem ser agrupados em uma family no ML.

    Regras:
      - Mesma conta (account_id)
      - Plataforma Mercado Livre (Shopee não tem family_name)
      - Mesma categoria
      - Todos têm platform_item_id (publicados no ML)
      - Status published (não bloqueia paused, mas avisa via warning depois)
    """
    if len(listings) < 2:
        raise HTTPException(
            status_code=422,
            detail="Um grupo de variações precisa ter pelo menos 2 anúncios",
        )
    first = listings[0]
    if first.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=422,
            detail="Agrupamento por family_name só funciona para Mercado Livre",
        )
    for l in listings:
        if l.account_id != first.account_id:
            raise HTTPException(
                status_code=422,
                detail=f"Todos os anúncios devem ser da mesma conta (#{l.id} está em conta diferente)",
            )
        if not l.platform_item_id:
            raise HTTPException(
                status_code=422,
                detail=f"Anúncio #{l.id} não está publicado no Mercado Livre",
            )
        if (l.category_id or "") != (first.category_id or ""):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Categorias divergem: #{first.id}={first.category_id} vs "
                    f"#{l.id}={l.category_id}. Todos precisam estar na mesma categoria."
                ),
            )


def _validate_brand_model_for_grouping(listings: list[ProductListing]) -> None:
    """Valida que todos os listings têm BRAND e MODEL idênticos em attributes_json.

    O ML exige esses atributos iguais para aceitar family_name entre itens.
    Falhar aqui (422) é melhor que o ML rejeitar com erro opaco (502).
    """
    import json as _json

    def _get_attr(listing: ProductListing, attr_id: str) -> str | None:
        raw = listing.attributes_json
        if not raw:
            return None
        try:
            attrs = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None
        for a in attrs:
            if (a.get("id") or "").upper() == attr_id.upper():
                v = a.get("value_name") or a.get("value") or ""
                return str(v).strip().lower() or None
        return None

    first = listings[0]
    first_brand = _get_attr(first, "BRAND")
    first_model = _get_attr(first, "MODEL")

    missing_brand = [l.id for l in listings if not _get_attr(l, "BRAND")]
    if missing_brand:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Anúncios {missing_brand} não têm o atributo BRAND (Marca). "
                "O Mercado Livre exige Marca idêntica em todos os itens do grupo."
            ),
        )

    brand_conflicts = [
        l.id for l in listings if _get_attr(l, "BRAND") != first_brand
    ]
    if brand_conflicts:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Marcas divergem: anúncios {brand_conflicts} têm marcas diferentes de "
                f"#{first.id} ('{first_brand}'). O ML exige a mesma marca em todos os itens do grupo."
            ),
        )

    model_conflicts = [
        l.id for l in listings
        if first_model and _get_attr(l, "MODEL") != first_model
    ]
    if model_conflicts:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Modelos divergem: anúncios {model_conflicts} têm modelos diferentes de "
                f"#{first.id} ('{first_model}'). O ML exige o mesmo modelo em todos os itens do grupo."
            ),
        )


def _default_family_name(listings: list[ProductListing]) -> str:
    """Calcula um family_name padrão removendo a parte variável (cor, voltagem)
    e pegando o prefixo comum dos títulos."""
    titles = [(l.title_override or "").strip() for l in listings if l.title_override]
    if not titles:
        return "Família"
    # prefixo comum char-a-char
    prefix = titles[0]
    for t in titles[1:]:
        i = 0
        while i < len(prefix) and i < len(t) and prefix[i].lower() == t[i].lower():
            i += 1
        prefix = prefix[:i]
    prefix = prefix.strip(" -–—·,/")
    return prefix[:60] or titles[0][:60]


@router.post("/groups", status_code=201)
async def create_variation_group(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria um grupo de variações agrupando N anúncios já publicados via family_name.

    Body:
      - listing_ids: list[int]      — anúncios a agrupar (mín 2, mesma conta+categoria)
      - family_name: str (opcional) — se omitido, usa prefixo comum dos títulos
    """
    import uuid as _uuid

    listing_ids = body.get("listing_ids") or []
    listings = await _load_listings_for_group(listing_ids, current_user, db)
    _validate_grouping_compatibility(listings)
    _validate_brand_model_for_grouping(listings)

    family_name = (body.get("family_name") or "").strip() or _default_family_name(listings)
    family_name = family_name[:120]  # cap defensivo (ML aceita até max_title_length da categoria)

    # Bloqueia se algum listing já estiver em outro grupo (precisa desagrupar antes)
    already_grouped = [l for l in listings if l.variation_group_id]
    if already_grouped:
        groups = {l.variation_group_id for l in already_grouped}
        raise HTTPException(
            status_code=409,
            detail=(
                f"Anúncios {[l.id for l in already_grouped]} já pertencem a outro grupo "
                f"({groups}). Desagrupe-os antes de criar um novo grupo."
            ),
        )

    access_token = await _get_valid_token(listings[0].account, db)

    # Pré-flight: confere status real no ML antes de tentar setar family_name.
    # Anúncios fechados/pausados/deletados rejeitam alterações com cause 374
    # críptico ("The field family name is invalid"). Atualiza o status local
    # quando divergente — o DB pode estar out-of-sync com o ML.
    #
    # Mapeamento ML→local: o DB tem CHECK constraint chk_pl_status restringindo
    # status a ('draft','published','paused','error'). Mapeamos closed/inactive/
    # under_review → 'paused' (semanticamente: "não vendendo agora").
    ML_TO_LOCAL_STATUS = {
        "active": "published",
        "paused": "paused",
        "closed": "paused",
        "inactive": "paused",
        "under_review": "paused",
    }
    mlb_ids = [l.platform_item_id for l in listings if l.platform_item_id]
    ml_family_by_id: dict[str, str | None] = {}
    if mlb_ids:
        try:
            ml_items = await ml_service.get_items_bulk(access_token, mlb_ids)
        except Exception:
            ml_items = []  # falha silenciosa: deixa o PUT abaixo falhar com erro claro
        status_by_id = {item.get("id"): item.get("status") for item in ml_items}
        ml_family_by_id = {item.get("id"): item.get("family_name") for item in ml_items}

        not_active: list[dict] = []
        status_changed = False
        for l in listings:
            real_status = status_by_id.get(l.platform_item_id)
            if real_status and real_status != "active":
                local_status = ML_TO_LOCAL_STATUS.get(real_status, "paused")
                if l.status != local_status:
                    l.status = local_status
                    status_changed = True
                not_active.append({
                    "listing_id": l.id,
                    "platform_item_id": l.platform_item_id,
                    "ml_status": real_status,
                })

        if not_active:
            if status_changed:
                try:
                    await db.commit()
                except Exception as commit_exc:
                    # Falha de commit no sync de status é não-crítica: não pode
                    # bloquear o usuário de ver o erro real (agrupamento falhou).
                    await db.rollback()
                    logger.warning(
                        "Falha ao sincronizar status local dos listings %s: %s",
                        [e["listing_id"] for e in not_active], commit_exc,
                    )
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "listings_not_active",
                    "message": (
                        f"{len(not_active)} anúncio(s) não estão ativos no Mercado Livre "
                        "e não podem ser agrupados."
                    ),
                    "instruction": (
                        "Remova-os da seleção (ou republique se necessário) e tente novamente "
                        "com apenas anúncios ativos."
                    ),
                    "ml_errors": [
                        {
                            "listing_id": e["listing_id"],
                            "error": f"{e['platform_item_id']} está {e['ml_status']} no ML",
                        }
                        for e in not_active
                    ],
                },
            )

    # Detecta se os anúncios já têm family_name setado no ML. Categorias
    # User Products auto-agrupam itens publicados com mesmo family_name e
    # rejeitam reset/alteração via PUT (cause 374 "family name is invalid").
    # Se todos já compartilham o mesmo family_name → registra grupo localmente
    # sem PUT. Se divergem → erro claro.
    existing_families = {
        ml_family_by_id.get(l.platform_item_id)
        for l in listings
        if ml_family_by_id.get(l.platform_item_id)
    }
    all_already_grouped = (
        len(existing_families) == 1
        and all(ml_family_by_id.get(l.platform_item_id) for l in listings)
    )

    if len(existing_families) > 1:
        # Family_names divergentes — não dá pra unificar sem republicar
        raise HTTPException(
            status_code=422,
            detail={
                "type": "family_name_mismatch",
                "message": (
                    "Os anúncios selecionados têm nomes de família diferentes no Mercado "
                    "Livre — não é possível agrupá-los sem republicar."
                ),
                "instruction": (
                    "Selecione anúncios que ainda não foram agrupados, ou anúncios que "
                    "compartilhem o mesmo nome de família no ML."
                ),
                "ml_errors": [
                    {
                        "listing_id": l.id,
                        "error": (
                            f"{l.platform_item_id} → family_name no ML: "
                            f"'{ml_family_by_id.get(l.platform_item_id) or '(vazio)'}'"
                        ),
                    }
                    for l in listings
                ],
            },
        )

    if all_already_grouped:
        # Honra o family_name que o ML já atribuiu (não o que o usuário digitou)
        family_name = next(iter(existing_families))

    group_id = str(_uuid.uuid4())

    # Aplica family_name em cada anúncio no ML — best-effort por anúncio,
    # interrompe no primeiro erro para não deixar grupo parcial.
    # Se all_already_grouped, pula o PUT (ML já agrupou na publicação).
    errors: list[dict] = []
    for l in listings:
        try:
            if not all_already_grouped:
                await ml_service.set_item_family_name(
                    access_token, l.platform_item_id, family_name
                )
            l.variation_group_id = group_id
            l.family_name_ml = family_name
            l.last_sync_at = datetime.now(UTC)
        except Exception as exc:
            err_msg = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            errors.append({"listing_id": l.id, "error": err_msg})
            logger.error("Falha ao aplicar family_name no anúncio #%s: %s", l.id, err_msg)
            # Rollback dos que já foram aplicados
            for prev in listings:
                if prev.id == l.id:
                    break
                try:
                    await ml_service.set_item_family_name(
                        access_token, prev.platform_item_id, None
                    )
                except Exception:
                    pass
                prev.variation_group_id = None
                prev.family_name_ml = None
            # Surface o erro real do ML por listing — não tentamos adivinhar
            # o motivo (cause 374 pode ser "item closed", "BRAND inválida",
            # "family_name inválido", etc.). A UI mostra ml_errors[].
            raise HTTPException(
                status_code=502,
                detail={
                    "message": f"Falha ao agrupar anúncio #{l.id} — grupo não criado",
                    "ml_errors": errors,
                },
            ) from exc

    await db.commit()
    for l in listings:
        await db.refresh(l)

    return {
        "variation_group_id": group_id,
        "family_name": family_name,
        "account_id": listings[0].account_id,
        "category_id": listings[0].category_id,
        "listings": [_serialize_listing(l) for l in listings],
    }


@router.get("/groups")
async def list_variation_groups(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista grupos de variação da conta agregando os listings que compartilham
    variation_group_id."""
    await _get_account_or_403(account_id, current_user, db)

    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(
            ProductListing.account_id == account_id,
            ProductListing.variation_group_id.isnot(None),
        )
        .order_by(ProductListing.variation_group_id, ProductListing.id)
    )
    listings = result.scalars().all()

    groups: dict[str, dict] = {}
    for l in listings:
        gid = l.variation_group_id
        if gid not in groups:
            groups[gid] = {
                "variation_group_id": gid,
                "family_name": l.family_name_ml,
                "account_id": l.account_id,
                "category_id": l.category_id,
                "category_name": l.category_name,
                "listings": [],
            }
        groups[gid]["listings"].append(_serialize_listing(l))

    return list(groups.values())


@router.get("/groups/{group_id}")
async def get_variation_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna detalhes de um grupo: listings + family_name + categoria."""
    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.account).selectinload(MarketplaceAccount.administrators),
            selectinload(ProductListing.cmig_product).selectinload(CMIGProduct.images),
            selectinload(ProductListing.catalog_product).selectinload(CatalogProduct.images),
        )
        .where(ProductListing.variation_group_id == group_id)
        .order_by(ProductListing.id)
    )
    listings = result.scalars().all()
    if not listings:
        raise HTTPException(status_code=404, detail="Grupo de variações não encontrado")

    # Verifica acesso via primeira listing (todas da mesma conta)
    await _get_account_or_403(listings[0].account_id, current_user, db)

    return {
        "variation_group_id": group_id,
        "family_name": listings[0].family_name_ml,
        "account_id": listings[0].account_id,
        "category_id": listings[0].category_id,
        "category_name": listings[0].category_name,
        "listings": [_serialize_listing(l) for l in listings],
    }


@router.post("/groups/{group_id}/add")
async def add_listing_to_variation_group(
    group_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Adiciona um anúncio existente ao grupo (aplica family_name do grupo nele)."""
    listing_id = body.get("listing_id")
    if not listing_id:
        raise HTTPException(status_code=422, detail="listing_id é obrigatório")

    # Carrega grupo existente
    existing = (await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.account).selectinload(MarketplaceAccount.administrators),
        )
        .where(ProductListing.variation_group_id == group_id)
    )).scalars().all()
    if not existing:
        raise HTTPException(status_code=404, detail="Grupo de variações não encontrado")

    # Carrega o novo listing e valida compatibilidade com os do grupo
    new_listings = await _load_listings_for_group([listing_id], current_user, db)
    new_listing = new_listings[0]
    if new_listing.variation_group_id:
        raise HTTPException(
            status_code=409,
            detail=f"Anúncio #{listing_id} já pertence ao grupo {new_listing.variation_group_id}",
        )

    _validate_grouping_compatibility(existing + [new_listing])

    family_name = existing[0].family_name_ml or ""
    access_token = await _get_valid_token(new_listing.account, db)
    await ml_service.set_item_family_name(
        access_token, new_listing.platform_item_id, family_name
    )
    new_listing.variation_group_id = group_id
    new_listing.family_name_ml = family_name
    new_listing.last_sync_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(new_listing)
    return _serialize_listing(new_listing)


@router.post("/groups/{group_id}/remove")
async def remove_listing_from_variation_group(
    group_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove um anúncio do grupo (limpa family_name dele no ML)."""
    listing_id = body.get("listing_id")
    if not listing_id:
        raise HTTPException(status_code=422, detail="listing_id é obrigatório")

    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.variation_group_id != group_id:
        raise HTTPException(
            status_code=409,
            detail=f"Anúncio #{listing_id} não pertence ao grupo {group_id}",
        )

    # Se for o penúltimo, desagrupa tudo (grupo de 1 não faz sentido)
    remaining = (await db.execute(
        select(ProductListing).where(ProductListing.variation_group_id == group_id)
    )).scalars().all()

    access_token = await _get_valid_token(listing.account, db)
    try:
        await ml_service.set_item_family_name(
            access_token, listing.platform_item_id, None
        )
    except HTTPException as exc:
        # Não bloqueia desagrupamento local se o ML falhar — log e segue
        logger.warning(
            "Falha ao limpar family_name do item %s no ML: %s",
            listing.platform_item_id, exc.detail,
        )
    listing.variation_group_id = None
    listing.family_name_ml = None
    listing.last_sync_at = datetime.now(UTC)

    # Se restar só 1 listing no grupo, desagrupa ele também (grupo de 1 = ruído)
    leftover = [l for l in remaining if l.id != listing.id]
    if len(leftover) == 1:
        solo = leftover[0]
        try:
            await ml_service.set_item_family_name(
                access_token, solo.platform_item_id, None
            )
        except HTTPException:
            pass
        solo.variation_group_id = None
        solo.family_name_ml = None
        solo.last_sync_at = datetime.now(UTC)

    await db.commit()
    return {"ok": True, "group_dissolved": len(leftover) <= 1}


@router.delete("/groups/{group_id}", status_code=204)
async def delete_variation_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Desagrupa todos os anúncios do grupo (limpa family_name de cada um no ML)."""
    listings = (await db.execute(
        select(ProductListing)
        .options(selectinload(ProductListing.account).selectinload(MarketplaceAccount.administrators))
        .where(ProductListing.variation_group_id == group_id)
    )).scalars().all()
    if not listings:
        raise HTTPException(status_code=404, detail="Grupo de variações não encontrado")

    await _get_account_or_403(listings[0].account_id, current_user, db)

    access_token = await _get_valid_token(listings[0].account, db)
    for l in listings:
        try:
            await ml_service.set_item_family_name(
                access_token, l.platform_item_id, None
            )
        except HTTPException as exc:
            logger.warning(
                "Falha ao limpar family_name do item %s: %s",
                l.platform_item_id, exc.detail,
            )
        l.variation_group_id = None
        l.family_name_ml = None
        l.last_sync_at = datetime.now(UTC)

    await db.commit()


@router.post("/publish")
async def publish_anuncio(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Publica ou vincula um novo anúncio ao marketplace.
    mode='create' → cria item no ML; mode='link' → valida ID existente.
    """
    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")

    account = await _get_account_or_403(account_id, current_user, db)
    access_token = await _get_valid_token(account, db)
    await _validate_token_owner(account, access_token)

    cmig_product_id = body.get("cmig_product_id")
    catalog_product_id = body.get("catalog_product_id")
    if not cmig_product_id and not catalog_product_id:
        raise HTTPException(status_code=400, detail="Informe cmig_product_id ou catalog_product_id")

    sale_price = body.get("sale_price")
    if not sale_price:
        raise HTTPException(status_code=400, detail="sale_price é obrigatório")

    mode = body.get("mode", "create")
    title_override = body.get("title_override")
    category_id = body.get("category_id")
    listing_type = body.get("listing_type", "gold_special")
    platform_item_id = body.get("platform_item_id")

    # Resolve produto
    product_title = title_override
    if cmig_product_id:
        r = await db.execute(select(CMIGProduct).where(CMIGProduct.id == cmig_product_id))
        prod = r.scalar_one_or_none()
        if not prod:
            raise HTTPException(status_code=404, detail="Produto CMIG não encontrado")
        product_title = product_title or prod.title
    elif catalog_product_id:
        r = await db.execute(select(CatalogProduct).where(CatalogProduct.id == catalog_product_id))
        prod = r.scalar_one_or_none()
        if not prod:
            raise HTTPException(status_code=404, detail="Produto PG não encontrado")
        product_title = product_title or prod.title

    description = body.get("description_override") or body.get("description")
    item_condition = body.get("item_condition") or "new"
    warranty_type = body.get("warranty_type")
    warranty_time = body.get("warranty_time")
    shipping_mode = body.get("shipping_mode") or "me2"
    free_shipping = bool(body.get("free_shipping", False))
    video_id = body.get("video_id")
    attributes_list = body.get("attributes") or []
    attributes_json = body.get("attributes_json")
    if not attributes_json and attributes_list:
        attributes_json = _json.dumps(attributes_list, ensure_ascii=False)
    pictures = body.get("pictures") or []

    # Estoque local
    stock_mode = body.get("stock_mode") or "product"
    fixed_quantity = int(body.get("fixed_quantity") or 1)
    keep_stock_fixed = bool(body.get("keep_stock_fixed", False))
    if stock_mode == "product":
        # Recalcula antes de publicar — o cache pode estar stale (pedido recente,
        # NFe finalizada não propagada). Publicar com estoque desatualizado pode
        # gerar vendas que o vendedor não consegue entregar.
        available_quantity = await _refresh_product_stock(prod, db)
    else:
        available_quantity = fixed_quantity

    fiscal_sync_warning = None
    if mode == "create":
        if not category_id:
            raise HTTPException(
                status_code=400, detail="category_id é obrigatório para criar anúncio"
            )

        cmig_crt = await _resolve_cmig_crt(account, db)
        ml_form = {
            "title_override": product_title,
            "sale_price": sale_price,
            "listing_type": listing_type,
            "category_id": category_id,
            "available_quantity": available_quantity,
            "item_condition": item_condition,
            "warranty_type": warranty_type,
            "warranty_time": warranty_time,
            "shipping_mode": shipping_mode,
            "free_shipping": free_shipping,
            "pictures": pictures,
            "attributes": attributes_list,
            "height_cm": body.get("height_cm"),
            "width_cm": body.get("width_cm"),
            "length_cm": body.get("length_cm"),
            "weight_kg": body.get("weight_kg"),
            "model": body.get("model"),
            "sku": body.get("sku"),
            "fiscal_json": body.get("fiscal_json"),
            "cmig_crt": cmig_crt,
            # family_name é usado em categorias User Products. _build_ml_payload
            # detecta sua presença e inclui no POST /items (substituindo title).
            "family_name": body.get("family_name"),
        }
        ml_item = await _create_ml_item_with_retry(access_token, prod, ml_form)
        platform_item_id = ml_item.get("id")

        # Faturador: cadastra fiscal_information do SKU (endpoint dedicado).
        # Best-effort — não derruba a publicação se falhar.
        sku_for_fiscal = (
            body.get("sku")
            or getattr(prod, "sku_cmig", None)
            or getattr(prod, "sku", None)
        )
        if sku_for_fiscal:
            fiscal_payload = _build_fiscal_payload_from_product(
                prod,
                str(sku_for_fiscal),
                cmig_crt,
                fiscal_overrides=_parse_fiscal_json(body.get("fiscal_json")),
            )
            if fiscal_payload:
                try:
                    fr = await ml_service.register_or_update_fiscal_information(
                        access_token, str(sku_for_fiscal), fiscal_payload
                    )
                    if not fr.get("ok"):
                        fiscal_sync_warning = fr.get("error") or "Erro ao cadastrar fiscal_information"
                        logging.getLogger(__name__).warning(
                            "fiscal_information sync falhou para SKU %s: %s",
                            sku_for_fiscal, fr.get("body"),
                        )
                except Exception as exc:
                    fiscal_sync_warning = f"Exceção ao sincronizar fiscal: {exc}"
                    logging.getLogger(__name__).warning(
                        "Exceção em register_or_update_fiscal_information SKU %s: %s",
                        sku_for_fiscal, exc,
                    )

        if description and platform_item_id:
            try:
                await ml_service.post_item_description(access_token, platform_item_id, description)
            except Exception:
                pass  # não bloqueia criação se descrição falhar
        # ML retorna thumbnail do item criado; fallback para primeira foto enviada
        thumbnail = ml_item.get("secure_thumbnail") or ml_item.get("thumbnail") or (pictures[0] if pictures else None)
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")
        # Persiste fotos no formato {id, url} para a tela de gestão exibir miniaturas
        pictures_json = _pictures_to_json(ml_item.get("pictures"), pictures)
        # family_name_ml: fonte de verdade é o que o ML aceitou no create
        family_name_ml = ml_item.get("family_name")
        status = "published"
        published_at = datetime.now(UTC)
    else:
        if not platform_item_id:
            raise HTTPException(
                status_code=400, detail="platform_item_id é obrigatório para vincular"
            )
        ml_item_data = await ml_service.get_item(access_token, platform_item_id)
        thumbnail = ml_item_data.get("secure_thumbnail") or ml_item_data.get("thumbnail") or (pictures[0] if pictures else None)
        if thumbnail:
            thumbnail = thumbnail.replace("http://", "https://")
        pictures_json = _pictures_to_json(ml_item_data.get("pictures"), pictures)
        # No link mode, herda o family_name que já existir no item ML
        family_name_ml = ml_item_data.get("family_name")
        status = "published"
        published_at = datetime.now(UTC)

    # Dimensões: usa o que veio no body, senão cai no produto
    dim_height = body.get("height_cm") or (
        float(prod.height_cm) if getattr(prod, "height_cm", None) else None
    )
    dim_width = body.get("width_cm") or (
        float(prod.width_cm) if getattr(prod, "width_cm", None) else None
    )
    dim_length = body.get("length_cm") or (
        float(prod.length_cm) if getattr(prod, "length_cm", None) else None
    )
    dim_weight = body.get("weight_kg") or (
        float(prod.weight_kg) if getattr(prod, "weight_kg", None) else None
    )

    listing = ProductListing(
        account_id=account_id,
        cmig_product_id=cmig_product_id,
        catalog_product_id=catalog_product_id,
        platform_item_id=platform_item_id,
        sale_price=sale_price,
        title_override=product_title,
        thumbnail=thumbnail,
        category_id=category_id,
        listing_type=listing_type,
        description_override=description,
        attributes_json=attributes_json,
        available_quantity=available_quantity,
        stock_mode=stock_mode,
        fixed_quantity=fixed_quantity,
        keep_stock_fixed=keep_stock_fixed,
        item_condition=item_condition,
        warranty_type=warranty_type,
        warranty_time=warranty_time,
        shipping_mode=shipping_mode,
        free_shipping=free_shipping,
        video_id=video_id,
        weight_kg=dim_weight,
        height_cm=dim_height,
        width_cm=dim_width,
        length_cm=dim_length,
        status=status,
        published_at=published_at,
        pictures_json=pictures_json,
        family_name_ml=family_name_ml,
        last_sync_at=datetime.now(UTC),
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)

    response = _serialize_listing(listing)
    if fiscal_sync_warning:
        response["fiscal_sync_warning"] = fiscal_sync_warning
    return response


def _extract_differentiator(product) -> tuple[str | None, str | None]:
    """Tenta extrair o atributo diferenciador (cor/tamanho/voltagem) de um produto
    PG/CMIG para usar em anúncios User Products. Retorna (attr_id, value_name).
    Hoje a cobertura é simples — usa apenas o campo `color` do produto se houver.
    """
    color = getattr(product, "color", None)
    if color:
        return ("COLOR", str(color))
    # Próximos passos: também ler de attributes_json/variants se necessário.
    return (None, None)


@router.post("/publish-as-family")
async def publish_anuncios_as_family(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Publica N anúncios compartilhando o mesmo family_name (modelo User Products
    do ML). Cada produto vira um item separado no ML; o ML auto-agrupa pelos
    items que compartilham family_name + BRAND + MODEL idênticos.

    Loop INDEPENDENTE: cada produto é tentado isoladamente. Se falhar, registra
    o erro e segue para o próximo. Resposta inclui resultado por produto.

    Body:
      account_id, source ('pg'|'cmig'), category_id, family_name (compartilhado),
      model, listing_type, free_shipping, item_condition, warranty_type,
      warranty_time, shipping_mode, stock_mode, fixed_quantity, keep_stock_fixed,
      products: [{ product_id, sale_price, pictures, attributes(opcional) }]
    """
    import uuid as _uuid

    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")

    source = (body.get("source") or "").lower()
    if source not in ("pg", "cmig"):
        raise HTTPException(status_code=400, detail="source deve ser 'pg' ou 'cmig'")

    products_input = body.get("products") or []
    if len(products_input) < 2:
        raise HTTPException(
            status_code=400,
            detail="Informe pelo menos 2 produtos para agrupar como família",
        )

    family_name = (body.get("family_name") or "").strip()
    if not family_name:
        raise HTTPException(status_code=400, detail="family_name é obrigatório")
    family_name = family_name[:60]  # ML cap

    category_id = body.get("category_id")
    if not category_id:
        raise HTTPException(status_code=400, detail="category_id é obrigatório")

    account = await _get_account_or_403(account_id, current_user, db)
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=422,
            detail="Agrupamento por family_name só funciona para Mercado Livre",
        )
    access_token = await _get_valid_token(account, db)
    await _validate_token_owner(account, access_token)

    cmig_crt = await _resolve_cmig_crt(account, db)
    model = body.get("model")
    listing_type = body.get("listing_type", "gold_special")
    free_shipping = bool(body.get("free_shipping", False))
    item_condition = body.get("item_condition") or "new"
    warranty_type = body.get("warranty_type")
    warranty_time = body.get("warranty_time")
    shipping_mode = body.get("shipping_mode") or "me2"
    stock_mode = body.get("stock_mode") or "product"
    fixed_quantity = int(body.get("fixed_quantity") or 1)
    keep_stock_fixed = bool(body.get("keep_stock_fixed", False))

    # variation_group_id compartilhado — todos os listings ficam vinculados
    group_id = str(_uuid.uuid4())

    results: list[dict] = []  # por produto: {product_id, ok, listing? error?}

    for p_input in products_input:
        product_id = p_input.get("product_id")
        sale_price = p_input.get("sale_price")
        pictures = p_input.get("pictures") or []

        if not product_id or not sale_price:
            results.append({
                "product_id": product_id,
                "ok": False,
                "error": "product_id e sale_price são obrigatórios",
            })
            continue

        try:
            # Carrega o produto fonte (PG ou CMIG)
            if source == "pg":
                prod = (await db.execute(
                    select(CatalogProduct).where(CatalogProduct.id == product_id)
                )).scalar_one_or_none()
            else:
                prod = (await db.execute(
                    select(CMIGProduct).where(CMIGProduct.id == product_id)
                )).scalar_one_or_none()

            if not prod:
                results.append({
                    "product_id": product_id,
                    "ok": False,
                    "error": f"Produto {source.upper()} #{product_id} não encontrado",
                })
                continue

            # Estoque: recalcula real ou usa fixo
            if stock_mode == "product":
                available_quantity = await _refresh_product_stock(prod, db)
            else:
                available_quantity = fixed_quantity

            # Atributos: mescla atributos manuais + diferenciador inferido do produto
            attrs = list(p_input.get("attributes") or [])
            attr_ids = {(a.get("id") or "").upper() for a in attrs}
            if model and "MODEL" not in attr_ids:
                attrs.append({"id": "MODEL", "value_name": str(model)})
                attr_ids.add("MODEL")

            diff_id, diff_value = _extract_differentiator(prod)
            if diff_id and diff_id not in attr_ids and diff_value:
                attrs.append({"id": diff_id, "value_name": diff_value})

            ml_form = {
                "title_override": (prod.title or "")[:60],
                "sale_price": sale_price,
                "listing_type": listing_type,
                "category_id": category_id,
                "available_quantity": available_quantity,
                "item_condition": item_condition,
                "warranty_type": warranty_type,
                "warranty_time": warranty_time,
                "shipping_mode": shipping_mode,
                "free_shipping": free_shipping,
                "pictures": pictures,
                "attributes": attrs,
                "height_cm": getattr(prod, "height_cm", None),
                "width_cm": getattr(prod, "width_cm", None),
                "length_cm": getattr(prod, "length_cm", None),
                "weight_kg": getattr(prod, "weight_kg", None),
                "model": model,
                "sku": getattr(prod, "sku", None) or getattr(prod, "sku_cmig", None),
                "fiscal_json": p_input.get("fiscal_json"),
                "cmig_crt": cmig_crt,
                "family_name": family_name,
            }

            ml_item = await _create_ml_item_with_retry(access_token, prod, ml_form)
            platform_item_id = ml_item.get("id")

            thumbnail = (
                ml_item.get("secure_thumbnail")
                or ml_item.get("thumbnail")
                or (pictures[0] if pictures else None)
            )
            if thumbnail:
                thumbnail = thumbnail.replace("http://", "https://")
            pictures_json = _pictures_to_json(ml_item.get("pictures"), pictures)
            family_name_ml = ml_item.get("family_name") or family_name

            listing = ProductListing(
                account_id=account_id,
                cmig_product_id=product_id if source == "cmig" else None,
                catalog_product_id=product_id if source == "pg" else None,
                platform_item_id=platform_item_id,
                sale_price=float(sale_price),
                title_override=(prod.title or "")[:60],
                thumbnail=thumbnail,
                category_id=category_id,
                listing_type=listing_type,
                attributes_json=_json.dumps(attrs, ensure_ascii=False) if attrs else None,
                available_quantity=available_quantity,
                stock_mode=stock_mode,
                fixed_quantity=fixed_quantity,
                keep_stock_fixed=keep_stock_fixed,
                item_condition=item_condition,
                warranty_type=warranty_type,
                warranty_time=warranty_time,
                shipping_mode=shipping_mode,
                free_shipping=free_shipping,
                weight_kg=float(prod.weight_kg) if getattr(prod, "weight_kg", None) else None,
                height_cm=float(prod.height_cm) if getattr(prod, "height_cm", None) else None,
                width_cm=float(prod.width_cm) if getattr(prod, "width_cm", None) else None,
                length_cm=float(prod.length_cm) if getattr(prod, "length_cm", None) else None,
                status="published",
                published_at=datetime.now(UTC),
                last_sync_at=datetime.now(UTC),
                pictures_json=pictures_json,
                family_name_ml=family_name_ml,
                variation_group_id=group_id,
            )
            db.add(listing)
            await db.flush()
            results.append({
                "product_id": product_id,
                "ok": True,
                "listing_id": listing.id,
                "platform_item_id": platform_item_id,
            })
        except HTTPException as exc:
            err_msg = str(exc.detail)
            logger.error(
                "publish_anuncios_as_family: produto %s falhou (HTTP %s): %s",
                product_id, exc.status_code, err_msg,
            )
            results.append({
                "product_id": product_id,
                "ok": False,
                "error": err_msg,
            })
        except Exception as exc:
            logger.exception(
                "Falha inesperada em publish_anuncios_as_family produto=%s", product_id
            )
            results.append({
                "product_id": product_id,
                "ok": False,
                "error": f"Erro inesperado: {exc}",
            })

    await db.commit()

    success_count = sum(1 for r in results if r.get("ok"))
    return {
        "variation_group_id": group_id,
        "family_name": family_name,
        "account_id": account_id,
        "category_id": category_id,
        "total": len(results),
        "success_count": success_count,
        "failure_count": len(results) - success_count,
        "results": results,
    }


@router.put("/{listing_id}")
async def update_anuncio(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza anúncio no DB e, se tiver platform_item_id, sincroniza completamente no ML."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    # Salva campos simples no DB
    for field in (
        "sale_price",
        "title_override",
        "category_id",
        "listing_type",
        "description_override",
        "attributes_json",
        "item_condition",
        "warranty_type",
        "warranty_time",
        "shipping_mode",
        "free_shipping",
        "video_id",
        "sku",
        "weight_kg",
        "height_cm",
        "width_cm",
        "length_cm",
        "fiscal_json",
        "stock_mode",
        "fixed_quantity",
        "keep_stock_fixed",
    ):
        if field in body:
            setattr(listing, field, body[field])

    # family_name_ml: atualiza no DB quando vier no body
    if "family_name" in body:
        listing.family_name_ml = body["family_name"] or None

    # Recalcula available_quantity de acordo com o modo de estoque
    new_mode = body.get("stock_mode", listing.stock_mode or "product")
    if new_mode == "fixed":
        listing.available_quantity = int(body.get("fixed_quantity") or listing.fixed_quantity or 1)
    elif "available_quantity" in body:
        listing.available_quantity = int(body["available_quantity"])

    # Converte pictures (array de URLs) → pictures_json no DB
    if "pictures" in body and isinstance(body["pictures"], list):
        listing.pictures_json = (
            _json.dumps(
                [{"id": "", "url": u} for u in body["pictures"] if u],
                ensure_ascii=False,
            )
            if body["pictures"]
            else listing.pictures_json
        )

    listing.last_sync_at = datetime.now(UTC)

    # Cascata de SKU para CMIG/PG vinculado, se solicitada
    cascade_summary = {"cmig_updated": False, "pg_updated": False}
    if body.get("cascade_sku_to_linked") and "sku" in body and body["sku"]:
        new_sku = str(body["sku"]).strip()
        if listing.cmig_product_id and listing.cmig_product:
            cp = listing.cmig_product
            if cp.sku_cmig != new_sku:
                dup = (
                    await db.execute(
                        select(CMIGProduct).where(
                            CMIGProduct.cmig_id == cp.cmig_id,
                            CMIGProduct.sku_cmig == new_sku,
                            CMIGProduct.id != cp.id,
                        )
                    )
                ).scalar_one_or_none()
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cascata abortada: SKU '{new_sku}' já em uso no CMIG (produto #{dup.id})",
                    )
                cp.sku_cmig = new_sku
                cascade_summary["cmig_updated"] = True
        if listing.catalog_product_id and listing.catalog_product:
            pg = listing.catalog_product
            if pg.sku != new_sku:
                dup = (
                    await db.execute(
                        select(CatalogProduct).where(
                            CatalogProduct.sku == new_sku, CatalogProduct.id != pg.id
                        )
                    )
                ).scalar_one_or_none()
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Cascata abortada: SKU '{new_sku}' já em uso no PG #{dup.id}",
                    )
                pg.sku = new_sku
                cascade_summary["pg_updated"] = True

    ml_error: str | None = None
    ml_skipped: list[str] = []
    fiscal_sync_warning: str | None = None

    # Sincroniza ML com payload completo se listing tem platform_item_id
    if listing.platform_item_id and listing.account.platform == "mercadolivre":
        try:
            access_token = await _get_valid_token(listing.account, db)

            cmig_crt = await _resolve_cmig_crt(listing.account, db)
            # Monta form consolidado com dados do body ou do DB como fallback
            form = {
                "title_override": listing.title_override,
                "sale_price": listing.sale_price,
                "listing_type": listing.listing_type or "gold_special",
                "available_quantity": listing.available_quantity or 1,
                "item_condition": listing.item_condition or "new",
                "category_id": listing.category_id,
                "pictures": body.get("pictures") or [],
                "attributes": body.get("attributes") or [],
                "warranty_type": listing.warranty_type,
                "warranty_time": listing.warranty_time,
                "shipping_mode": listing.shipping_mode or "me2",
                "free_shipping": listing.free_shipping or False,
                "sku": body.get("sku") or listing.sku,
                "model": body.get("model"),
                "height_cm": body.get("height_cm"),
                "width_cm": body.get("width_cm"),
                "length_cm": body.get("length_cm"),
                "weight_kg": body.get("weight_kg"),
                "fiscal_json": body.get("fiscal_json") or listing.fiscal_json,
                "cmig_crt": cmig_crt,
                # family_name só pode ser enviado ao ML se o item já foi criado com ele;
                # enviar para um item sem family_name causa cause:374 no PUT.
                "family_name": body.get("family_name") if listing.family_name_ml else None,
            }
            # Se fotos não vieram no body, tenta parsear pictures_json do DB
            if not form["pictures"] and listing.pictures_json:
                try:
                    pics = _json.loads(listing.pictures_json)
                    form["pictures"] = [p.get("url") or p for p in pics if p]
                except Exception:
                    pass

            product = listing.cmig_product or listing.catalog_product
            ml_payload = _build_ml_payload(product, form, for_update=True)
            # ML rejeita mudança de categoria após criação
            ml_payload.pop("category_id", None)
            # ML rejeita title em contas com family_name (não Lojas Oficiais)
            if not getattr(listing.account, "is_official_store", False):
                ml_payload.pop("title", None)
            # Campos imutáveis após criação — ML rejeita com field_not_updatable
            for _f in ("buying_mode", "listing_type_id", "condition"):
                ml_payload.pop(_f, None)
            # Itens de catálogo ML têm estoque gerenciado pelo ML — quantidade não editável
            if listing.ml_catalog_id:
                ml_payload.pop("available_quantity", None)

            # Se atualizamos pictures e o item tem variations registradas no ML, limpa
            # variations[].picture_ids — caso contrário ML reclama dos picture_ids
            # antigos (que podem referenciar URLs relativas inválidas). Após o update
            # as variations herdam as fotos do top-level.
            if "pictures" in ml_payload and listing.variations_json:
                try:
                    _vars = _json.loads(listing.variations_json)
                    _vids = [v.get("id") for v in _vars if v.get("id")]
                    if _vids:
                        ml_payload["variations"] = [
                            {"id": vid, "picture_ids": []} for vid in _vids
                        ]
                except Exception:
                    pass

            ml_resp = await ml_service.update_item(
                access_token, listing.platform_item_id, ml_payload
            )
            ml_skipped = ml_resp.get("_skipped_fields") or []

            # Faturador: sincroniza fiscal_information do SKU (endpoint dedicado).
            # Best-effort — não derruba o update se falhar.
            sku_for_fiscal = body.get("sku") or listing.sku or getattr(product, "sku_cmig", None) or getattr(product, "sku", None)
            if sku_for_fiscal:
                fiscal_payload = _build_fiscal_payload_from_product(
                    product,
                    str(sku_for_fiscal),
                    cmig_crt,
                    fiscal_overrides=_parse_fiscal_json(body.get("fiscal_json") or listing.fiscal_json),
                )
                if fiscal_payload:
                    try:
                        fr = await ml_service.register_or_update_fiscal_information(
                            access_token, str(sku_for_fiscal), fiscal_payload
                        )
                        if not fr.get("ok"):
                            fiscal_sync_warning = fr.get("error") or "Erro ao sincronizar fiscal_information"
                            logging.getLogger(__name__).warning(
                                "fiscal_information sync falhou para SKU %s: %s",
                                sku_for_fiscal, fr.get("body"),
                            )
                    except Exception as exc:
                        fiscal_sync_warning = f"Exceção ao sincronizar fiscal: {exc}"
                        logging.getLogger(__name__).warning(
                            "Exceção em register_or_update_fiscal_information SKU %s: %s",
                            sku_for_fiscal, exc,
                        )

            description = listing.description_override
            if description:
                desc_ok = True
                try:
                    desc_ok = await ml_service.update_item_description(
                        access_token, listing.platform_item_id, description
                    )
                except Exception:
                    try:
                        desc_ok = await ml_service.post_item_description(
                            access_token, listing.platform_item_id, description
                        )
                    except Exception:
                        desc_ok = False
                if desc_ok is False and "description" not in ml_skipped:
                    ml_skipped.append("description")

        except HTTPException as exc:
            ml_error = exc.detail  # token inválido — salva no DB mas não sincroniza ML
        except Exception as exc:
            ml_error = str(exc)

    await db.commit()

    # Atualiza cache de custos + promoção com o preço atual (em background, não bloqueia resposta)
    if listing.platform_item_id and listing.account.platform == "mercadolivre" and not ml_error:
        try:
            _at = await _get_valid_token(listing.account, db)
            _sid = listing.account.platform_user_id or ""
            await _cache_costs(listing, _at, _sid, db)
            await db.commit()
        except Exception:
            pass

    result = _serialize_listing(listing)
    if ml_error:
        result["ml_sync_warning"] = ml_error
    if ml_skipped:
        result["ml_skipped_fields"] = ml_skipped
    if fiscal_sync_warning:
        result["fiscal_sync_warning"] = fiscal_sync_warning
    if cascade_summary["cmig_updated"] or cascade_summary["pg_updated"]:
        result["_cascade"] = cascade_summary
    return result


@router.get("/stats")
async def get_anuncio_stats(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna contagens por status + total vendidos + visitas 7d do ML."""
    account = await _get_account_or_403(account_id, current_user, db)

    rows = await db.execute(
        select(ProductListing.status, func.count().label("cnt"))
        .where(ProductListing.account_id == account_id)
        .group_by(ProductListing.status)
    )
    counts = {row.status: row.cnt for row in rows}

    total_sold = (
        await db.scalar(
            select(func.sum(ProductListing.sold_quantity)).where(
                ProductListing.account_id == account_id
            )
        )
        or 0
    )

    visit_stats: dict = {"total_visits": 0}
    if account.platform == "mercadolivre":
        try:
            access_token = await _get_valid_token(account, db)
            user_info = await ml_service.get_user_info(access_token)
            seller_id = str(user_info.get("id", ""))
            if seller_id:
                visit_stats = await ml_service.get_account_visit_stats(access_token, seller_id)
        except Exception:
            pass

    return {"counts": counts, "total_sold": int(total_sold), "visits": visit_stats}


@router.get("/categories/search")
async def search_categories(
    q: str,
    current_user: User = Depends(get_current_user),
):
    """Busca categorias ML por texto (não requer conta específica)."""
    return await ml_service.search_categories(q)


@router.get("/categories/{category_id}")
async def get_category_info(
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retorna nome e path_from_root de uma categoria ML (endpoint público ML)."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://api.mercadolibre.com/categories/{category_id}")
    if resp.status_code != 200:
        return {"id": category_id, "name": category_id, "path_from_root": []}
    data = resp.json()
    return {
        "id": data.get("id", category_id),
        "name": data.get("name", category_id),
        "path_from_root": data.get("path_from_root", []),
    }


@router.get("/categories/{category_id}/attributes")
async def get_category_attributes(
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retorna todos os atributos de uma categoria ML (exceto read_only)."""
    attrs = await ml_service.get_category_attributes(category_id)
    result = []
    for attr in attrs:
        tags = attr.get("tags") or []
        if "read_only" in tags:
            continue
        is_required = "required" in tags
        is_recommended = "recommended" in tags
        is_optional = not is_required and not is_recommended
        result.append(
            {
                "id": attr.get("id"),
                "name": attr.get("name"),
                "value_type": attr.get("value_type"),
                "is_required": is_required,
                "is_recommended": is_recommended,
                "is_optional": is_optional,
                "allowed_units": attr.get("allowed_units"),
                "values": [
                    {"id": v.get("id"), "name": v.get("name")}
                    for v in (attr.get("values") or [])[:50]
                ],
            }
        )
    return result


@router.get("/categories/{category_id}/variation-support")
async def get_category_variation_support(
    category_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retorna informações sobre suporte a variações de uma categoria ML.

    Critério de detecção:
      1. **Bloqueador**: categoria sob modelo User Products / catalog domain
         (`settings.catalog_domain` não-nulo + atributos com tag `catalog_required`).
         Essas categorias exigem `family_name` no item-pai e o ML **não aceita**
         o campo `variations` junto — retorna 400 `body.invalid_fields`. Sinalizamos
         `supports_variations: false` com `requires_family_name: true` para a UI
         orientar o usuário a usar a publicação normal (1 produto = 1 anúncio).
      2. Algum atributo com tag `allow_variations` → aceita variações por atributo
         da categoria (ex.: COLOR, SIZE, VOLTAGE).
      3. `settings.attribute_types == "variations"` → aceita variações também.
      4. Sem nenhum sinal acima → categoria não aceita variações.
    """
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        cat_resp = await client.get(f"https://api.mercadolibre.com/categories/{category_id}")
    cat_data = cat_resp.json() if cat_resp.status_code == 200 else {}
    settings = cat_data.get("settings") or {}
    attribute_types = settings.get("attribute_types") or ""
    catalog_domain = settings.get("catalog_domain") or None

    attrs = await ml_service.get_category_attributes(category_id)

    combination_attrs: list[dict] = []
    own_attrs: list[dict] = []
    variations_required = False
    has_catalog_required_attr = False

    for attr in attrs:
        tags = attr.get("tags") or {}
        if isinstance(tags, dict):
            tag_keys = set(tags.keys())
        else:
            tag_keys = set(tags or [])

        if "catalog_required" in tag_keys:
            has_catalog_required_attr = True

        allow_variations = "allow_variations" in tag_keys
        variation_attribute = "variation_attribute" in tag_keys
        if not (allow_variations or variation_attribute):
            continue
        is_required = "required" in tag_keys
        if is_required and allow_variations:
            variations_required = True
        entry = {
            "id": attr.get("id"),
            "name": attr.get("name"),
            "value_type": attr.get("value_type"),
            "is_required": is_required,
            "values": [
                {"id": v.get("id"), "name": v.get("name")}
                for v in (attr.get("values") or [])[:200]
            ],
        }
        if allow_variations:
            combination_attrs.append(entry)
        if variation_attribute:
            own_attrs.append(entry)

    has_allow_variations_attr = bool(combination_attrs)
    supports_via_setting = attribute_types == "variations"

    # Modelo User Products: categoria com catalog_domain + atributos catalog_required
    # exige family_name no POST /items e rejeita o campo `variations` (erros do ML:
    # cause 369 "body needs family_name|price|available_quantity" + cause 374
    # "The field variations is invalid with family name").
    #
    # ATENÇÃO: `attribute_types: "variations"` e atributos com tag `allow_variations`
    # NÃO são sinais confiáveis de "aceita variações tradicionais". Categorias como
    # MLB198238 (Foam Roller) expõem ambos os campos mas ainda assim rejeitam o
    # array `variations` na prática (validado em 2026-06-02 com POST real).
    # O único sinal seguro é a presença de catalog_domain + atributos catalog_required.
    # Para essas categorias, o fluxo correto é publicação 1-a-1 via catalog_product_id
    # + opcional agrupamento por family_name depois.
    requires_family_name = bool(catalog_domain) and has_catalog_required_attr
    allows_custom_variations = (
        supports_via_setting
        and not has_allow_variations_attr
        and not requires_family_name
    )

    supports_variations = (
        not requires_family_name
        and (has_allow_variations_attr or supports_via_setting)
    )

    block_reason = None
    if requires_family_name:
        block_reason = (
            f"Esta categoria está sob o modelo User Products do Mercado Livre "
            f"(catalog_domain={catalog_domain}). Nesse modelo, o ML exige family_name no item-pai "
            f"e não permite o campo variations no POST /items. Para publicar nesta "
            f"categoria, use a publicação padrão do Catálogo (1 produto = 1 anúncio)."
        )

    return {
        "category_id": category_id,
        "category_name": cat_data.get("name") or category_id,
        "supports_variations": supports_variations,
        "variations_required": variations_required,
        "allows_custom_variations": allows_custom_variations,
        "requires_family_name": requires_family_name,
        "catalog_domain": catalog_domain,
        "block_reason": block_reason,
        "attribute_types": attribute_types or None,
        "max_variations_allowed": settings.get("max_variations_allowed"),
        "max_pictures_per_item_var": settings.get("max_pictures_per_item_var")
        or settings.get("max_pictures_per_variation"),
        "variation_combination_attrs": combination_attrs,
        "variation_own_attrs": own_attrs,
    }


_DIMENSIONAL_ATTR_IDS = {
    "WEIGHT", "NET_WEIGHT", "GROSS_WEIGHT", "PACKAGE_WEIGHT", "PACKAGE_NET_WEIGHT",
    "HEIGHT", "WIDTH", "LENGTH", "DEPTH",
    "PACKAGE_HEIGHT", "PACKAGE_WIDTH", "PACKAGE_LENGTH", "PACKAGE_DEPTH",
}
_FISCAL_ATTR_IDS = {"GTIN", "EAN", "NCM", "CEST", "FISCAL_CLASSIFICATION"}


def _parse_ml_item_dimensions(item: dict) -> dict:
    """Extrai weight_kg / height_cm / width_cm / length_cm dos atributos do item ML.

    Faz fallback para shipping.dimensions ("HxWxL,weight_g") quando os atributos
    não trazem valor. Espelha a lógica usada em import_anuncios.
    """
    import re as _re

    dim_map: dict = {}
    for attr in item.get("attributes") or []:
        attr_id = (attr.get("id") or "").upper()
        if attr_id not in _DIMENSIONAL_ATTR_IDS:
            continue
        val_name = attr.get("value_name")
        val_struct = attr.get("value_struct") or {}
        val_num = val_struct.get("number")
        unit = val_struct.get("unit") or ""
        if val_num is None and val_name:
            m = _re.match(r"([\d.,]+)\s*(.*)", val_name.strip())
            if m:
                try:
                    val_num = float(m.group(1).replace(",", "."))
                    if not unit:
                        unit = m.group(2).strip()
                except ValueError:
                    pass
        dim_map[attr_id] = {"value": val_num, "unit": unit}

    def _to_kg(key):
        d = dim_map.get(key, {})
        v = d.get("value")
        if v is None:
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        u = (d.get("unit") or "").lower()
        if u in ("g", "gr", "grams", "gramas"):
            return round(v / 1000, 3)
        if u in ("mg", "milligrams"):
            return round(v / 1_000_000, 3)
        return round(v, 3)

    def _to_cm(key):
        d = dim_map.get(key, {})
        v = d.get("value")
        if v is None:
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        u = (d.get("unit") or "").lower()
        if u in ("mm", "millimeters", "milímetros"):
            return round(v / 10, 2)
        if u in ("m", "meters", "metros"):
            return round(v * 100, 2)
        return round(v, 2)

    weight_kg = (
        _to_kg("WEIGHT") or _to_kg("NET_WEIGHT") or _to_kg("GROSS_WEIGHT")
        or _to_kg("PACKAGE_WEIGHT") or _to_kg("PACKAGE_NET_WEIGHT")
    )
    height_cm = _to_cm("HEIGHT") or _to_cm("PACKAGE_HEIGHT")
    width_cm = _to_cm("WIDTH") or _to_cm("PACKAGE_WIDTH")
    length_cm = (
        _to_cm("LENGTH") or _to_cm("DEPTH")
        or _to_cm("PACKAGE_LENGTH") or _to_cm("PACKAGE_DEPTH")
    )

    # Fallback: shipping.dimensions
    shipping = item.get("shipping") or {}
    dims_str = (shipping.get("dimensions") or "").strip()
    if dims_str:
        try:
            parts = dims_str.split(",")
            size_parts = parts[0].strip().lower().split("x")
            if len(size_parts) == 3:
                h, w, l = [float(s.strip()) for s in size_parts]
                if height_cm is None:
                    height_cm = h
                if width_cm is None:
                    width_cm = w
                if length_cm is None:
                    length_cm = l
            if len(parts) >= 2 and weight_kg is None:
                weight_kg = round(float(parts[1].strip()) / 1000, 3)
        except (ValueError, IndexError):
            pass

    return {
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "width_cm": width_cm,
        "length_cm": length_cm,
    }


def _apply_ml_item_to_listing(
    listing: ProductListing,
    item: dict,
    description_text: str | None,
    *,
    preserve_local_stock: bool = True,
) -> None:
    """Aplica os campos de um item ML (resp. de GET /items/{id}) num ProductListing.

    Espelha o caminho de UPDATE do import_anuncios. Sempre preserva o vínculo
    de produto (cmig_product_id / catalog_product_id) — o caller manipula isso
    manualmente se precisar.

    - `preserve_local_stock=True`: NÃO sobrescreve available_quantity em anúncios
      não-Full (preserva o estoque local de cross-docking). Para Full, atualiza
      qty_full lendo do ML.
    """
    title = item.get("title", "") or ""
    permalink = item.get("permalink", "") or ""
    sku = item.get("seller_custom_field") or ""
    price = float(item.get("price") or 0)
    original_price = float(item.get("original_price") or 0)

    if original_price > 0 and price > 0 and original_price > price * 1.01:
        regular_price = original_price
        promo_disc_pct = round((original_price - price) / original_price * 100, 1)
    else:
        regular_price = None
        promo_disc_pct = None

    ml_status = item.get("status", "active")
    status_map = {
        "active": "published", "paused": "paused", "closed": "paused",
        "under_review": "draft", "inactive": "paused",
    }
    item_status = status_map.get(ml_status, "published")

    # Preserva estoque 0 — antes `or 1` virava 1 quando o anuncio estava sem estoque
    _aq = item.get("available_quantity")
    if _aq is None:
        _aq = item.get("initial_quantity")
    available_qty = int(_aq) if _aq is not None else 0
    sold_qty = int(item.get("sold_quantity") or 0)
    item_condition = item.get("condition") or "new"
    listing_type = item.get("listing_type_id") or ""
    category_id = item.get("category_id") or ""

    shipping = item.get("shipping") or {}
    shipping_mode = shipping.get("mode") or "me2"
    free_shipping = bool(shipping.get("free_shipping", False))
    shipping_tags = set(shipping.get("tags") or [])
    logistic_type_raw = (shipping.get("logistic_type") or "cross_docking").lower()
    if "self_service_in" in shipping_tags and logistic_type_raw not in ("fulfillment", "self_service"):
        logistic_type_raw = "self_service"
    is_full = logistic_type_raw == "fulfillment"
    ml_catalog_id = item.get("catalog_product_id") or ""
    catalog_listing = bool(item.get("catalog_listing", False))

    # Fotos
    pics_list = []
    for pic in item.get("pictures", []):
        url = pic.get("secure_url") or pic.get("url", "")
        if url:
            pics_list.append(
                {"id": pic.get("id", ""), "url": url.replace("http://", "https://")}
            )
    thumbnail = item.get("thumbnail", "") or ""
    if not thumbnail and pics_list:
        thumbnail = pics_list[0]["url"]
    if thumbnail:
        thumbnail = thumbnail.replace("http://", "https://")

    # Atributos: dimensional, fiscal, ficha técnica
    fiscal: dict = {}
    tech: list = []
    for attr in item.get("attributes", []):
        attr_id = (attr.get("id") or "").upper()
        if attr_id in _DIMENSIONAL_ATTR_IDS:
            continue
        val_name = attr.get("value_name")
        if attr_id in _FISCAL_ATTR_IDS:
            fiscal_val = val_name or attr.get("value_id")
            if fiscal_val is not None:
                fiscal[attr_id.lower()] = str(fiscal_val)
        elif val_name is not None:
            tech.append({"id": attr_id, "name": attr.get("name"), "value": val_name})

    for term in item.get("sale_terms", []):
        term_id = (term.get("id") or "").upper()
        if term_id in _FISCAL_ATTR_IDS:
            term_val = term.get("value_name") or term.get("value_id")
            if term_val and not fiscal.get(term_id.lower()):
                fiscal[term_id.lower()] = str(term_val)

    # Variações
    variations_list = []
    for var in item.get("variations", []):
        variations_list.append({
            "id": var.get("id"),
            "price": var.get("price"),
            "available_quantity": var.get("available_quantity"),
            "sold_quantity": var.get("sold_quantity"),
            "attributes": [
                {"id": a.get("id"), "name": a.get("name"), "value": a.get("value_name")}
                for a in var.get("attribute_combinations", [])
            ],
            "picture_ids": var.get("picture_ids", []),
        })

    # SKU fallback
    if not sku:
        sku_attr = next(
            (a for a in item.get("attributes", [])
             if (a.get("id") or "").upper() == "SELLER_SKU"),
            None,
        )
        if sku_attr:
            sku = sku_attr.get("value_name") or ""

    dims = _parse_ml_item_dimensions(item)

    pictures_json = _json.dumps(pics_list, ensure_ascii=False) if pics_list else None
    fiscal_json = _json.dumps(fiscal, ensure_ascii=False) if fiscal else None
    variations_json = _json.dumps(variations_list, ensure_ascii=False) if variations_list else None
    attributes_json = _json.dumps(tech, ensure_ascii=False) if tech else None

    # Aplicar no listing (campos sempre sobrescritos)
    listing.title_override = title
    listing.sale_price = price
    listing.status = item_status
    listing.category_id = category_id or listing.category_id
    listing.listing_type = listing_type or listing.listing_type
    listing.is_full = is_full
    listing.logistic_type = logistic_type_raw
    listing.ml_catalog_id = ml_catalog_id or listing.ml_catalog_id
    listing.catalog_listing = catalog_listing
    listing.sold_quantity = sold_qty
    listing.item_condition = item_condition
    listing.shipping_mode = shipping_mode
    listing.free_shipping = free_shipping
    if thumbnail:
        listing.thumbnail = thumbnail
    if permalink:
        listing.permalink = permalink
    if sku:
        listing.sku = sku
    if description_text:
        listing.description_override = description_text
    # Só sobrescreve dimensões quando o ML retornou valor — evita zerar
    # cadastro local quando o anúncio no ML não tem essas infos.
    if dims["weight_kg"] is not None:
        listing.weight_kg = dims["weight_kg"]
    if dims["height_cm"] is not None:
        listing.height_cm = dims["height_cm"]
    if dims["width_cm"] is not None:
        listing.width_cm = dims["width_cm"]
    if dims["length_cm"] is not None:
        listing.length_cm = dims["length_cm"]
    if pictures_json:
        listing.pictures_json = pictures_json
    if fiscal_json:
        listing.fiscal_json = fiscal_json
    if variations_json:
        listing.variations_json = variations_json
    if attributes_json:
        listing.attributes_json = attributes_json

    # Estoque: Full sempre lê do ML; não-Full preserva local se preserve_local_stock=True
    if is_full:
        listing.qty_full = available_qty
        listing.qty_local = 0
        listing.available_quantity = available_qty
    elif not preserve_local_stock:
        listing.available_quantity = available_qty
        listing.qty_local = available_qty
        listing.qty_full = 0
    # else: preserva available_quantity/qty_local locais

    # Promoção
    if regular_price is not None:
        listing.regular_price = regular_price
        listing.promo_discount_pct = promo_disc_pct
    elif (
        listing.regular_price is not None
        and price >= float(listing.regular_price or 0) * 0.99
    ):
        listing.regular_price = None
        listing.promo_type = None
        listing.promo_discount_pct = None

    listing.last_sync_at = datetime.now(UTC)
    # Vínculo de produto (cmig/catalog) e overrides locais nunca são tocados aqui.


def _score_listing_relevance(item: dict, current_platform_item_id: str | None) -> int:
    """Score de "relevância" de um anúncio ML para sugerir qual excluir num conflito.

    Quanto **menor** o score, **menos relevante** (melhor candidato a excluir).
    Pesos refletem o que normalmente importa pro seller:
      +1000 se for o próprio anúncio sendo sincronizado (nunca sugerir excluir)
      +400 se status != closed/paused (anúncio ativo é mais valioso)
      +300 se logistic_type == fulfillment (Full é mais raro/valioso)
      +200 se catalog_listing == true (catálogo costuma vender mais via buy box)
      +sold_quantity (vendas históricas)
      +visits/10 (visitas se disponíveis)
    """
    score = 0
    if current_platform_item_id and item.get("id") == current_platform_item_id:
        score += 1000
    status = (item.get("status") or "").lower()
    if status not in ("closed", "paused", "inactive", "under_review"):
        score += 400
    shipping = item.get("shipping") or {}
    logistic = (shipping.get("logistic_type") or "").lower()
    if logistic == "fulfillment":
        score += 300
    if item.get("catalog_listing"):
        score += 200
    score += int(item.get("sold_quantity") or 0)
    score += int(item.get("visits") or 0) // 10
    return score


async def _build_user_product_conflict_payload(
    *,
    access_token: str,
    listing: ProductListing,
    user_product_id: str,
) -> dict:
    """Monta payload de resposta 409 para o frontend resolver o conflito.

    Retorna o User Product em conflito + lista de MLB ligados a ele com dados de
    título, status, fotos, vendas e logística; também marca o **menos relevante**
    como sugestão de exclusão.
    """
    seller_id = listing.account.platform_user_id or ""
    if not user_product_id and not seller_id:
        return {
            "error": "user_product_repeated_conflict",
            "user_product_id": None,
            "current_item_id": listing.platform_item_id,
            "candidates": [],
            "suggested_delete_item_id": None,
            "message": (
                "O Mercado Livre rejeitou a sincronização por User Product duplicado, "
                "mas não foi possível identificar o anúncio conflitante. "
                "Verifique manualmente no painel do ML."
            ),
        }

    payload: dict = {
        "error": "user_product_repeated_conflict",
        "user_product_id": user_product_id or None,
        "current_item_id": listing.platform_item_id,
        "current_listing_id": listing.id,
        "candidates": [],
        "suggested_delete_item_id": None,
        "message": (
            "Existem anúncios duplicados nesta conta. Escolha qual remover para "
            "concluir a sincronização."
        ),
    }

    item_ids: list[str] = []
    if user_product_id:
        try:
            item_ids = await ml_service.get_items_for_user_product(
                access_token, seller_id, user_product_id
            )
        except Exception:
            item_ids = []

    # Inclui o item atual se ainda não estiver na lista (cenário do "terceiro MLB"
    # que está sendo sincronizado mas ainda não pertence ao UP conflitante).
    if listing.platform_item_id and listing.platform_item_id not in item_ids:
        item_ids.append(listing.platform_item_id)

    items: list[dict] = []
    if item_ids:
        try:
            items = await ml_service.get_items_bulk(access_token, item_ids)
        except Exception:
            items = []

    candidates: list[dict] = []
    for it in items:
        shipping = it.get("shipping") or {}
        candidate = {
            "item_id": it.get("id"),
            "title": it.get("title"),
            "status": it.get("status"),
            "permalink": it.get("permalink"),
            "thumbnail": it.get("thumbnail") or it.get("secure_thumbnail"),
            "price": it.get("price"),
            "sold_quantity": it.get("sold_quantity") or 0,
            "available_quantity": it.get("available_quantity") or 0,
            "catalog_listing": bool(it.get("catalog_listing")),
            "catalog_product_id": it.get("catalog_product_id"),
            "logistic_type": shipping.get("logistic_type"),
            "listing_type_id": it.get("listing_type_id"),
            "is_current": it.get("id") == listing.platform_item_id,
            "relevance_score": _score_listing_relevance(it, listing.platform_item_id),
        }
        candidates.append(candidate)

    candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
    payload["candidates"] = candidates

    # Sugestão de exclusão: o de menor score que não seja o anúncio atual.
    deletable = [c for c in candidates if not c["is_current"]]
    if deletable:
        payload["suggested_delete_item_id"] = min(
            deletable, key=lambda c: c["relevance_score"]
        )["item_id"]

    return payload


@router.post("/{listing_id}/sync-to-ml")
async def sync_listing_to_ml(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sincroniza todos os dados do listing de volta ao ML."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma para sincronizar")

    access_token = await _get_valid_token(listing.account, db)

    # Resolve produto vinculado para preencher campos do payload
    product = listing.cmig_product or listing.catalog_product
    if not product:
        raise HTTPException(
            status_code=400, detail="Anúncio sem produto vinculado para sincronizar"
        )

    form = {
        "title_override": listing.title_override,
        "sale_price": listing.sale_price,
        "listing_type": listing.listing_type,
        "category_id": listing.category_id,
        "available_quantity": listing.available_quantity or 1,
        "item_condition": listing.item_condition or "new",
        "warranty_type": listing.warranty_type,
        "warranty_time": listing.warranty_time,
        "shipping_mode": listing.shipping_mode or "me2",
        "free_shipping": listing.free_shipping or False,
        "attributes": [],
    }
    ml_payload = _build_ml_payload(product, form, for_update=True)
    # Remove category_id from update payload (ML rejects changing category after creation)
    ml_payload.pop("category_id", None)
    # ML rejeita title em contas com family_name (não Lojas Oficiais)
    if not getattr(listing.account, "is_official_store", False):
        ml_payload.pop("title", None)
    # Campos imutáveis após criação — ML rejeita com field_not_updatable
    for _f in ("buying_mode", "listing_type_id", "condition"):
        ml_payload.pop(_f, None)
    # Itens de catálogo ML têm estoque gerenciado pelo ML — quantidade não editável
    if listing.ml_catalog_id:
        ml_payload.pop("available_quantity", None)

    try:
        ml_resp = await ml_service.update_item(
            access_token, listing.platform_item_id, ml_payload
        )
    except ml_service.UserProductRepeatedError as exc:
        # ML rejeitou: o sync deixaria este anúncio idêntico a outro User Product
        # já existente na conta. Devolve 409 com os candidatos para o usuário decidir
        # qual MLB excluir antes de re-tentar.
        conflict = await _build_user_product_conflict_payload(
            access_token=access_token,
            listing=listing,
            user_product_id=exc.user_product_id,
        )
        raise HTTPException(status_code=409, detail=conflict) from exc
    skipped = ml_resp.get("_skipped_fields") or []

    if listing.description_override:
        desc_ok = True
        try:
            desc_ok = await ml_service.update_item_description(
                access_token, listing.platform_item_id, listing.description_override
            )
        except Exception:
            try:
                desc_ok = await ml_service.post_item_description(
                    access_token, listing.platform_item_id, listing.description_override
                )
            except Exception:
                desc_ok = False
        if desc_ok is False and "description" not in skipped:
            skipped.append("description")

    # Nota: a leitura de qty_full (Full) NÃO acontece aqui — foi movida para
    # sync_stock_to_marketplace, que agora trata Full lendo o estoque do ML.
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    result = _serialize_listing(listing)
    if skipped:
        result["ml_skipped_fields"] = skipped
    return result


_CONFLICT_RESOLVE_MAX_ATTEMPTS = 5


@router.post("/{listing_id}/resolve-user-product-conflict")
async def resolve_user_product_conflict(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve um conflito de User Product duplicado fechando o MLB escolhido.

    Body: {
        "delete_item_id": "MLB...",
        "retry_sync": true,
        "attempted_item_ids": ["MLB...", ...]   # ids já fechados em tentativas anteriores
    }

    Fluxo:
      1. Valida que delete_item_id pertence ao mesmo seller (bloqueia por padrão).
      2. Fecha o anúncio no ML via close_item (não tem DELETE direto).
      3. Re-tenta o sync do anúncio original.
      4. Apenas se o sync for bem-sucedido (ou falhar com outro erro que não 409),
         remove o ProductListing local correspondente. Em caso de novo 409, anexa
         `previous_deleted_item_ids` ao detail para o frontend continuar o ciclo
         sem reapresentar o item já fechado e respeitando o cap de tentativas.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    delete_item_id = (body.get("delete_item_id") or "").strip()
    retry_sync = bool(body.get("retry_sync", True))
    attempted = list(body.get("attempted_item_ids") or [])

    if not delete_item_id:
        raise HTTPException(status_code=400, detail="delete_item_id é obrigatório")
    if delete_item_id == listing.platform_item_id:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir o próprio anúncio que está sendo sincronizado",
        )
    if len(attempted) >= _CONFLICT_RESOLVE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Limite de {_CONFLICT_RESOLVE_MAX_ATTEMPTS} tentativas de resolução de "
                "conflito atingido. Investigue manualmente os anúncios no painel do ML."
            ),
        )
    if delete_item_id in attempted:
        raise HTTPException(
            status_code=400,
            detail=f"O anúncio {delete_item_id} já foi processado nesta sessão.",
        )

    access_token = await _get_valid_token(listing.account, db)

    # Confirma que o MLB a excluir pertence à mesma conta — bloqueia por padrão
    # se não der pra confirmar o seller (defesa contra excluir item de outro seller).
    try:
        target = await ml_service.get_item(access_token, delete_item_id)
    except HTTPException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível verificar o anúncio {delete_item_id} no ML: {e.detail}",
        ) from e
    target_seller_id = str(target.get("seller_id") or "")
    account_seller_id = str(listing.account.platform_user_id or "")
    if not target_seller_id or not account_seller_id or target_seller_id != account_seller_id:
        raise HTTPException(
            status_code=403,
            detail="O anúncio a excluir não pertence a esta conta ou não pôde ser confirmado.",
        )

    # Fecha no ML (estado terminal — funcionalmente equivalente ao "excluir")
    try:
        await ml_service.close_item(access_token, delete_item_id)
    except HTTPException as e:
        # ML 4xx/5xx ao fechar — reporta erro mas não toca em estado local
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao fechar o anúncio {delete_item_id} no Mercado Livre: {e.detail}",
        ) from e

    attempted_now = [*attempted, delete_item_id]
    result: dict = {
        "deleted_item_id": delete_item_id,
        "attempted_item_ids": attempted_now,
        "deleted_locally": False,
    }

    if not retry_sync:
        await _apurge_local_listing(db, listing.account_id, delete_item_id, result)
        await db.commit()
        return result

    # Re-tenta o sync do anúncio original. Só deleta o listing local depois do retry
    # para não deixar estado inconsistente caso o ML/rede falhe no meio.
    try:
        sync_result = await sync_listing_to_ml(
            listing_id=listing_id, db=db, current_user=current_user
        )
    except HTTPException as exc:
        if exc.status_code == 409 and isinstance(exc.detail, dict):
            # Outro conflito: anexa contexto e re-propaga sem deletar local agora.
            new_detail = dict(exc.detail)
            new_detail["previous_deleted_item_ids"] = attempted_now
            # Remove dos candidatos os MLBs já fechados (defesa caso ML ainda
            # esteja propagando o estado e retorne o item recém-fechado).
            new_detail["candidates"] = [
                c for c in (new_detail.get("candidates") or [])
                if c.get("item_id") not in attempted_now
            ]
            if new_detail.get("suggested_delete_item_id") in attempted_now:
                deletable = [
                    c for c in new_detail["candidates"]
                    if not c.get("is_current")
                ]
                new_detail["suggested_delete_item_id"] = (
                    min(deletable, key=lambda c: c.get("relevance_score", 0))["item_id"]
                    if deletable else None
                )
            # Limpa o local do MLB já fechado mesmo nesse caminho, para refletir realidade
            await _apurge_local_listing(db, listing.account_id, delete_item_id, result)
            await db.commit()
            raise HTTPException(status_code=409, detail=new_detail) from exc
        # Erro não-409 no retry: NÃO deleta listing local — usuário pode tentar de novo.
        raise

    # Sync OK → seguro deletar listing local do MLB fechado.
    await _apurge_local_listing(db, listing.account_id, delete_item_id, result)
    await db.commit()
    result["sync"] = sync_result
    return result


async def _apurge_local_listing(
    db: AsyncSession, account_id: int, platform_item_id: str, result: dict
) -> None:
    """Localiza e deleta o ProductListing local equivalente a um MLB fechado.

    Não chama commit — o caller controla a transação. Atualiza `result["deleted_locally"]`.
    """
    local = await db.scalar(
        select(ProductListing).where(
            ProductListing.platform_item_id == platform_item_id,
            ProductListing.account_id == account_id,
        )
    )
    if local:
        db.delete(local)
        result["deleted_locally"] = True


@router.post("/{listing_id}/switch-to-cross-docking")
async def switch_to_cross_docking(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Converte anúncio Full para cross-docking usando estoque do galpão do seller.

    Disponível apenas quando qty_full = 0 (sem estoque no galpão do ML).
    Envia ao ML: logistic_type=cross_docking + available_quantity do produto vinculado.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")

    is_full = (listing.logistic_type == "fulfillment") or bool(listing.is_full)
    if not is_full:
        raise HTTPException(status_code=400, detail="Anúncio não está no modo Full")

    if (listing.qty_full or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Anúncio possui {listing.qty_full} unidades no galpão do ML. "
            "Remova o estoque do Full antes de converter.",
        )

    # Use seller warehouse stock from linked product; fall back to 1
    product = listing.cmig_product or listing.catalog_product
    seller_stock = max(int(getattr(product, "stock_quantity", None) or 0), 1) if product else 1

    access_token = await _get_valid_token(listing.account, db)

    import httpx as _httpx

    def _has_cause_code(body: dict, code: str) -> bool:
        return any((c or {}).get("code") == code for c in ml_service._cause_list(body))

    headers = {"Authorization": f"Bearer {access_token}"}
    async with _httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            f"{ml_service.ML_API_BASE}/items/{listing.platform_item_id}",
            headers=headers,
            json={
                "available_quantity": seller_stock,
                "shipping": {"logistic_type": "cross_docking"},
            },
        )

    if resp.status_code not in (200, 201):
        # Detect catalog items where logistic_type is ML-controlled
        is_not_modifiable = False
        if resp.status_code == 400:
            try:
                body = resp.json()
                is_not_modifiable = _has_cause_code(body, "item.shipping.logistic_type.not_modifiable")
            except Exception:
                pass

        if is_not_modifiable:
            seller_center_url = listing.permalink or f"https://www.mercadolivre.com.br/anuncios/{listing.platform_item_id}/modificar"
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Este anúncio é do catálogo do ML — a logística Full não pode ser alterada via API. "
                    f"Acesse o Seller Center para fazer a conversão manualmente: {seller_center_url}"
                ),
            )

        raise HTTPException(
            status_code=400,
            detail=f"Erro ao converter para cross-docking: {resp.text}",
        )

    listing.is_full = False
    listing.logistic_type = "cross_docking"
    listing.qty_full = 0
    listing.qty_local = seller_stock
    listing.available_quantity = seller_stock
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    return _serialize_listing(listing)


def _ml_status_to_local(ml_status: str | None) -> str:
    """Mapeia status do ML para nosso enum local."""
    return {
        "active": "published",
        "paused": "paused",
        "closed": "paused",
        "under_review": "draft",
        "inactive": "paused",
    }.get(ml_status or "", "paused")


@router.post("/{listing_id}/reactivate")
async def reactivate_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reativa anúncio pausado ou fechado no ML.

    Valida que o ML realmente trocou o status — se o ML respondeu 200 mas
    manteve o item no estado anterior (caso raro), levanta erro pro usuário
    saber que precisa agir manualmente no Seller Center.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")

    access_token = await _get_valid_token(listing.account, db)
    quantity = listing.available_quantity or 1
    ml_item = await ml_service.reactivate_item(access_token, listing.platform_item_id, quantity)

    ml_status = (ml_item or {}).get("status")
    if ml_status and ml_status != "active":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mercado Livre aceitou a chamada mas manteve o anúncio como '{ml_status}'. "
                f"Verifique restrições no Seller Center (estoque, qualidade, sub_status)."
            ),
        )

    listing.status = _ml_status_to_local(ml_status) if ml_status else "published"
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/pause")
async def pause_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pausa o anúncio no Mercado Livre.

    Valida que o ML realmente pausou — pause em itens Full/catálogo às vezes
    retorna 200 mas o ML ignora silenciosamente.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma para pausar")

    access_token = await _get_valid_token(listing.account, db)
    ml_item = await ml_service.pause_item(access_token, listing.platform_item_id)

    ml_status = (ml_item or {}).get("status")
    if ml_status and ml_status != "paused":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mercado Livre aceitou a chamada mas manteve o anúncio como '{ml_status}'. "
                f"Anúncios Full ou de catálogo do ML geralmente precisam ser pausados pelo Seller Center."
            ),
        )

    listing.status = _ml_status_to_local(ml_status) if ml_status else "paused"
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()
    return _serialize_listing(listing)


@router.post("/{listing_id}/toggle-flex")
async def toggle_flex_anuncio(
    listing_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ativa/desativa Mercado Envios Flex (self_service) num anúncio.

    Body: {"enable": true|false}

    Usa o endpoint dedicado POST/DELETE /sites/MLB/shipping/selfservice/items/{id}
    (PUT /items com shipping.tags é rejeitado pelo ML como field_not_updatable).
    """
    enable = bool(body.get("enable", True))
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")
    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Flex disponível apenas no Mercado Livre")
    if (listing.logistic_type or "").lower() == "fulfillment":
        raise HTTPException(
            status_code=400,
            detail="Anúncio Full não pode usar Flex (modalidades exclusivas).",
        )
    if enable and not listing.account.effective_has_flex:
        raise HTTPException(
            status_code=400,
            detail="Esta conta não tem Mercado Envios Flex habilitado.",
        )
    if enable and listing.status != "published":
        raise HTTPException(
            status_code=400,
            detail="Anúncio precisa estar publicado para ativar Flex. Reative o anúncio primeiro.",
        )

    access_token = await _get_valid_token(listing.account, db)

    if enable:
        me = await ml_service.get_item_owner_me(access_token)
        me_envios = (me.get("status") or {}).get("mercadoenvios") or "unknown"
        if me_envios != "accepted":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"A conta '{listing.account.platform_username}' não está habilitada para Mercado Envios "
                    f"(status: '{me_envios}'). Acesse Minha conta → Envios no Mercado Livre e aceite o serviço antes de ativar Flex."
                ),
            )

    result = await ml_service.set_item_flex(
        access_token, listing.platform_item_id, enable, site_id="MLB"
    )

    # already_in_state: o item já estava no estado desejado (Flex é opt-out automático).
    # Reusa o logistic_type que veio do GET inicial, sem refetch.
    if result.get("already_in_state"):
        new_logistic = result.get("logistic_type") or ""
    else:
        # Refetch para pegar o estado pós-ação (propagação não é instantânea no ML)
        try:
            ml_item = await ml_service.get_item(access_token, listing.platform_item_id)
            ml_shipping = ml_item.get("shipping") or {}
            ml_tags = set(ml_shipping.get("tags") or [])
            new_logistic = (ml_shipping.get("logistic_type") or "").lower()
            if "self_service_in" in ml_tags and new_logistic not in ("fulfillment", "self_service"):
                new_logistic = "self_service"
        except Exception:
            new_logistic = "self_service" if enable else "cross_docking"

    if new_logistic:
        listing.logistic_type = new_logistic
    listing.last_sync_at = datetime.now(UTC)
    await db.commit()

    result_dict = _serialize_listing(listing)
    if result.get("already_in_state"):
        result_dict["_already_in_state"] = True
    return result_dict


@router.delete("/{listing_id}", status_code=204)
async def delete_anuncio_sistema(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove o anúncio apenas do sistema (não afeta o marketplace)."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    db.delete(listing)
    await db.commit()


@router.get("/{listing_id}/debug-shipping")
async def debug_shipping_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna o objeto shipping bruto do ML para diagnóstico.

    Útil para verificar logistic_type, tags (self_service_in = Flex ativo)
    e comparar com o que está salvo no banco, sem precisar reimportar.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")
    if (listing.account.platform or "") != "mercadolivre":
        raise HTTPException(status_code=400, detail="Debug de shipping disponível apenas para ML")

    access_token = await _get_valid_token(listing.account, db)
    data, selfservice_raw = await ml_service.get_item_and_selfservice(
        access_token, listing.platform_item_id
    )
    shipping = data.get("shipping") or {}
    tags = shipping.get("tags") or []
    return {
        "platform_item_id": listing.platform_item_id,
        "status": data.get("status"),
        "shipping_raw": shipping,
        "logistic_type": shipping.get("logistic_type"),
        "tags": tags,
        "is_flex_by_tag": "self_service_in" in tags,
        "mode": shipping.get("mode"),
        "free_shipping": shipping.get("free_shipping"),
        "db_logistic_type": listing.logistic_type,
        "db_is_flex": (listing.logistic_type or "").lower() == "self_service",
        "selfservice_endpoint": {
            "url": f"GET /sites/MLB/shipping/selfservice/items/{listing.platform_item_id}",
            "status_code": selfservice_raw.get("_status_code"),
            "headers_sent": selfservice_raw.get("headers_sent"),
            "raw": selfservice_raw.get("body"),
        },
    }


@router.get("/{listing_id}/debug-oauth")
async def debug_oauth_anuncio(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico OAuth: verifica scopes concedidos e identidade do token.

    Teste 1 — GET /applications/{app_id}/grants: lista os scopes que o app tem
    com o seller dono deste anúncio. Precisa de 'write' para ativar/desativar Flex.

    Teste 2 — GET /users/me: confirma que o token pertence ao seller dono do anúncio.
    Token de outra conta tentando mexer em item alheio gera 403 imediatamente.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID de plataforma")
    if (listing.account.platform or "") != "mercadolivre":
        raise HTTPException(status_code=400, detail="Debug OAuth disponível apenas para ML")

    access_token = await _get_valid_token(listing.account, db)
    app_id = get_settings().ML_APP_ID

    grants_data, me_data = await ml_service.get_app_grants_and_me(access_token, app_id)

    me_id = str(me_data.get("id") or "")
    account_seller_id = str(listing.account.platform_user_id or "")
    me_status = me_data.get("status") or {}
    mercadoenvios_status = me_status.get("mercadoenvios") or "unknown"
    mercadoenvios_ok = mercadoenvios_status == "accepted"

    grants_error = grants_data.get("error")
    grants_note = (
        "Endpoint /grants exige credencial do dono do app (não do seller) — use o token da aplicação para checar scopes"
        if grants_error else None
    )

    return {
        "app_id": app_id,
        "platform_item_id": listing.platform_item_id,
        "account_name": listing.account.platform_username or listing.account.platform_user_id,
        "test_1_grants": {
            "raw": grants_data,
            "note": grants_note,
            "diagnosis": "Inconclusivo — endpoint /grants requer token do app owner, não do seller",
        },
        "test_2_users_me": {
            "token_user_id": me_id,
            "account_seller_id": account_seller_id,
            "ids_match": me_id == account_seller_id,
            "mercadoenvios_status": mercadoenvios_status,
            "mercadoenvios_accepted": mercadoenvios_ok,
            "diagnosis_token": "OK — token é do dono do anúncio" if me_id == account_seller_id else f"PROBLEMA — token é do user {me_id}, mas anúncio pertence ao seller {account_seller_id}",
            "diagnosis_envios": "OK — Mercado Envios aceito" if mercadoenvios_ok else f"BLOQUEADOR — mercadoenvios='{mercadoenvios_status}'. A conta precisa aceitar o Mercado Envios no painel ML antes de gerenciar Flex via API.",
        },
    }


@router.delete("/{listing_id}/marketplace", status_code=204)
async def delete_anuncio_marketplace(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fecha o anúncio no marketplace e depois remove do sistema."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.platform_item_id:
        access_token = await _get_valid_token(listing.account, db)
        await ml_service.close_item(access_token, listing.platform_item_id)
    db.delete(listing)
    await db.commit()


@router.get("/{listing_id}/costs")
async def get_anuncio_costs(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna custos reais (comissão ML + frete) de um anúncio consultando a API do Mercado Livre."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if listing.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Consulta de custos disponível apenas para Mercado Livre"
        )
    if not listing.sale_price:
        raise HTTPException(status_code=400, detail="Anúncio sem preço definido")
    if not listing.category_id:
        raise HTTPException(status_code=400, detail="Anúncio sem categoria definida")

    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""

    # Busca preço real e detecta automação de preço — em paralelo
    promo_info: dict = {}
    real_price = float(listing.sale_price)
    auto_price_adj = False
    if listing.platform_item_id:
        try:
            import asyncio as _aio

            promo_info, auto_info = await _aio.gather(
                ml_service.get_sale_price_info(access_token, listing.platform_item_id),
                ml_service.get_item_auto_pricing(access_token, listing.platform_item_id),
            )
            if promo_info.get("sale_price") and float(promo_info["sale_price"]) > 0:
                real_price = float(promo_info["sale_price"])
                listing.sale_price = real_price
            promo_type_live = (
                promo_info.get("promotion_type") if promo_info.get("has_promotion") else None
            )
            if promo_info.get("has_promotion"):
                listing.regular_price = promo_info.get("regular_price")
                listing.promo_type = promo_type_live
                listing.promo_discount_pct = promo_info.get("discount_pct")
            else:
                listing.regular_price = None
                listing.promo_type = None
                listing.promo_discount_pct = None
            # Detecção via /items/{id}/prices e tags — fonte correta para automação de preço
            auto_price_adj = auto_info["is_auto"]
            listing.has_auto_price_adj = auto_price_adj
        except Exception:
            pass

    logistic_type = (listing.logistic_type or "").strip().lower() or (
        "fulfillment" if listing.is_full else "cross_docking"
    )

    costs = await ml_service.get_listing_costs(
        access_token=access_token,
        seller_id=seller_id,
        price=real_price,
        category_id=listing.category_id,
        listing_type=listing.listing_type or "gold_special",
        shipping_mode=listing.shipping_mode or "me2",
        logistic_type=logistic_type,
        weight_kg=float(listing.weight_kg) if listing.weight_kg else None,
        height_cm=float(listing.height_cm) if listing.height_cm else None,
        width_cm=float(listing.width_cm) if listing.width_cm else None,
        length_cm=float(listing.length_cm) if listing.length_cm else None,
        free_shipping=bool(listing.free_shipping),
    )

    # Para Full: se a API não retornou custo (timeout, indisponível, dims ausentes),
    # usa tabela local ml_full_tariffs como fallback.
    shipping_cost_final = float(costs.get("shipping_cost") or 0)
    if (
        logistic_type == "fulfillment"
        and shipping_cost_final == 0
        and listing.weight_kg
        and listing.height_cm
        and listing.width_cm
        and listing.length_cm
    ):
        wb = ml_service._calc_billable_weight(
            float(listing.weight_kg),
            float(listing.height_cm),
            float(listing.width_cm),
            float(listing.length_cm),
        )
        tier = ml_service.reputation_tier_for_account(listing.account)
        full_tariff = await ml_service.get_full_shipping_cost(
            wb["billable_kg"],
            real_price,
            tier,
            db,
            free_shipping=bool(listing.free_shipping),
        )
        if full_tariff > 0:
            commission = float(costs.get("commission_amount") or 0)
            fixed_fee = float(costs.get("fixed_fee") or 0)
            financing = float(costs.get("financing_fee") or 0)
            total = commission + full_tariff + fixed_fee + financing
            costs = {
                **costs,
                "shipping_cost": round(full_tariff, 2),
                "total_cost": round(total, 2),
                "net_revenue": round(real_price - total, 2),
                "margin_pct": round(((real_price - total) / real_price) * 100, 2)
                if real_price > 0
                else 0.0,
                "shipping_source": "local_table_fallback",
            }

    # Persiste os custos calculados para evitar recalculo e manter histórico
    listing.commission_pct = costs.get("commission_pct")
    listing.commission_amount = costs.get("commission_amount")
    listing.shipping_cost = costs.get("shipping_cost")
    listing.net_revenue = costs.get("net_revenue")
    listing.margin_pct = costs.get("margin_pct")
    listing.costs_cached_at = datetime.now(UTC)
    await db.commit()

    # Devolve custos + dados de promoção + flag de ajuste automático
    return {**costs, **promo_info, "has_auto_price_adj": auto_price_adj}


@router.post("/sync-stock")
async def sync_stock_to_marketplace(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sincroniza estoque entre Sistema Drop e Marketplace.

    Dois ramos numa única passada:
    - **Anúncios não-Full**: envia `stock_quantity` do produto vinculado ao ML/Shopee.
    - **Anúncios Full** (`logistic_type='fulfillment'`): lê `available_quantity` do ML
      e atualiza `listing.qty_full` localmente (estoque do Full é gerenciado pelo ML).

    Body:
      - `account_id` (obrigatório)
      - `listing_ids` (opcional): se presente, filtra apenas esses listings da conta.
        Se omitido/vazio, processa todos os publicados da conta.
    """
    from services import shopee_service

    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")

    account = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == account_id)
        )
    ).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Verifica acesso do usuário à conta
    if current_user.role not in ("admin", "ugo"):
        from models.user import AccountAdministrator
        admin = (
            await db.execute(
                select(AccountAdministrator).where(
                    AccountAdministrator.user_id == current_user.id,
                    AccountAdministrator.account_id == account_id,
                )
            )
        ).scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=403, detail="Acesso negado a esta conta")

    # Busca token válido para ML; Shopee usa token raw
    access_token = None
    if account.platform == "mercadolivre":
        access_token = await _get_valid_token(account, db)
    elif account.platform == "shopee":
        if not account.access_token:
            raise HTTPException(status_code=401, detail="Conta Shopee sem token de acesso.")
        access_token = account.access_token
    else:
        raise HTTPException(status_code=400, detail=f"Plataforma '{account.platform}' não suportada para sync de estoque")

    # Carrega listings com produto vinculado.
    # - Sem listing_ids: apenas published (chamada automática do scheduler).
    # - Com listing_ids: respeita seleção do usuário e reporta status != published
    #   como skipped explícito em error_details.
    q = (
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product),
            selectinload(ProductListing.catalog_product),
        )
        .where(ProductListing.account_id == account_id)
    )
    if listing_ids:
        q = q.where(ProductListing.id.in_(listing_ids))
    else:
        q = q.where(ProductListing.status == "published")
    listings = (await db.execute(q)).scalars().all()

    updated = 0
    skipped = 0
    errors = 0
    full_read = 0
    full_read_errors = 0
    error_details = []

    # Quando listing_ids é fornecido, registra IDs não encontrados
    if listing_ids:
        found_ids = {lst.id for lst in listings}
        for lid in listing_ids:
            if lid not in found_ids:
                skipped += 1
                error_details.append({
                    "listing_id": lid,
                    "stage": "not_found",
                    "error": "Anúncio não pertence à conta ou não existe.",
                })

    now = datetime.now(UTC)

    for lst in listings:
        # status != published quando explicitamente selecionado pelo user:
        # reporta como skipped pra ele entender o que aconteceu
        if listing_ids and lst.status != "published":
            skipped += 1
            error_details.append({
                "listing_id": lst.id,
                "platform_item_id": lst.platform_item_id,
                "stage": "not_published",
                "error": f"Status do anúncio é '{lst.status}' — só anúncios publicados podem sincronizar estoque.",
            })
            continue

        # Sem ID no marketplace — não dá pra atualizar nem ler
        if not lst.platform_item_id:
            skipped += 1
            continue

        is_full = (lst.logistic_type == "fulfillment") or bool(lst.is_full)

        # Ramo Full: ler qty_full do ML
        if is_full:
            if account.platform != "mercadolivre":
                # Shopee não tem conceito de Full do ML — pula
                skipped += 1
                continue
            try:
                ml_item = await ml_service.get_item(access_token, lst.platform_item_id)
                lst.qty_full = int(ml_item.get("available_quantity") or 0)
                lst.qty_local = 0
                lst.available_quantity = lst.qty_full
                lst.last_sync_at = now
                full_read += 1
            except Exception as exc:
                full_read_errors += 1
                error_details.append({
                    "listing_id": lst.id,
                    "platform_item_id": lst.platform_item_id,
                    "stage": "full_read",
                    "error": str(exc),
                })
            continue

        # Ramo não-Full: enviar stock_quantity do produto vinculado ao marketplace
        if lst.stock_mode == "fixed":
            skipped += 1
            continue

        stock = None
        if lst.cmig_product_id and lst.cmig_product:
            stock = int(lst.cmig_product.stock_quantity or 0)
        elif lst.catalog_product_id and lst.catalog_product:
            stock = int(lst.catalog_product.stock_quantity or 0)

        if stock is None:
            skipped += 1
            continue

        # Garante estoque não-negativo
        stock = max(0, stock)

        try:
            if account.platform == "mercadolivre":
                await ml_service.update_item_stock(access_token, lst.platform_item_id, stock)
            elif account.platform == "shopee":
                await shopee_service.update_item_stock(
                    access_token, account.shop_id, int(lst.platform_item_id), stock
                )

            lst.available_quantity = stock
            lst.last_sync_at = now
            updated += 1
        except Exception as exc:
            errors += 1
            error_details.append({
                "listing_id": lst.id,
                "platform_item_id": lst.platform_item_id,
                "stage": "stock_push",
                "error": str(exc),
            })

    await db.commit()

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "full_read": full_read,
        "full_read_errors": full_read_errors,
        "error_details": error_details,
    }


@router.post("/sync-to-ml-batch")
async def sync_to_ml_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envia em lote o anúncio inteiro (título, preço, atributos, fotos, descrição)
    para o Marketplace, reusando a lógica do `sync_listing_to_ml` por listing.

    Cada listing é commitado individualmente (via sync_listing_to_ml) — falhas
    não revertem itens já sincronizados.

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "processed": int, "errors": [{listing_id, code, detail}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    # Valida ownership da conta e filtra listings ao escopo dela
    await _get_account_or_403(account_id, current_user, db)

    valid_ids_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    valid_ids = set(valid_ids_result.scalars().all())
    out_of_scope = [lid for lid in listing_ids if lid not in valid_ids]

    processed = 0
    errors: list[dict] = []
    for lid in out_of_scope:
        errors.append({
            "listing_id": lid,
            "code": 403,
            "detail": "Anúncio não pertence à conta informada.",
        })

    for lid in listing_ids:
        if lid not in valid_ids:
            continue
        try:
            await sync_listing_to_ml(listing_id=lid, db=db, current_user=current_user)
            processed += 1
        except HTTPException as exc:
            # 409 user_product_repeated_conflict: detalha pra UI decidir
            errors.append({
                "listing_id": lid,
                "code": exc.status_code,
                "detail": exc.detail,
            })
        except Exception as exc:  # noqa: BLE001 — captura genérica intencional
            logger.exception("sync_to_ml_batch: erro inesperado em listing %s", lid)
            errors.append({
                "listing_id": lid,
                "code": 500,
                "detail": f"Erro interno ({exc.__class__.__name__})",
            })

    return {"processed": processed, "errors": errors}


@router.post("/reimport-batch")
async def reimport_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-importa em lote a info do Marketplace para os listings selecionados.

    Para cada listing, busca `/items/{id}` + descrição no ML e aplica em
    ProductListing PRESERVANDO:
      - vínculo de produto (cmig_product_id / catalog_product_id)
      - available_quantity local (apenas em anúncios não-Full)

    Sobrescreve tudo o mais que vem do ML: title, atributos, fotos, status,
    preço, garantia, modo de envio, listing_type. Para Full, atualiza qty_full.

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "updated": int, "errors": [{listing_id, error}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    account = await _get_account_or_403(account_id, current_user, db)
    if account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Re-importação suporta apenas Mercado Livre"
        )
    access_token = await _get_valid_token(account, db)

    updated = 0
    errors: list[dict] = []

    # Carrega os listings em uma query só
    result = await db.execute(
        select(ProductListing)
        .options(
            selectinload(ProductListing.cmig_product),
            selectinload(ProductListing.catalog_product),
        )
        .where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    listings = result.scalars().all()

    # Validação rápida: IDs solicitados mas não pertencentes à conta
    found_ids = {lst.id for lst in listings}
    missing = set(listing_ids) - found_ids
    for mid in missing:
        errors.append({"listing_id": mid, "error": "Anúncio não encontrado ou sem acesso"})

    # Busca itens + descrições do ML em paralelo (por chunks de 20 do bulk endpoint)
    platform_ids = [lst.platform_item_id for lst in listings if lst.platform_item_id]
    ml_items: list[dict] = []
    descriptions: dict[str, str] = {}
    if platform_ids:
        try:
            ml_items = await ml_service.get_items_bulk(access_token, platform_ids)
            descriptions = await ml_service.get_items_descriptions(access_token, platform_ids)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Falha ao consultar ML: {exc}"
            ) from exc

    items_by_id = {it.get("id"): it for it in ml_items}

    for lst in listings:
        if not lst.platform_item_id:
            errors.append({"listing_id": lst.id, "error": "Anúncio sem platform_item_id"})
            continue
        item = items_by_id.get(lst.platform_item_id)
        if not item:
            errors.append({
                "listing_id": lst.id, "error": f"ML não retornou dados para {lst.platform_item_id}"
            })
            continue
        try:
            _apply_ml_item_to_listing(
                lst,
                item,
                descriptions.get(lst.platform_item_id) or "",
                preserve_local_stock=True,
            )
            updated += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("reimport_batch: erro inesperado em listing %s", lst.id)
            errors.append({
                "listing_id": lst.id,
                "error": f"Erro interno ({exc.__class__.__name__})",
            })

    await db.commit()
    return {"updated": updated, "errors": errors}


@router.post("/reactivate-batch")
async def reactivate_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reativa em lote anúncios pausados.

    Reusa a lógica de `reactivate_anuncio` por listing — cada chamada faz commit
    independente, então falhas parciais não revertem itens já reativados.

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "processed": int, "errors": [{listing_id, code, detail}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    await _get_account_or_403(account_id, current_user, db)

    valid_ids_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    valid_ids = set(valid_ids_result.scalars().all())
    out_of_scope = [lid for lid in listing_ids if lid not in valid_ids]

    processed = 0
    errors: list[dict] = []
    for lid in out_of_scope:
        errors.append({
            "listing_id": lid,
            "code": 403,
            "detail": "Anúncio não pertence à conta informada.",
        })

    for lid in listing_ids:
        if lid not in valid_ids:
            continue
        try:
            await reactivate_anuncio(listing_id=lid, db=db, current_user=current_user)
            processed += 1
        except HTTPException as exc:
            errors.append({
                "listing_id": lid,
                "code": exc.status_code,
                "detail": exc.detail,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("reactivate_batch: erro inesperado em listing %s", lid)
            errors.append({
                "listing_id": lid,
                "code": 500,
                "detail": f"Erro interno ({exc.__class__.__name__})",
            })

    return {"processed": processed, "errors": errors}


@router.post("/switch-to-cross-docking-batch")
async def switch_to_cross_docking_batch(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Converte em lote anúncios Full (qty_full=0) para cross-docking.

    Anúncios que não são Full ou que possuem estoque no galpão do ML são ignorados
    (não contam como erro).

    Body: { "account_id": int, "listing_ids": [int, ...] }
    Retorno: { "processed": int, "skipped": int, "errors": [{listing_id, code, detail}] }
    """
    account_id = body.get("account_id")
    listing_ids: list[int] = list(body.get("listing_ids") or [])
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id é obrigatório")
    if not listing_ids:
        raise HTTPException(status_code=400, detail="listing_ids é obrigatório (lista não vazia)")

    await _get_account_or_403(account_id, current_user, db)

    valid_ids_result = await db.execute(
        select(ProductListing.id).where(
            ProductListing.account_id == account_id,
            ProductListing.id.in_(listing_ids),
        )
    )
    valid_ids = set(valid_ids_result.scalars().all())

    processed = 0
    skipped = 0
    errors: list[dict] = []

    for lid in listing_ids:
        if lid not in valid_ids:
            errors.append({
                "listing_id": lid,
                "code": 403,
                "detail": "Anúncio não pertence à conta informada.",
            })
            continue
        try:
            await switch_to_cross_docking(listing_id=lid, db=db, current_user=current_user)
            processed += 1
        except HTTPException as exc:
            # Anúncio não é Full, sem ID de plataforma, ou tem estoque no galpão → ignora
            _detail = exc.detail or ""
            _skip = exc.status_code == 400 and (
                _detail == "Anúncio não está no modo Full"
                or _detail == "Anúncio sem ID de plataforma"
                or "unidades no galpão" in _detail
            )
            if _skip:
                skipped += 1
            else:
                errors.append({
                    "listing_id": lid,
                    "code": exc.status_code,
                    "detail": exc.detail,
                })
        except Exception as exc:  # noqa: BLE001
            logger.exception("switch_to_cross_docking_batch: erro inesperado em listing %s", lid)
            errors.append({
                "listing_id": lid,
                "code": 500,
                "detail": f"Erro interno ({exc.__class__.__name__})",
            })

    return {"processed": processed, "skipped": skipped, "errors": errors}


@router.get("/{listing_id}/costs-debug")
async def get_anuncio_costs_debug(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico do cálculo de frete — retorna raw do ML + motivo de skip.

    Usado pra investigar casos onde o frete vem 0 mesmo com seller pagando.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Diagnóstico disponível apenas para Mercado Livre"
        )
    access_token = await _get_valid_token(listing.account, db)
    seller_id = listing.account.platform_user_id or ""

    logistic_type = (listing.logistic_type or "").strip().lower() or (
        "fulfillment" if listing.is_full else "cross_docking"
    )
    weight_kg = float(listing.weight_kg) if listing.weight_kg else None
    height_cm = float(listing.height_cm) if listing.height_cm else None
    width_cm = float(listing.width_cm) if listing.width_cm else None
    length_cm = float(listing.length_cm) if listing.length_cm else None
    price = float(listing.sale_price) if listing.sale_price else 0.0
    free_shipping = bool(listing.free_shipping)
    seller_pays = free_shipping or logistic_type == "fulfillment"

    debug: dict = {
        "listing_id": listing.id,
        "platform_item_id": listing.platform_item_id,
        "inputs": {
            "price": price,
            "category_id": listing.category_id,
            "listing_type": listing.listing_type,
            "shipping_mode": listing.shipping_mode,
            "logistic_type": logistic_type,
            "free_shipping": free_shipping,
            "weight_kg": weight_kg,
            "height_cm": height_cm,
            "width_cm": width_cm,
            "length_cm": length_cm,
        },
        "seller_pays": seller_pays,
        "skip_reason": None,
        "raw_listing_prices": None,
        "raw_shipping_options": None,
        "parsed_net_cost": None,
    }

    if not seller_pays:
        debug["skip_reason"] = "buyer_pays_me2_non_free"
    elif not (weight_kg and height_cm and width_cm and length_cm):
        debug["skip_reason"] = (
            f"missing_dimensions (weight={weight_kg}, h={height_cm}, "
            f"w={width_cm}, l={length_cm})"
        )

    import httpx as _httpx

    async with _httpx.AsyncClient(timeout=15) as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # listing_prices (comissão)
        if listing.category_id and price > 0:
            try:
                resp = await client.get(
                    f"{ml_service.ML_API_BASE}/sites/MLB/listing_prices",
                    headers=headers,
                    params={
                        "price": price,
                        "category_id": listing.category_id,
                        "listing_type_id": listing.listing_type or "gold_special",
                        "shipping_mode": listing.shipping_mode or "me2",
                        "logistic_type": logistic_type,
                    },
                )
                debug["raw_listing_prices"] = {
                    "status": resp.status_code,
                    "body": resp.json() if resp.status_code == 200 else resp.text[:500],
                }
            except Exception as exc:
                debug["raw_listing_prices"] = {"error": str(exc)}

        # shipping_options/free (frete)
        if seller_pays and weight_kg and height_cm and width_cm and length_cm and seller_id:
            physical_g = int(round(weight_kg * 1000))
            # ML exige formato "HeightxWidthxLength,Weight" com INTEIROS
            dims = (
                f"{int(round(height_cm))}x{int(round(width_cm))}x"
                f"{int(round(length_cm))},{physical_g}"
            )
            try:
                resp = await client.get(
                    f"{ml_service.ML_API_BASE}/users/{seller_id}/shipping_options/free",
                    headers=headers,
                    params={
                        "dimensions": dims,
                        "item_price": price,
                        "listing_type_id": listing.listing_type or "gold_special",
                        "mode": listing.shipping_mode or "me2",
                        "logistic_type": logistic_type,
                        "free_shipping": str(free_shipping or logistic_type == "fulfillment").lower(),
                        "condition": "new",
                        "verbose": "true",
                    },
                )
                debug["raw_shipping_options"] = {
                    "status": resp.status_code,
                    "dimensions_sent": dims,
                    "body": resp.json() if resp.status_code == 200 else resp.text[:500],
                }
                if resp.status_code == 200:
                    parsed = ml_service._parse_shipping_response(resp.json())
                    debug["parsed_net_cost"] = parsed.get("net_cost")
                    if parsed.get("net_cost") == 0 and not debug["skip_reason"]:
                        debug["skip_reason"] = "ml_returned_zero_cost"
                elif not debug["skip_reason"]:
                    debug["skip_reason"] = f"ml_returned_status_{resp.status_code}"
            except Exception as exc:
                debug["raw_shipping_options"] = {"error": str(exc)}
                if not debug["skip_reason"]:
                    debug["skip_reason"] = f"exception: {exc}"

    return debug


@router.post("/{listing_id}/debug-fiscal-sync")
async def debug_fiscal_sync(
    listing_id: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Debug: envia atributos fiscais para o ML e retorna a resposta CRUA.

    Útil pra investigar por que NCM/CEST/GTIN/ORIGIN/CSOSN não aparecem no painel
    "Edite os dados fiscais" do anúncio ML. **Não commita nada no banco** — só
    faz o PUT direto no ML e devolve status + body + cause + atributos persistidos.

    Body (opcional):
    ```json
    {
      "overrides": {
        "ncm": "61091000",
        "cest": null,
        "gtin": "7891234567890",
        "origin": 0,
        "csosn": "102"
      },
      "extra_attributes": [
        {"id": "ICMS_CSOSN", "value_name": "102"},
        {"id": "TIPO_DE_ORIGEM", "value_name": "Nacional"}
      ],
      "only_fiscal": true
    }
    ```

    - `overrides`: substituem os valores resolvidos do produto/fiscal_json/CMIG.
    - `extra_attributes`: enviados literalmente — útil pra testar IDs experimentais.
    - `only_fiscal` (default true): se true, envia só atributos fiscais; se false,
      envia o payload completo do `_build_ml_payload` (mesmo do update real).
    """
    import httpx

    body = body or {}
    overrides = body.get("overrides") or {}
    extra_attrs = body.get("extra_attributes") or []
    only_fiscal = body.get("only_fiscal", True)

    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Disponível apenas para Mercado Livre")
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem platform_item_id no ML")

    product = listing.cmig_product or listing.catalog_product
    if not product:
        raise HTTPException(status_code=400, detail="Anúncio sem produto vinculado")

    access_token = await _get_valid_token(listing.account, db)
    cmig_crt = await _resolve_cmig_crt(listing.account, db)

    # Monta fiscal_json mesclando o do listing com overrides
    fiscal_dict: dict = {}
    if listing.fiscal_json:
        try:
            fiscal_dict = _json.loads(listing.fiscal_json) or {}
        except Exception:
            fiscal_dict = {}
    for k, v in overrides.items():
        if v is not None:
            fiscal_dict[k] = v

    # Override de origin direto no produto (in-memory, sem commit)
    if "origin" in overrides and overrides["origin"] is not None:
        try:
            product.origin = int(overrides["origin"])
        except (TypeError, ValueError):
            pass

    # Form igual ao do update real — _build_ml_payload faz toda a lógica
    form = {
        "title_override": listing.title_override,
        "sale_price": listing.sale_price,
        "listing_type": listing.listing_type or "gold_special",
        "available_quantity": listing.available_quantity or 1,
        "item_condition": listing.item_condition or "new",
        "category_id": listing.category_id,
        "pictures": [],
        "attributes": list(extra_attrs),  # extras já entram como manuais (prioridade)
        "warranty_type": listing.warranty_type,
        "warranty_time": listing.warranty_time,
        "shipping_mode": listing.shipping_mode or "me2",
        "free_shipping": listing.free_shipping or False,
        "sku": listing.sku,
        "model": getattr(product, "model", None),
        "height_cm": float(listing.height_cm) if listing.height_cm else None,
        "width_cm": float(listing.width_cm) if listing.width_cm else None,
        "length_cm": float(listing.length_cm) if listing.length_cm else None,
        "weight_kg": float(listing.weight_kg) if listing.weight_kg else None,
        "fiscal_json": fiscal_dict,
        "cmig_crt": cmig_crt,
    }

    full_payload = _build_ml_payload(product, form, for_update=True)

    # Filtra só atributos fiscais se only_fiscal=true (isola variável)
    FISCAL_ATTR_IDS = {
        "NCM", "FISCAL_CLASSIFICATION", "CEST", "GTIN", "EAN", "ORIGIN",
        "ICMS_CSOSN", "CSOSN", "TIPO_DE_ORIGEM", "ORIGIN_TYPE",
    }
    # Inclui IDs dos extra_attributes (usuário pode estar testando IDs novos)
    FISCAL_ATTR_IDS.update(
        a.get("id", "").upper() for a in extra_attrs if isinstance(a, dict)
    )

    if only_fiscal:
        all_attrs = full_payload.get("attributes") or []
        fiscal_attrs = [a for a in all_attrs if (a.get("id") or "").upper() in FISCAL_ATTR_IDS]
        payload_to_send = {"attributes": fiscal_attrs}
    else:
        # Mesmo payload do update real — remove imutáveis
        payload_to_send = dict(full_payload)
        for f in ("buying_mode", "listing_type_id", "condition", "category_id"):
            payload_to_send.pop(f, None)
        if not getattr(listing.account, "is_official_store", False):
            payload_to_send.pop("title", None)

    # PUT direto no ML
    ML_BASE = "https://api.mercadolibre.com"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        put_resp = await client.put(
            f"{ML_BASE}/items/{listing.platform_item_id}",
            headers=headers,
            json=payload_to_send,
        )
        try:
            put_body = put_resp.json()
        except Exception:
            put_body = {"_raw_text": put_resp.text[:2000]}

        # GET pós-PUT pra confirmar quais atributos persistiram no ML
        get_resp = await client.get(
            f"{ML_BASE}/items/{listing.platform_item_id}",
            headers=headers,
            params={"include_attributes": "all"},
        )
        try:
            get_body = get_resp.json() if get_resp.status_code == 200 else {}
        except Exception:
            get_body = {}

    persisted_attrs = [
        {
            "id": a.get("id"),
            "name": a.get("name"),
            "value_name": a.get("value_name"),
            "value_id": a.get("value_id"),
        }
        for a in (get_body.get("attributes") or [])
        if (a.get("id") or "").upper() in FISCAL_ATTR_IDS
    ]

    causes = None
    if isinstance(put_body, dict):
        causes = put_body.get("cause") or put_body.get("causes")

    return {
        "listing_id": listing.id,
        "platform_item_id": listing.platform_item_id,
        "ml_url": f"{ML_BASE}/items/{listing.platform_item_id}",
        "payload_sent": payload_to_send,
        "ml_status_code": put_resp.status_code,
        "ml_response_body": put_body,
        "ml_error_causes": causes,
        "fiscal_attributes_persisted_after_put": persisted_attrs,
        "note": (
            "only_fiscal=true isola só atributos fiscais. Use overrides para testar valores; "
            "extra_attributes para testar IDs novos (ex: ICMS_CSOSN). Nada foi commitado no DB."
        ),
    }


@router.post("/{listing_id}/sync-fiscal")
async def sync_listing_fiscal_information(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sincroniza fiscal_information de UM anúncio no Faturador do ML.

    Útil para empurrar dados fiscais de anúncios já publicados sem precisar
    abrir/salvar o wizard. Usa os campos do produto vinculado (PG ou CMIG)
    + fiscal_json do listing + fallback do CRT da CMIG para o CSOSN.

    Retorna `{ok, status_code, method, body}` da operação.
    """
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Disponível apenas para Mercado Livre")

    product = listing.cmig_product or listing.catalog_product
    if not product:
        raise HTTPException(status_code=400, detail="Anúncio sem produto vinculado")

    sku = (
        listing.sku
        or getattr(product, "sku_cmig", None)
        or getattr(product, "sku", None)
    )
    if not sku:
        raise HTTPException(status_code=400, detail="Anúncio/produto sem SKU")

    access_token = await _get_valid_token(listing.account, db)
    cmig_crt = await _resolve_cmig_crt(listing.account, db)

    payload = _build_fiscal_payload_from_product(
        product,
        str(sku),
        cmig_crt,
        fiscal_overrides=_parse_fiscal_json(listing.fiscal_json),
    )
    if not payload:
        raise HTTPException(
            status_code=400,
            detail="Sem NCM configurado no produto/anúncio — Faturador rejeita sem NCM",
        )

    result = await ml_service.register_or_update_fiscal_information(
        access_token, str(sku), payload
    )
    return {
        "listing_id": listing.id,
        "sku": sku,
        "payload_sent": payload,
        **result,
    }


@router.post("/{listing_id}/debug-fiscal-information")
async def debug_fiscal_information(
    listing_id: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Debug: cadastra/atualiza dados fiscais via endpoint dedicado do Faturador ML.

    Diferente de `debug-fiscal-sync` (que envia atributos via `PUT /items` mas
    NÃO consegue gravar CSOSN), este endpoint usa o caminho correto descoberto
    em `https://developers.mercadolivre.com.br/pt_br/envio-dos-dados-fiscais`:

    - **POST** `/items/fiscal_information` → cadastra fiscal data para o SKU
    - **PUT** `/items/fiscal_information/{SKU}` → atualiza
    - **GET** `/items/fiscal_information/{SKU}` → consulta

    O endpoint tenta POST primeiro; se retornar 409/duplicate, faz PUT.

    **Não commita nada no DB.** Retorna a resposta crua do ML.

    Body (opcional):
    ```json
    {
      "overrides": {
        "ncm": "61091000",
        "csosn": "102",
        "cest": "2806400",
        "ean": "7898510754383",
        "origin_type": "manufacturer",
        "origin_detail": 0,
        "cost": 25.0,
        "net_weight": 5.55,
        "gross_weight": 5.55,
        "measurement_unit": "UN",
        "type": "single"
      },
      "method": "auto"
    }
    ```

    `method`: "auto" (default — POST primeiro, PUT se 409), "post", "put".

    Mapeamento padrão (quando overrides não passa):
    - sku → product.sku/sku_cmig
    - title → product.title
    - type → "bundle" se product.is_composite senão "single"
    - measurement_unit → "UN"
    - cost → product.cost_price
    - tax_information.ncm → product.ncm
    - tax_information.origin_detail → product.origin (0-8)
    - tax_information.origin_type → derivado de origin: {0,3,4,5,8}→manufacturer,
      {1,6}→imported, {2,7}→reseller
    - tax_information.cest → product.cest
    - tax_information.ean → product.ean
    - tax_information.csosn → product.csosn ou "102" (Simples) ou null (Normal)
    - tax_information.net/gross_weight → product.weight_kg
    """
    import httpx

    body = body or {}
    overrides = body.get("overrides") or {}
    method = (body.get("method") or "auto").lower()

    listing = await _get_listing_or_404(listing_id, current_user, db)
    if listing.account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Disponível apenas para Mercado Livre")

    product = listing.cmig_product or listing.catalog_product
    if not product:
        raise HTTPException(status_code=400, detail="Anúncio sem produto vinculado")

    access_token = await _get_valid_token(listing.account, db)
    cmig_crt = await _resolve_cmig_crt(listing.account, db)

    # Resolve SKU — o Faturador indexa por SKU, não por item_id
    sku = (
        overrides.get("sku")
        or listing.sku
        or getattr(product, "sku_cmig", None)
        or getattr(product, "sku", None)
    )
    if not sku:
        raise HTTPException(
            status_code=400,
            detail="SKU obrigatório para Faturador — anúncio/produto sem SKU",
        )

    # Mapeamento origin (0-8) → origin_type (manufacturer/imported/reseller)
    def _origin_to_type(o: int | None) -> str:
        if o is None:
            return "manufacturer"
        o = int(o)
        if o in (1, 6):
            return "imported"
        if o in (2, 7):
            return "reseller"
        return "manufacturer"  # 0, 3, 4, 5, 8

    origin_detail = overrides.get("origin_detail")
    if origin_detail is None:
        origin_detail = getattr(product, "origin", None) or 0

    origin_type = overrides.get("origin_type") or _origin_to_type(origin_detail)

    # CSOSN — só Simples Nacional
    csosn = overrides.get("csosn") if "csosn" in overrides else getattr(product, "csosn", None)
    if not csosn and cmig_crt in (1, 2):
        csosn = "102"  # default Simples Nacional sem permissão de crédito

    # Monta tax_information apenas com campos preenchidos
    tax_info: dict = {}

    def _add_if_present(key: str, value, normalize=None):
        if value is None or value == "":
            return
        if normalize:
            value = normalize(value)
            if not value:
                return
        tax_info[key] = value

    ncm = overrides.get("ncm") if "ncm" in overrides else getattr(product, "ncm", None)
    _add_if_present("ncm", ncm, lambda v: str(v).replace(".", "").replace("-", "")[:8] or None)

    _add_if_present("origin_type", origin_type)
    if origin_detail is not None:
        tax_info["origin_detail"] = str(origin_detail)

    cest = overrides.get("cest") if "cest" in overrides else getattr(product, "cest", None)
    _add_if_present("cest", cest, lambda v: str(v).replace(".", "").replace("-", "")[:7] or None)

    if csosn:
        tax_info["csosn"] = str(csosn)

    ean = overrides.get("ean") if "ean" in overrides else getattr(product, "ean", None)
    if ean and _is_valid_ean13(str(ean).strip()):
        tax_info["ean"] = str(ean).strip()

    weight_kg = overrides.get("net_weight")
    if weight_kg is None:
        weight_kg = float(product.weight_kg) if getattr(product, "weight_kg", None) else None
    if weight_kg is not None:
        tax_info["net_weight"] = float(weight_kg)
        tax_info["gross_weight"] = float(overrides.get("gross_weight") or weight_kg)

    # tax_rule_id é para Regime Normal apenas (CRT=3) — se for o caso, espera
    # vir explícito em overrides; sem isso o ML aceitará só Simples
    if "tax_rule_id" in overrides:
        tax_info["tax_rule_id"] = overrides["tax_rule_id"]

    # Campos opcionais avançados
    for opt_key in ("fci", "ex_tipi", "med_anvisa_code", "med_exemption_reason"):
        if opt_key in overrides:
            tax_info[opt_key] = overrides[opt_key]

    cost = overrides.get("cost")
    if cost is None:
        cost = float(product.cost_price) if getattr(product, "cost_price", None) else 0.0

    product_type = overrides.get("type") or (
        "bundle" if getattr(product, "is_composite", False) else "single"
    )

    payload = {
        "sku": str(sku),
        "title": (overrides.get("title") or product.title or "")[:255],
        "type": product_type,
        "measurement_unit": overrides.get("measurement_unit") or "UN",
        "cost": float(cost),
        "tax_information": tax_info,
    }

    ML_BASE = "https://api.mercadolibre.com"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "content-type": "application/json",
    }

    attempts: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # POST primeiro (cria) — se 409/duplicate, PUT
        if method in ("auto", "post"):
            post_resp = await client.post(
                f"{ML_BASE}/items/fiscal_information",
                headers=headers,
                json=payload,
            )
            try:
                post_body = post_resp.json()
            except Exception:
                post_body = {"_raw_text": post_resp.text[:2000]}
            attempts.append({
                "method": "POST",
                "url": f"{ML_BASE}/items/fiscal_information",
                "status": post_resp.status_code,
                "body": post_body,
            })

            # Se POST sucesso ou método explícito post, retorna
            if method == "post" or post_resp.status_code in (200, 201):
                final_status = post_resp.status_code
                final_body = post_body
            else:
                # Fallback PUT
                put_resp = await client.put(
                    f"{ML_BASE}/items/fiscal_information/{sku}",
                    headers=headers,
                    json=payload,
                )
                try:
                    put_body = put_resp.json()
                except Exception:
                    put_body = {"_raw_text": put_resp.text[:2000]}
                attempts.append({
                    "method": "PUT",
                    "url": f"{ML_BASE}/items/fiscal_information/{sku}",
                    "status": put_resp.status_code,
                    "body": put_body,
                })
                final_status = put_resp.status_code
                final_body = put_body
        else:  # method == "put"
            put_resp = await client.put(
                f"{ML_BASE}/items/fiscal_information/{sku}",
                headers=headers,
                json=payload,
            )
            try:
                put_body = put_resp.json()
            except Exception:
                put_body = {"_raw_text": put_resp.text[:2000]}
            attempts.append({
                "method": "PUT",
                "url": f"{ML_BASE}/items/fiscal_information/{sku}",
                "status": put_resp.status_code,
                "body": put_body,
            })
            final_status = put_resp.status_code
            final_body = put_body

        # GET pós-operação pra confirmar persistência
        get_resp = await client.get(
            f"{ML_BASE}/items/fiscal_information/{sku}",
            headers=headers,
        )
        try:
            get_body = get_resp.json() if get_resp.status_code == 200 else {}
        except Exception:
            get_body = {}

    causes = None
    if isinstance(final_body, dict):
        causes = final_body.get("fields") or final_body.get("cause") or final_body.get("causes")

    return {
        "listing_id": listing.id,
        "platform_item_id": listing.platform_item_id,
        "sku": sku,
        "cmig_crt": cmig_crt,
        "payload_sent": payload,
        "attempts": attempts,
        "final_status_code": final_status,
        "final_response_body": final_body,
        "ml_error_causes": causes,
        "fiscal_data_persisted": get_body if get_resp.status_code == 200 else None,
        "get_status": get_resp.status_code,
        "note": (
            "Endpoint dedicado do Faturador. Indexa por SKU, não por item_id. "
            "Método 'auto' tenta POST e cai pra PUT se já existir. Nada foi commitado no DB."
        ),
    }


@router.get("/{listing_id}/prices-debug")
async def get_anuncio_prices_debug(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnóstico: retorna raw de /items/{id}/prices e tags do item — para identificar campos de automação de preço."""
    listing = await _get_listing_or_404(listing_id, current_user, db)
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")
    access_token = await _get_valid_token(listing.account, db)
    result = await ml_service.get_item_auto_pricing(access_token, listing.platform_item_id)
    return {
        "platform_item_id": listing.platform_item_id,
        "is_auto_detected": result["is_auto"],
        "auto_type": result["auto_type"],
        "prices_raw": result["prices_raw"],
        "tags_raw": result["tags_raw"],
    }


@router.get("/{listing_id}/promotion")
async def get_anuncio_promotion(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna dados de promoção ativa do item no Mercado Livre."""
    listing = await _get_listing_or_404(listing_id, current_user, db)

    if listing.account.platform != "mercadolivre":
        raise HTTPException(
            status_code=400, detail="Promoções disponíveis apenas para Mercado Livre"
        )
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")

    access_token = await _get_valid_token(listing.account, db)
    return await ml_service.get_item_promotion(
        access_token=access_token,
        item_id=listing.platform_item_id,
    )

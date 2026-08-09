"""
Gerenciamento de anúncios (ProductListings) por CONTA de marketplace.
Um AC pode ter anúncios de uma mesma CONTA publicados em marketplace.
"""

import json
import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user
from models.integration import MarketplaceAccount
from models.product import (
    CatalogProduct,
    DropshipperProduct,
    ProductListing,
    ProductMarketplaceCategory,
)
from models.user import AccountAdministrator, User
from services import ml_service, shopee_service
from services.content_declaration import (
    _host_is_safe,  # guard SSRF reusável (resolve DNS, bloqueia IP privado)
)
from services.shopee_auth import get_valid_shopee_token

logger = logging.getLogger(__name__)
router = APIRouter()

_IMG_MAX_BYTES = 3_000_000  # teto anti-imagem-gigante no download (igual content_declaration)


async def _fetch_image_bytes(url: str) -> bytes | None:
    """Baixa uma imagem do produto (URL interna/externa) com guarda SSRF, para re-upload na Shopee
    (que NÃO aceita URL externa — exige o image_id do media_space). Stream com teto de tamanho."""
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return None
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname
        if not host or not await _host_is_safe(host):
            return None
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    if len(buf) > _IMG_MAX_BYTES:
                        return None
                return buf
    except Exception as exc:  # noqa: BLE001 — imagem indisponível não deve derrubar a publicação
        logger.warning("[shopee] falha ao baixar imagem %s: %s", url, exc)
        return None


def _serialize_listing(listing: ProductListing, account: MarketplaceAccount) -> dict:
    return {
        "id": listing.id,
        "product_id": listing.product_id,
        "account_id": listing.account_id,
        "platform": account.platform,
        "account_name": account.platform_username or account.description,
        "platform_item_id": listing.platform_item_id,
        "sale_price": float(listing.sale_price),
        "title_override": listing.title_override,
        "category_id": listing.category_id,
        "listing_type": listing.listing_type,
        "status": listing.status,
        "error_message": listing.error_message,
        "published_at": listing.published_at.isoformat() if listing.published_at else None,
        "last_sync_at": listing.last_sync_at.isoformat() if listing.last_sync_at else None,
    }


async def _get_product_for_user(
    product_id: int, user_id: int, db: AsyncSession
) -> DropshipperProduct:
    result = await db.execute(
        select(DropshipperProduct).where(
            DropshipperProduct.id == product_id,
            DropshipperProduct.dropshipper_id == user_id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


async def _assert_account_access(
    account_id: int, user_id: int, db: AsyncSession
) -> MarketplaceAccount:
    """Verifica que o usuário é co-administrador da CONTA."""
    result = await db.execute(
        select(MarketplaceAccount)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .where(
            MarketplaceAccount.id == account_id,
            AccountAdministrator.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=404, detail="Conta de marketplace não encontrada ou sem permissão"
        )
    return account


async def _get_listing_for_user(
    listing_id: int, product_id: int, user_id: int, db: AsyncSession
) -> tuple:
    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .join(AccountAdministrator, MarketplaceAccount.id == AccountAdministrator.account_id)
        .join(DropshipperProduct, ProductListing.product_id == DropshipperProduct.id)
        .where(
            ProductListing.id == listing_id,
            ProductListing.product_id == product_id,
            DropshipperProduct.dropshipper_id == user_id,
            AccountAdministrator.user_id == user_id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
    return row


# ─── Listar anúncios de um produto ───────────────────────────────────────────


@router.get("")
async def list_listings(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_product_for_user(product_id, current_user.id, db)

    result = await db.execute(
        select(ProductListing, MarketplaceAccount)
        .join(MarketplaceAccount, ProductListing.account_id == MarketplaceAccount.id)
        .where(ProductListing.product_id == product_id)
        .order_by(ProductListing.created_at)
    )
    return [_serialize_listing(listing, account) for listing, account in result.all()]


# ─── Criar anúncio (draft) ────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_listing(
    product_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cria um anúncio em status draft.
    Body: account_id, sale_price, title_override?, category_id?, listing_type?
    """
    await _get_product_for_user(product_id, current_user.id, db)

    account_id = body.get("account_id")
    sale_price = body.get("sale_price")
    if not account_id or sale_price is None:
        raise HTTPException(status_code=400, detail="account_id e sale_price são obrigatórios")

    account = await _assert_account_access(account_id, current_user.id, db)
    if not account.is_active:
        raise HTTPException(status_code=400, detail="Conta inativa")

    dup = await db.execute(
        select(ProductListing).where(
            ProductListing.product_id == product_id,
            ProductListing.account_id == account_id,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Já existe um anúncio para este produto nesta conta"
        )

    listing = ProductListing(
        product_id=product_id,
        account_id=account_id,
        sale_price=sale_price,
        title_override=body.get("title_override"),
        category_id=body.get("category_id"),
        listing_type=body.get("listing_type"),
        status="draft",
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return _serialize_listing(listing, account)


# ─── Atualizar anúncio ────────────────────────────────────────────────────────


@router.put("/{listing_id}")
async def update_listing(
    product_id: int,
    listing_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)

    if "sale_price" in body:
        listing.sale_price = body["sale_price"]
    if "title_override" in body:
        listing.title_override = body["title_override"]
    if "category_id" in body:
        listing.category_id = body["category_id"]
    if "listing_type" in body:
        listing.listing_type = body["listing_type"]

    await db.commit()
    return _serialize_listing(listing, account)


# ─── Remover anúncio ──────────────────────────────────────────────────────────


@router.delete("/{listing_id}", status_code=204)
async def delete_listing(
    product_id: int,
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing, _ = await _get_listing_for_user(listing_id, product_id, current_user.id, db)
    db.delete(listing)
    await db.commit()


# ─── Publicar anúncio no marketplace ─────────────────────────────────────────


@router.post("/{listing_id}/publish")
async def publish_listing(
    product_id: int,
    listing_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publica ou vincula o anúncio no marketplace.
    Body: mode ("create"|"link"), platform_item_id? (obrigatório se mode=link)
    """
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)
    product_result = await db.execute(
        select(DropshipperProduct)
        .where(DropshipperProduct.id == product_id)
        .options(selectinload(DropshipperProduct.images))
    )
    product = product_result.scalar_one()
    mode = body.get("mode", "link")

    try:
        if mode == "link":
            platform_item_id = body.get("platform_item_id") or listing.platform_item_id
            if not platform_item_id:
                raise HTTPException(
                    status_code=400, detail="platform_item_id é obrigatório para mode=link"
                )

            if account.platform == "mercadolivre":
                item = await ml_service.get_item(account.access_token, platform_item_id)
                listing.title_override = listing.title_override or item.get("title")
                listing.category_id = listing.category_id or item.get("category_id")
            elif account.platform == "shopee":
                item = await shopee_service.get_item_base_info(
                    account.access_token, account.shop_id, int(platform_item_id)
                )
                listing.title_override = listing.title_override or item.get("item_name")

            listing.platform_item_id = str(platform_item_id)
            listing.status = "published"
            listing.published_at = datetime.now(UTC)
            listing.error_message = None

        elif mode == "create":
            if account.platform == "mercadolivre":
                item_data = _build_ml_item(product, listing)
                result = await ml_service.create_item(account.access_token, item_data)
                listing.platform_item_id = result["id"]
            elif account.platform == "shopee":
                # Falhar alto: reexecuta os bloqueios ANTES do add_item (o preview pode ter sido
                # pulado). Aborta com a lista clara apontando o cadastro, em vez do erro cru da Shopee.
                bloqueios = await _shopee_publish_bloqueios(product, listing, account, db)
                if bloqueios:
                    raise HTTPException(status_code=400, detail={"bloqueios": bloqueios})
                item_data = await _build_shopee_item(product, listing, account, db)
                token = await get_valid_shopee_token(account, db)
                item_id = await shopee_service.add_item(token, account.shop_id, item_data)
                listing.platform_item_id = str(item_id)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Criação automática não suportada para {account.platform}",
                )

            listing.status = "published"
            listing.published_at = datetime.now(UTC)
            listing.error_message = None
        else:
            raise HTTPException(status_code=400, detail="mode deve ser 'create' ou 'link'")

    except HTTPException:
        raise
    except Exception as exc:
        listing.status = "error"
        listing.error_message = str(exc)[:2000]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Erro ao publicar anúncio: {exc}")

    await db.commit()
    return _serialize_listing(listing, account)


# ─── Pausar anúncio ───────────────────────────────────────────────────────────


@router.post("/{listing_id}/pause")
async def pause_listing(
    product_id: int,
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)

    if listing.status != "published":
        raise HTTPException(
            status_code=400, detail="Somente anúncios publicados podem ser pausados"
        )
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")

    try:
        if account.platform == "mercadolivre":
            await ml_service.pause_item(account.access_token, listing.platform_item_id)
        elif account.platform == "shopee":
            # Pausar na Shopee = unlist (oculta); NÃO zerar estoque (ADR-0014). Falhar alto.
            token = await get_valid_shopee_token(account, db)
            await shopee_service.unlist_item(token, account.shop_id, int(listing.platform_item_id), unlist=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao pausar anúncio: {exc}")

    listing.status = "paused"
    await db.commit()
    return _serialize_listing(listing, account)


@router.post("/{listing_id}/reactivate")
async def reactivate_listing(
    product_id: int,
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reativa (republica) um anúncio pausado. ML: unpause; Shopee: unlist(False)."""
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)
    if listing.status != "paused":
        raise HTTPException(status_code=400, detail="Somente anúncios pausados podem ser reativados")
    if not listing.platform_item_id:
        raise HTTPException(status_code=400, detail="Anúncio sem ID no marketplace")

    try:
        if account.platform == "mercadolivre":
            await ml_service.activate_item(account.access_token, listing.platform_item_id)
        elif account.platform == "shopee":
            token = await get_valid_shopee_token(account, db)
            await shopee_service.unlist_item(token, account.shop_id, int(listing.platform_item_id), unlist=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao reativar anúncio: {exc}")

    listing.status = "published"
    await db.commit()
    return _serialize_listing(listing, account)


# ─── Helpers de payload ───────────────────────────────────────────────────────


def _build_ml_item(product: DropshipperProduct, listing: ProductListing) -> dict:
    if not listing.category_id:
        raise HTTPException(
            status_code=400, detail="category_id é obrigatório para criar anúncio no ML"
        )
    if not listing.listing_type:
        raise HTTPException(
            status_code=400, detail="listing_type é obrigatório para criar anúncio no ML"
        )
    return {
        "title": listing.title_override or product.title,
        "category_id": listing.category_id,
        "price": float(listing.sale_price),
        "currency_id": "BRL",
        "available_quantity": 1,
        "buying_mode": "buy_it_now",
        "listing_type_id": listing.listing_type,
        "condition": "new",
    }


async def _shopee_pmc(product: DropshipperProduct, listing: ProductListing, db: AsyncSession):
    """Categoria+atributos da Shopee CADASTRADOS na aba de categorias do Produto PG. Só usa se a
    categoria cadastrada bate com a do anúncio (evita mandar atributos de outra categoria)."""
    cpid = getattr(product, "catalog_product_id", None)
    if not cpid:
        return None
    pmc = (await db.execute(select(ProductMarketplaceCategory).where(and_(
        ProductMarketplaceCategory.catalog_product_id == cpid,
        ProductMarketplaceCategory.marketplace == "shopee",
    )))).scalars().first()
    if not pmc:
        return None
    if listing.category_id and str(pmc.category_id) != str(listing.category_id):
        return None  # categoria cadastrada ≠ categoria do anúncio → revalidar/recadastrar
    return pmc


def _build_shopee_attributes(attrs_raw: str | None) -> tuple[list, int | None, set]:
    """Do `attributes_json` (cadastro) → `attribute_list` do add_item + brand_id + ids salvos.
    Formato confirmado ao vivo: value_id da lista (original_value_name/value_unit vazios);
    value_id=0 + original_value_name p/ quantitativo/texto; value_unit só no quantitativo;
    multi = vários itens no mesmo attribute_value_list."""
    try:
        entries = json.loads(attrs_raw or "[]")
    except (ValueError, TypeError):
        entries = []
    attribute_list: list = []
    brand_id: int | None = None
    saved_ids: set = set()
    for e in entries:
        if e.get("id") == "__SHOPEE_BRAND__":
            brand_id = e.get("value_id")
            continue
        try:
            aid = int(e.get("id"))
        except (TypeError, ValueError):
            continue  # id não-numérico não é atributo Shopee
        kind = e.get("kind")
        if kind == "multi":
            vals = [{"value_id": int(v), "original_value_name": "", "value_unit": ""}
                    for v in (e.get("value_ids") or []) if v is not None]
        elif kind == "quantitative":
            vals = [{"value_id": 0, "original_value_name": str(e.get("value_name") or ""),
                     "value_unit": e.get("value_unit") or ""}]
        elif kind == "single":
            try:
                vals = [{"value_id": int(e.get("value_id")), "original_value_name": "", "value_unit": ""}]
            except (TypeError, ValueError):
                vals = []
        else:  # text (ou legado)
            vals = [{"value_id": 0, "original_value_name": str(e.get("value_name") or ""), "value_unit": ""}]
        if vals:
            saved_ids.add(aid)
            attribute_list.append({"attribute_id": aid, "attribute_value_list": vals})
    return attribute_list, brand_id, saved_ids


async def _shopee_publish_bloqueios(
    product: DropshipperProduct, listing: ProductListing,
    account: MarketplaceAccount, db: AsyncSession,
) -> list[str]:
    """Valida (READ-ONLY, sem publicar) se o produto tem tudo que o add_item da Shopee exige.
    Retorna a lista de bloqueios — a UI mostra ANTES de publicar (falhar alto, padrão preview_ordem).
    """
    b: list[str] = []
    if not listing.category_id:
        b.append("Falta a categoria (folha) da Shopee — use 'Sugerir categoria' e escolha uma folha.")
    if not (listing.sale_price or getattr(product, "sale_price_shopee", None)):
        b.append("Falta o preço de venda para a Shopee.")

    cat = None
    if getattr(product, "catalog_product_id", None):
        cat = (await db.execute(
            select(CatalogProduct).where(CatalogProduct.id == product.catalog_product_id)
        )).scalar_one_or_none()
    for nome, attr in (("peso", "weight_kg"), ("comprimento", "length_cm"),
                       ("largura", "width_cm"), ("altura", "height_cm")):
        if not (getattr(product, attr, None) or getattr(cat, attr, None)):
            b.append(f"Falta {nome} do produto (a Shopee exige para o add_item).")
    if not (product.images or []):
        b.append("Produto sem imagens (a Shopee exige ao menos uma).")

    try:
        token = await get_valid_shopee_token(account, db)
        channels = await shopee_service.get_channel_list(token, account.shop_id)
        if not any(c.get("enabled") for c in channels):
            b.append("Nenhum canal de logística habilitado na loja Shopee.")
        if listing.category_id:
            # Bloqueio DINÂMICO: só bloqueia se o obrigatório NÃO estiver cadastrado na aba de
            # categorias do Produto PG (Fase 2). Revalida na loja-ALVO do anúncio (não a de navegação).
            pmc = await _shopee_pmc(product, listing, db)
            _, saved_brand, saved_ids = _build_shopee_attributes(
                pmc.attributes_json if pmc else None)
            br = await shopee_service.get_brand_list(token, account.shop_id, int(listing.category_id))
            if br.get("is_mandatory") and (saved_brand is None or saved_brand == 0):
                b.append("Esta categoria EXIGE marca — cadastre a marca da Shopee na aba de "
                         "categorias do produto (o sistema publicaria como 'Sem marca').")
            attrs = await shopee_service.get_attribute_tree(token, account.shop_id, int(listing.category_id))
            faltam = [a.get("name") for a in attrs
                      if a.get("mandatory") and int(a.get("attribute_id", 0)) not in saved_ids]
            if faltam:
                b.append("Categoria exige atributo(s) obrigatório(s) não cadastrado(s): "
                         f"{', '.join(faltam[:5])}. Preencha na aba de categorias do produto.")
    except Exception as exc:  # noqa: BLE001 — falha ao consultar a Shopee vira aviso (não quebra o preview)
        # Inclui HTTPException de token vencido / loja desconectada / erro de API Shopee: viram
        # bloqueio textual amigável, não 5xx. Detalhe cru fica no log (não vaza para o front).
        logger.warning("[shopee] falha ao validar categoria/canais (conta %s): %s",
                       account.id, exc, exc_info=True)
        b.append("Não foi possível validar categoria/marca/canais na Shopee agora "
                 "(conta pode estar desconectada — reconecte). Tente novamente.")
    return b


@router.get("/{listing_id}/publish-preview")
async def publish_preview(
    product_id: int,
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Prévia da publicação Shopee: o que falta (bloqueios[]) ANTES de chamar o add_item."""
    listing, account = await _get_listing_for_user(listing_id, product_id, current_user.id, db)
    if account.platform != "shopee":
        return {"bloqueios": [], "plataforma": account.platform}
    product = (await db.execute(
        select(DropshipperProduct)
        .where(DropshipperProduct.id == product_id)
        .options(selectinload(DropshipperProduct.images))
    )).scalar_one()
    bloqueios = await _shopee_publish_bloqueios(product, listing, account, db)
    return {"bloqueios": bloqueios, "pode_publicar": not bloqueios, "plataforma": "shopee"}


async def _build_shopee_item(
    product: DropshipperProduct, listing: ProductListing,
    account: MarketplaceAccount, db: AsyncSession,
) -> dict:
    """Monta o payload do add_item da Shopee (contrato BR vivo). Diferente do ML (que recebe URL),
    a Shopee exige image_id (media_space) + peso/dimensão/logistic_info/seller_stock. Falha alto
    com bloqueios claros quando falta dado obrigatório (categoria folha, preço, peso, imagem, canal).
    """
    if not listing.category_id:
        raise HTTPException(status_code=400, detail="category_id (folha) é obrigatório para publicar na Shopee")
    price = listing.sale_price or getattr(product, "sale_price_shopee", None)
    if not price:
        raise HTTPException(status_code=400, detail="Preço de venda ausente para a Shopee")

    token = await get_valid_shopee_token(account, db)

    # Peso/dimensões: do produto ou do CatalogProduct vinculado.
    cat = None
    if getattr(product, "catalog_product_id", None):
        cat = (await db.execute(
            select(CatalogProduct).where(CatalogProduct.id == product.catalog_product_id)
        )).scalar_one_or_none()

    def _num(*vals, default=None):
        for v in vals:
            if v is not None:
                return float(v)
        return default

    weight = _num(getattr(product, "weight_kg", None), getattr(cat, "weight_kg", None), default=None)
    length = _num(getattr(product, "length_cm", None), getattr(cat, "length_cm", None), default=None)
    width = _num(getattr(product, "width_cm", None), getattr(cat, "width_cm", None), default=None)
    height = _num(getattr(product, "height_cm", None), getattr(cat, "height_cm", None), default=None)
    faltando = [n for n, v in (("peso", weight), ("comprimento", length),
                               ("largura", width), ("altura", height)) if not v]
    if faltando:
        raise HTTPException(status_code=400,
                            detail=f"Shopee exige {', '.join(faltando)} do produto para publicar (add_item).")

    # Canais habilitados (logistic_info exige ≥1 enabled).
    channels = await shopee_service.get_channel_list(token, account.shop_id)
    logistic_info = [{"logistic_id": c["logistics_channel_id"], "enabled": True}
                     for c in channels if c.get("enabled")]
    if not logistic_info:
        raise HTTPException(status_code=400, detail="Nenhum canal de logística habilitado na loja Shopee.")

    # Imagens: baixa (SSRF-safe) e sobe no media_space → image_id (máx 9; capa primeiro).
    imgs = sorted(product.images or [], key=lambda i: (not i.is_primary, i.sort_order or 0))
    image_ids: list = []
    for img in imgs[:9]:
        data = await _fetch_image_bytes(img.url)
        if not data:
            continue
        iid = await shopee_service.upload_image(token, account.shop_id, data)
        if iid:
            image_ids.append(iid)
    if not image_ids:
        raise HTTPException(status_code=400, detail="Nenhuma imagem válida do produto para a Shopee (add_item exige imagem).")

    # Atributos + marca cadastrados na aba de categorias do Produto PG (Fase 2).
    pmc = await _shopee_pmc(product, listing, db)
    attribute_list, brand_id, _ = _build_shopee_attributes(pmc.attributes_json if pmc else None)
    try:
        brand_id_int = int(brand_id) if brand_id is not None else 0
    except (TypeError, ValueError):
        brand_id_int = 0  # legado/manual não-numérico → "Sem marca" (não estoura o add_item)

    name = (product.title_shopee or listing.title_override or product.title or "")[:100]
    item = {
        "item_name": name,
        "description": (product.description or name)[:3000],
        "category_id": int(listing.category_id),
        "original_price": float(price),
        "seller_stock": [{"stock": 1}],
        "weight": weight,
        "dimension": {"package_length": int(length), "package_width": int(width),
                      "package_height": int(height)},
        "logistic_info": logistic_info,
        "image": {"image_id_list": image_ids},
        # Marca cadastrada, ou 0 = "Sem marca" (NoBrand) quando não exigida/não escolhida.
        "brand": {"brand_id": brand_id_int},
        "condition": "NEW",
        "item_status": "NORMAL",
    }
    if attribute_list:
        item["attribute_list"] = attribute_list
    return item

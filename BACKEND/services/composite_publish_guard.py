"""Trava de publicação simultânea: kit ⇄ componente (ADR-0023).

Kit e componente são lastreados nas MESMAS unidades físicas (componente com 50 → um kit
de 2× anuncia 25 **e** o componente anuncia 50). Anunciar os dois ao mesmo tempo vende
unidades que não existem. Decisão do dono: **travar publicação simultânea**.

Duas frentes, com a MESMA regra de desempate (senão o gate e o job discordam):

1. **Gate de publicação** — recusa antes de criar o item no marketplace.
2. **`available_to_push`** — o lado perdedor passa a reportar 0 disponível, e a pausa
   automática da ADR-0014 o pausa/não-reativa sozinha. É o que fecha o buraco da
   reativação automática (o anúncio `auto_paused` que volta quando o estoque retorna)
   sem criar um segundo motor de decisão dentro do `sync_stock` — e a Shopee herda,
   porque o número é calculado antes de ramificar por plataforma (ADR-0020).

**Desempate:** quem publicou primeiro (`published_at`, `id` como critério estável)
mantém; o outro perde. Determinístico — sem isso os dois se pausam em alternância a
cada ciclo de 30 min.

**Limites conhecidos** (declarados, não mascarados):
- Anúncio publicado com variações guarda o vínculo dentro de `variations_json`, não nas
  FKs. A varredura cobre as FKs e o espelho PG⇄CMIG; variação fica de fora.
- O sistema espelha o marketplace: reativar pelo Seller Center não passa por aqui. A
  trava é da NOSSA borda, nunca absoluta.
- Profundidade 1: kit dentro de kit não é suportado pelo cálculo de estoque (o kit vale
  0 por definição — ADR-0023), então não há recursão.
"""

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.cmig import CMIGProduct, CMIGProductComponent
from models.product import (
    CatalogProduct,
    CatalogProductComponent,
    DropshipperProduct,
    ProductListing,
)

logger = logging.getLogger(__name__)

# Anúncio que ocupa as unidades: publicado OU pausado-pelo-sistema (`auto_paused` volta
# sozinho quando o estoque retorna — tratá-lo como inativo garantiria o conflito na volta).
def _active_clause():
    return or_(ProductListing.status == "published", ProductListing.auto_paused == True)  # noqa: E712


async def _sibling_keys(
    db: AsyncSession, *, catalog_product_id: int | None, cmig_product_id: int | None
) -> tuple[set[int], set[int]]:
    """Produtos que disputam as MESMAS unidades do produto informado.

    Se o produto é kit → seus componentes. Se é simples → os kits que o contêm (e os
    demais componentes desses kits NÃO entram: só kit ⇄ componente disputa).
    Devolve (catalog_ids, cmig_ids). O espelho PG⇄CMIG (ADR-0010) é canonizado."""
    cat_ids: set[int] = set()
    cmig_ids: set[int] = set()

    # Espelho: um CMIGProduct com pg_product_id é o MESMO estoque do PG.
    if cmig_product_id and not catalog_product_id:
        pg_id = (
            await db.execute(
                select(CMIGProduct.pg_product_id).where(CMIGProduct.id == cmig_product_id)
            )
        ).scalar_one_or_none()
        if pg_id:
            catalog_product_id = pg_id

    if catalog_product_id:
        # É kit? → componentes.
        cat_ids |= set(
            (
                await db.execute(
                    select(CatalogProductComponent.component_id).where(
                        CatalogProductComponent.composite_id == catalog_product_id
                    )
                )
            ).scalars().all()
        )
        # É componente? → kits que o contêm.
        cat_ids |= set(
            (
                await db.execute(
                    select(CatalogProductComponent.composite_id).where(
                        CatalogProductComponent.component_id == catalog_product_id
                    )
                )
            ).scalars().all()
        )
        # Kits CMIG que usam este PG como componente.
        cmig_ids |= set(
            (
                await db.execute(
                    select(CMIGProductComponent.composite_id).where(
                        CMIGProductComponent.catalog_product_id == catalog_product_id
                    )
                )
            ).scalars().all()
        )

    if cmig_product_id:
        cmig_ids |= set(
            (
                await db.execute(
                    select(CMIGProductComponent.cmig_product_id).where(
                        CMIGProductComponent.composite_id == cmig_product_id,
                        CMIGProductComponent.cmig_product_id.isnot(None),
                    )
                )
            ).scalars().all()
        )
        cat_ids |= set(
            (
                await db.execute(
                    select(CMIGProductComponent.catalog_product_id).where(
                        CMIGProductComponent.composite_id == cmig_product_id,
                        CMIGProductComponent.catalog_product_id.isnot(None),
                    )
                )
            ).scalars().all()
        )
        cmig_ids |= set(
            (
                await db.execute(
                    select(CMIGProductComponent.composite_id).where(
                        CMIGProductComponent.cmig_product_id == cmig_product_id
                    )
                )
            ).scalars().all()
        )

    # Canoniza: PG vinculado a esses CMIGs conta como o mesmo estoque, e vice-versa.
    if cmig_ids:
        cat_ids |= set(
            (
                await db.execute(
                    select(CMIGProduct.pg_product_id).where(
                        CMIGProduct.id.in_(cmig_ids), CMIGProduct.pg_product_id.isnot(None)
                    )
                )
            ).scalars().all()
        )
    if cat_ids:
        cmig_ids |= set(
            (
                await db.execute(
                    select(CMIGProduct.id).where(CMIGProduct.pg_product_id.in_(cat_ids))
                )
            ).scalars().all()
        )

    cat_ids.discard(catalog_product_id)
    cmig_ids.discard(cmig_product_id)
    return cat_ids, cmig_ids


async def conflicting_listings(
    db: AsyncSession,
    *,
    catalog_product_id: int | None = None,
    cmig_product_id: int | None = None,
    exclude_listing_id: int | None = None,
) -> list[ProductListing]:
    """Anúncios ATIVOS que disputam as mesmas unidades físicas deste produto.

    Escopo GLOBAL (todas as contas): o estoque é do produto, não da conta — kit numa
    conta e componente noutra são as mesmas unidades em duas vitrines."""
    cat_ids, cmig_ids = await _sibling_keys(
        db, catalog_product_id=catalog_product_id, cmig_product_id=cmig_product_id
    )
    if not cat_ids and not cmig_ids:
        return []

    conds = []
    if cat_ids:
        conds.append(ProductListing.catalog_product_id.in_(cat_ids))
        # Anúncio ligado via DropshipperProduct aponta para o PG por outra FK.
        dp_ids = (
            await db.execute(
                select(DropshipperProduct.id).where(
                    DropshipperProduct.catalog_product_id.in_(cat_ids)
                )
            )
        ).scalars().all()
        if dp_ids:
            conds.append(ProductListing.product_id.in_(dp_ids))
    if cmig_ids:
        conds.append(ProductListing.cmig_product_id.in_(cmig_ids))

    stmt = select(ProductListing).where(_active_clause(), or_(*conds))
    if exclude_listing_id:
        stmt = stmt.where(ProductListing.id != exclude_listing_id)
    return (await db.execute(stmt)).scalars().all()


def _rank(listing) -> tuple:
    """Chave de desempate: publicou primeiro vence. `id` desempata o empate."""
    pub = getattr(listing, "published_at", None)
    return (0, pub, listing.id) if pub is not None else (1, None, listing.id)


async def loses_to_conflict(db: AsyncSession, listing) -> bool:
    """True se ESTE anúncio perde a disputa para um kit/componente já ativo.

    Usado por `available_to_push`: o perdedor reporta 0 e a ADR-0014 o pausa (ou não o
    reativa), sem que `sync_stock` precise conhecer a regra."""
    try:
        outros = await conflicting_listings(
            db,
            catalog_product_id=listing.catalog_product_id,
            cmig_product_id=listing.cmig_product_id,
            exclude_listing_id=listing.id,
        )
    except Exception:  # noqa: BLE001 — guard nunca derruba o sync de estoque
        logger.exception("loses_to_conflict listing=%s", getattr(listing, "id", None))
        return False
    if not outros:
        return False
    meu = _rank(listing)
    return any(_rank(o) < meu for o in outros)


async def describe_conflicts(db: AsyncSession, listings: list) -> list[dict]:
    """Detalhe legível dos conflitos, para a mensagem de erro e para a tela."""
    out = []
    for lst in listings:
        titulo = None
        if lst.catalog_product_id:
            titulo = (
                await db.execute(
                    select(CatalogProduct.title).where(CatalogProduct.id == lst.catalog_product_id)
                )
            ).scalar_one_or_none()
        elif lst.cmig_product_id:
            titulo = (
                await db.execute(
                    select(CMIGProduct.title).where(CMIGProduct.id == lst.cmig_product_id)
                )
            ).scalar_one_or_none()
        out.append(
            {
                "listing_id": lst.id,
                "account_id": lst.account_id,
                "platform_item_id": lst.platform_item_id,
                "status": lst.status,
                "auto_paused": bool(lst.auto_paused),
                "title": titulo,
            }
        )
    return out


async def raise_if_conflict(
    db: AsyncSession,
    *,
    catalog_product_id: int | None = None,
    cmig_product_id: int | None = None,
    exclude_listing_id: int | None = None,
) -> None:
    """Levanta 409 se publicar/reativar criaria conflito kit ⇄ componente.

    Ponto único da recusa — usado pelos gates de publicação e reativação para que a
    mensagem e a regra sejam as mesmas em todos os caminhos."""
    from fastapi import HTTPException

    conf = await conflicting_listings(
        db,
        catalog_product_id=catalog_product_id,
        cmig_product_id=cmig_product_id,
        exclude_listing_id=exclude_listing_id,
    )
    if not conf:
        return
    det = await describe_conflicts(db, conf)
    txt = "; ".join(
        f"{d['title'] or 'anúncio'} ({d['platform_item_id'] or 'sem id'}, conta #{d['account_id']})"
        for d in det[:3]
    )
    raise HTTPException(
        status_code=409,
        detail=(
            "Kit e componente não podem ser anunciados ao mesmo tempo — os dois usam as "
            f"mesmas unidades em estoque. Já está anunciado: {txt}. "
            "Pause esse anúncio para publicar/reativar este."
        ),
    )

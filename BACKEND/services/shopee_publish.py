"""Publicação na Shopee — builder agnóstico de produto (ADR-0020).

Serve os TRÊS modelos de produto do sistema (`DropshipperProduct`, `CatalogProduct`/PG e
`CMIGProduct`) a partir de um **spec normalizado**, para não existir uma segunda cópia da
regra quando o Catálogo passar a publicar. Entra por módulo NOVO: nada aqui é ramo dentro
de `if platform == "mercadolivre"`.

Separação deliberada:
- `build_item_payload` e `collect_blockers` são **PUROS** (sem ORM, sem I/O, sem
  HTTPException) → testáveis sem Oracle e sem a Shopee.
- O I/O (token, canais, categoria/marca/atributos, upload de imagem) fica nos adaptadores
  e em `fetch_shop_ctx`.

## Contrato do `add_item` no BR — verificado AO VIVO na loja do dono

Obrigatórios: `category_id` (folha, > 99999), `item_name` (2–120), `description` (10–5000),
`image.image_id_list`, `original_price`, `weight`, `dimension`, `logistic_info`,
`seller_stock`, `condition`, `brand`, **`tax_info`**.

⚠ **`tax_info` é a armadilha do BR.** A loja é "invoice issued by Shopee" e o `add_item`
falha 100% sem ele:
    `Please input the tax information becasue the shop is invoice issued by Shopee`
e, com NCM sem CEST quando o NCM exige:
    `Please upload the corresponding CEST of NCM`
O builder anterior (`listings._build_shopee_item`) NÃO enviava `tax_info` — por isso o
caminho Shopee nunca publicou. NCM/CEST vêm do cadastro fiscal do PG/CMIG.

Outros limites confirmados na API (o builder anterior usava valores menores):
- título: 2–120 (usava 100)   • descrição: 10–5000 (usava 3000, sem mínimo)
- `description_type: "extended"` é BLOQUEADO por whitelist → só texto plano.

⚠ A Shopee **curto-circuita a validação** depois da 1ª falha na janela: a 2ª chamada repete
o erro anterior. Ao depurar, não confie no retry — e não conclua "corrigiu" porque a
mensagem mudou. Campo com nome errado é **ignorado em silêncio**.

**Fora de escopo (decisão do dono):** variações (`init_tier_variation`/`add_model`) — o
builder publica item simples. Marca: sempre `brand_id: 0` + `NoBrand`, salvo marca
cadastrada. Logística: todos os canais habilitados.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TITULO_MIN, TITULO_MAX = 2, 120
DESC_MIN, DESC_MAX = 10, 5000
MAX_IMAGENS = 9
CATEGORIA_ID_MIN = 100000  # a API recusa "value must be greater than 99999"


@dataclass
class ShopeeProductInput:
    """Produto normalizado para publicar na Shopee — sem ORM.

    Os adaptadores (`from_*`) preenchem isto a partir de cada modelo; o builder e os
    bloqueios só conhecem esta forma."""

    title: str
    description: str | None
    category_id: int | None
    price: float | None
    stock: int
    sku: str | None = None
    ncm: str | None = None
    cest: str | None = None
    weight_kg: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    # [{"url": ..., "is_primary": bool, "sort_order": int}] já ordenado ou não
    images: list[dict] = field(default_factory=list)
    attributes_json: str | None = None  # cadastro da aba de categorias (PMC)
    days_to_ship: int = 2

    def imagens_ordenadas(self) -> list[dict]:
        """Capa primeiro, depois `sort_order`. Máx. 9 (limite do add_item)."""
        return sorted(
            self.images or [],
            key=lambda i: (not i.get("is_primary"), i.get("sort_order") or 0),
        )[:MAX_IMAGENS]


@dataclass
class ShopCtx:
    """Contexto da loja/categoria consultado na Shopee (I/O isolado de `fetch_shop_ctx`)."""

    logistic_info: list = field(default_factory=list)  # [{"logistic_id", "enabled"}]
    marca_obrigatoria: bool = False
    atributos_obrigatorios: list[str] = field(default_factory=list)  # nomes faltando
    limite_peso_kg: float | None = None
    erro_consulta: str | None = None  # falha ao falar com a Shopee vira bloqueio amigável


def build_shopee_attributes(attrs_raw: str | None) -> tuple[list, int | None, set]:
    """Do `attributes_json` (cadastro) → `attribute_list` do add_item + brand_id + ids salvos.

    Formato confirmado ao vivo: `value_id` da lista (original_value_name/value_unit vazios);
    `value_id=0` + `original_value_name` p/ quantitativo/texto; `value_unit` só no
    quantitativo; multi = vários itens no mesmo `attribute_value_list`."""
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
            continue  # id não-numérico não é atributo Shopee (ex.: "BRAND" do ML)
        kind = e.get("kind")
        if kind == "multi":
            vals = [
                {"value_id": int(v), "original_value_name": "", "value_unit": ""}
                for v in (e.get("value_ids") or [])
                if v is not None
            ]
        elif kind == "quantitative":
            vals = [{
                "value_id": 0,
                "original_value_name": str(e.get("value_name") or ""),
                "value_unit": e.get("value_unit") or "",
            }]
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


def _texto(v, minimo: int, maximo: int) -> str:
    t = (v or "").strip()
    return t[:maximo] if len(t) >= minimo else t


def collect_blockers(inp: ShopeeProductInput, ctx: ShopCtx | None = None) -> list[str]:
    """O que impede o `add_item` — FALHAR ALTO antes de chamar a Shopee (CLAUDE.md).

    Puro: `ctx=None` valida só o que depende do produto. Mensagens em português, dizendo
    onde resolver — uma prévia que esconde o que falta transforma erro de 1 linha em três
    rodadas de retrabalho."""
    b: list[str] = []

    if not inp.category_id:
        b.append("Falta a categoria da Shopee — escolha uma categoria FOLHA (sem subcategorias).")
    elif int(inp.category_id) < CATEGORIA_ID_MIN:
        b.append(
            f"Categoria inválida para a Shopee ({inp.category_id}). "
            "Parece uma categoria de outro marketplace — escolha uma folha da Shopee."
        )

    titulo = (inp.title or "").strip()
    if len(titulo) < TITULO_MIN:
        b.append(f"Título muito curto (mínimo {TITULO_MIN} caracteres).")

    desc = (inp.description or "").strip()
    if len(desc) < DESC_MIN:
        b.append(
            f"Descrição muito curta (a Shopee exige no mínimo {DESC_MIN} caracteres). "
            "Preencha a descrição do produto."
        )

    if not inp.price:
        b.append("Falta o preço de venda para a Shopee.")

    for nome, v in (("peso", inp.weight_kg), ("comprimento", inp.length_cm),
                    ("largura", inp.width_cm), ("altura", inp.height_cm)):
        if not v:
            b.append(f"Falta {nome} do produto (a Shopee exige para o add_item).")

    if not (inp.images or []):
        b.append("Produto sem imagens (a Shopee exige ao menos uma).")

    # tax_info — o bloqueio que faltava e que derrubava toda publicação nesta loja.
    if not (inp.ncm or "").strip():
        b.append(
            "Falta o NCM do produto. A Shopee emite a nota por você (loja 'invoice issued by "
            "Shopee') e recusa o anúncio sem a informação fiscal — preencha o NCM no cadastro."
        )

    if ctx is not None:
        if ctx.erro_consulta:
            b.append(ctx.erro_consulta)
        else:
            if not ctx.logistic_info:
                b.append("Nenhum canal de logística habilitado na loja Shopee.")
            if ctx.marca_obrigatoria:
                b.append(
                    "Esta categoria EXIGE marca — cadastre a marca da Shopee na aba de "
                    "categorias do produto (o sistema publicaria como 'Sem marca')."
                )
            if ctx.atributos_obrigatorios:
                b.append(
                    "Categoria exige atributo(s) obrigatório(s) não cadastrado(s): "
                    f"{', '.join(ctx.atributos_obrigatorios[:5])}. "
                    "Preencha na aba de categorias do produto."
                )
            if ctx.limite_peso_kg and inp.weight_kg and inp.weight_kg > ctx.limite_peso_kg:
                b.append(
                    f"Peso {inp.weight_kg} kg acima do limite do canal de logística "
                    f"({ctx.limite_peso_kg} kg)."
                )
    return b


def build_item_payload(
    inp: ShopeeProductInput, image_ids: list, logistic_info: list
) -> dict:
    """Payload do `add_item` — PURO (recebe as imagens já subidas e os canais resolvidos).

    Não valida: quem valida é `collect_blockers`, chamado ANTES pelo caller. Assim o mesmo
    payload é montável em teste sem tocar na Shopee."""
    attribute_list, brand_id, _ = build_shopee_attributes(inp.attributes_json)
    try:
        brand_id_int = int(brand_id) if brand_id is not None else 0
    except (TypeError, ValueError):
        brand_id_int = 0  # legado/manual não-numérico → "Sem marca" (não estoura o add_item)

    titulo = _texto(inp.title, TITULO_MIN, TITULO_MAX)
    # Descrição curta demais é BLOQUEIO (collect_blockers), não algo para "completar" aqui:
    # inventar texto para passar da validação esconderia o cadastro incompleto.
    descricao = _texto(inp.description or titulo, DESC_MIN, DESC_MAX)

    item: dict = {
        "item_name": titulo,
        "description": descricao,
        "category_id": int(inp.category_id),
        "original_price": float(inp.price),
        # Estoque REAL (o builder anterior fixava 1 — o anúncio nascia com 1 unidade e só
        # se corrigia no sync 30 min depois).
        "seller_stock": [{"stock": max(0, int(inp.stock or 0))}],
        "weight": float(inp.weight_kg),
        "dimension": {
            "package_length": int(inp.length_cm),
            "package_width": int(inp.width_cm),
            "package_height": int(inp.height_cm),
        },
        "logistic_info": logistic_info,
        "image": {"image_id_list": image_ids},
        # Marca cadastrada, ou "Sem marca" (decisão do dono). `original_brand_name` é o que
        # a própria loja usa nos itens publicados com brand_id 0.
        "brand": {"brand_id": brand_id_int},
        "condition": "NEW",
        "item_status": "NORMAL",
        "days_to_ship": int(inp.days_to_ship or 2),
        # ⚠ SEM `description_type: "extended"`: esta loja não está na whitelist e a API
        # recusa ("can only upload plain text").
    }
    if brand_id_int == 0:
        item["brand"]["original_brand_name"] = "NoBrand"
    if attribute_list:
        item["attribute_list"] = attribute_list
    # `item_sku` amarra o pedido ao produto na baixa de estoque (o resolvedor de item de
    # pedido usa o SKU); publicar sem ele enfraquece o vínculo.
    if (inp.sku or "").strip():
        item["item_sku"] = inp.sku.strip()
    # tax_info: obrigatório nesta loja. CEST só quando cadastrado (a Shopee exige quando o
    # NCM está em substituição tributária).
    tax: dict = {"ncm": (inp.ncm or "").strip()}
    if (inp.cest or "").strip():
        tax["cest"] = inp.cest.strip()
    item["tax_info"] = tax
    return item


# ── Adaptadores: cada modelo de produto → spec normalizado ────────────────────
# Ficam aqui (e não nos routers) para que exista UM lugar que sabe traduzir produto →
# Shopee. `services/` nunca importa `routers/`.


def _f(*vals):
    """Primeiro valor não-nulo, como float."""
    for v in vals:
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _imgs(objs) -> list[dict]:
    return [
        {"url": i.url, "is_primary": bool(getattr(i, "is_primary", False)),
         "sort_order": getattr(i, "sort_order", 0) or 0}
        for i in (objs or []) if getattr(i, "url", None)
    ]


def from_catalog_product(
    pg, *, category_id, price, stock: int, attributes_json: str | None = None,
    title: str | None = None, description: str | None = None,
) -> ShopeeProductInput:
    """Produto do galpão (PG). Fiscal (NCM/CEST) vem do próprio cadastro."""
    return ShopeeProductInput(
        title=title or pg.title or "",
        description=description or pg.description,
        category_id=int(category_id) if category_id else None,
        price=_f(price),
        stock=int(stock or 0),
        sku=pg.sku,
        ncm=pg.ncm,
        cest=pg.cest,
        weight_kg=_f(pg.weight_kg),
        length_cm=_f(pg.length_cm),
        width_cm=_f(pg.width_cm),
        height_cm=_f(pg.height_cm),
        images=_imgs(getattr(pg, "images", None)),
        attributes_json=attributes_json,
    )


def from_cmig_product(
    cp, *, category_id, price, stock: int, attributes_json: str | None = None,
    pg=None, title: str | None = None, description: str | None = None,
) -> ShopeeProductInput:
    """Produto CMIG. `pg` (espelho no galpão, opcional) supre peso/dimensão/fiscal quando o
    CMIG não os tem — mesmo fallback que o resto do sistema já faz."""
    return ShopeeProductInput(
        title=title or cp.title or "",
        description=description or cp.description,
        category_id=int(category_id) if category_id else None,
        price=_f(price),
        stock=int(stock or 0),
        sku=cp.sku_cmig,
        ncm=cp.ncm or getattr(pg, "ncm", None),
        cest=cp.cest or getattr(pg, "cest", None),
        weight_kg=_f(cp.weight_kg, getattr(pg, "weight_kg", None)),
        length_cm=_f(cp.length_cm, getattr(pg, "length_cm", None)),
        width_cm=_f(cp.width_cm, getattr(pg, "width_cm", None)),
        height_cm=_f(cp.height_cm, getattr(pg, "height_cm", None)),
        images=_imgs(getattr(cp, "images", None)) or _imgs(getattr(pg, "images", None)),
        attributes_json=attributes_json,
    )


def from_dropshipper_product(
    product, listing, *, stock: int, attributes_json: str | None = None, pg=None,
) -> ShopeeProductInput:
    """Produto do dropshipper + anúncio (caminho de `routers/listings.py`). `pg` é o
    CatalogProduct vinculado, de onde vêm peso/dimensão/fiscal."""
    return ShopeeProductInput(
        title=(getattr(product, "title_shopee", None)
               or getattr(listing, "title_override", None) or product.title or ""),
        description=product.description,
        category_id=int(listing.category_id) if listing.category_id else None,
        price=_f(getattr(listing, "sale_price", None), getattr(product, "sale_price_shopee", None)),
        stock=int(stock or 0),
        sku=getattr(product, "sku", None) or getattr(listing, "sku", None) or getattr(pg, "sku", None),
        ncm=getattr(pg, "ncm", None),
        cest=getattr(pg, "cest", None),
        weight_kg=_f(getattr(product, "weight_kg", None), getattr(pg, "weight_kg", None)),
        length_cm=_f(getattr(product, "length_cm", None), getattr(pg, "length_cm", None)),
        width_cm=_f(getattr(product, "width_cm", None), getattr(pg, "width_cm", None)),
        height_cm=_f(getattr(product, "height_cm", None), getattr(pg, "height_cm", None)),
        images=_imgs(getattr(product, "images", None)),
        attributes_json=attributes_json,
    )


async def fetch_shop_ctx(token: str, shop_id: int, category_id, attributes_json: str | None) -> ShopCtx:
    """I/O isolado: canais habilitados + exigências da categoria (marca/atributos).

    Falha ao falar com a Shopee vira BLOQUEIO textual amigável (`erro_consulta`), nunca 5xx —
    o detalhe cru fica no log."""
    from services import shopee_service

    ctx = ShopCtx()
    try:
        canais = await shopee_service.get_channel_list(token, shop_id)
        habilitados = [c for c in canais if c.get("enabled")]
        # Decisão do dono: publica em TODOS os canais habilitados.
        ctx.logistic_info = [
            {"logistic_id": c["logistics_channel_id"], "enabled": True} for c in habilitados
        ]
        limites = [c.get("weight_limit", {}).get("item_max_weight") for c in habilitados]
        limites = [float(x) for x in limites if x]
        ctx.limite_peso_kg = max(limites) if limites else None

        if category_id:
            _, saved_brand, saved_ids = build_shopee_attributes(attributes_json)
            br = await shopee_service.get_brand_list(token, shop_id, int(category_id))
            ctx.marca_obrigatoria = bool(br.get("is_mandatory")) and (
                saved_brand is None or saved_brand == 0
            )
            attrs = await shopee_service.get_attribute_tree(token, shop_id, int(category_id))
            ctx.atributos_obrigatorios = [
                a.get("name") for a in attrs
                if a.get("mandatory") and int(a.get("attribute_id", 0)) not in saved_ids
            ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[shopee_publish] falha ao consultar loja %s: %s", shop_id, exc, exc_info=True)
        ctx.erro_consulta = (
            "Não foi possível validar categoria/marca/canais na Shopee agora "
            "(a conta pode estar desconectada — reconecte). Tente novamente."
        )
    return ctx

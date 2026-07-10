"""Nome de arquivo padronizado para downloads de pedido: `<Tipo>_<venda>_<cliente>.<ext>`.

O nome do cliente e o número da venda vão para o header `Content-Disposition` — por isso
tudo é **sanitizado estritamente para ASCII** (NFKD + ascii-ignore + slug), o que também
protege contra header injection / caracteres de controle (`"`, `\\r`, `\\n`) vindos de dados
externos (nome do comprador do ML/Shopee).

Ex.: `Etiqueta_2000017318796590_Elaine-C.pdf`, `NF-e_2000017318796590_Joao-Silva.xml`.
"""
from __future__ import annotations

import re
import unicodedata

# Tipos (rótulo = formato/representação, para distinguir na pasta de Downloads)
TIPO_ETIQUETA = "Etiqueta"
TIPO_NFE = "NF-e"       # XML da NF-e
TIPO_DANFE = "DANFE"    # PDF impresso da NF-e
TIPO_DACE = "DACE"      # PDF da DC-e


def slugify_name(s: str | None, maxlen: int = 40, fallback: str = "sem-nome") -> str:
    """ASCII-slug seguro para header HTTP: remove acento, troca não-alfanumérico por '-'."""
    ascii_s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_s).strip("-")
    slug = slug[:maxlen].rstrip("-")
    return slug or fallback


def order_download_filename(
    tipo: str,
    ext: str,
    *,
    order=None,
    venda: str | None = None,
    cliente: str | None = None,
    extra: str | None = None,
) -> str:
    """Monta `<Tipo>_<venda>_<cliente>[_<extra>].<ext>` — tudo ASCII-slug.

    Passe `order` (usa `order.platform_order_id` e `order.buyer_name`, com fallback
    `pedido-<id>`) OU `venda`/`cliente` direto (ex.: NF-e de entrada sem pedido).
    """
    if order is not None:
        if venda is None:
            venda = order.platform_order_id or f"pedido-{getattr(order, 'id', '')}"
        if cliente is None:
            cliente = order.buyer_name
    parts = [
        slugify_name(tipo, maxlen=12, fallback="doc"),
        slugify_name(venda, maxlen=30, fallback="sem-venda"),
        slugify_name(cliente, maxlen=40, fallback="sem-nome"),
    ]
    if extra:
        parts.append(slugify_name(extra, maxlen=20, fallback="x"))
    return "_".join(parts) + "." + ext

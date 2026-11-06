"""Parser único e tolerante do endereço do comprador vindo do marketplace.

Motivo: o Mercado Livre devolve vários campos de endereço como **objeto**
`{"id": ..., "name": ...}` (`neighborhood`, `city`, `state`, `country`). Antes
havia 4 parsers independentes espalhados (NF-e, etiqueta, eShip, Declaração de
Conteúdo) com corretude divergente — dois desembrulhavam o objeto, dois gravavam
o `dict` cru. Isso causava:
  - crash `DPY-3002: Python value of type "dict" is not supported` ao inserir em
    `people.neighborhood` (coluna String) na emissão de NF-e; e
  - o objeto serializado impresso na etiqueta/DANFE de pedido ML.

Este módulo é o ponto único: desembrulha `{id,name}`, trata dict já serializado
em string (dado legado), normaliza a UF e **sempre devolve `str`** em cada campo.
Cobre os dois formatos de `shipping_address`:
  - ML cru (`street_name`, `street_number`, `neighborhood`:{}, `city`:{}, `state`:{})
  - normalizado do pedido manual (`street`, `number`, `neighborhood`:str, ...)
"""
from __future__ import annotations

import ast
import json
from typing import Any

__all__ = ["parse_buyer_address", "addr_text"]


def addr_text(v: Any) -> str:
    """Valor de um campo de endereço que pode vir como string, dict `{id,name}` do
    ML, ou dict já serializado em string (dado legado). Devolve `name`/`id`/valor
    limpo — **sempre** `str`."""
    if v is None:
        return ""
    if isinstance(v, dict):
        return str(v.get("name") or v.get("id") or "").strip()
    s = str(v)
    if s.startswith("{") and "name" in s:
        try:
            d = ast.literal_eval(s)
            if isinstance(d, dict):
                return str(d.get("name") or d.get("id") or "").strip()
        except Exception:  # noqa: BLE001 — dado legado malformado nunca derruba o parse
            pass
    return s.strip()


def _uf(v: Any) -> str:
    """Normaliza a UF. Para o objeto do ML `{"id": "BR-SP", "name": "São Paulo"}`
    prefere o `id` ('BR-SP') — e não o `name` — espelhando o comportamento legado
    da emissão de NF-e; reduz 'BR-SP' → 'SP'.

    Falha alto, não inventa: se o valor não for uma sigla de 2 letras nem o padrão
    'XX-SP', devolve '' (ex.: dict só com `name` por extenso "Paraná"). Devolver uma
    UF inválida como 'NÁ' só empurraria o erro para a rejeição da SEFAZ."""
    if isinstance(v, dict):
        s = str(v.get("id") or v.get("name") or "").strip()
    else:
        s = addr_text(v)
    s = s.upper()
    if len(s) == 2:
        return s
    if "-" in s:
        # 'BR-SP' / 'XX-SP' → 'SP' (só quando o sufixo é uma sigla de 2 letras)
        tail = s.rsplit("-", 1)[-1]
        if len(tail) == 2:
            return tail
    return ""


def parse_buyer_address(raw: Any) -> dict[str, str]:
    """Converte `order.shipping_address` (JSON-string CLOB OU dict) num dict de
    strings limpas e tolerantes ao formato do ML. Nunca devolve objeto num valor.

    Chaves canônicas: street, number, complement, neighborhood, city, state, zip_code.
    """
    data: dict = {}
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except (ValueError, TypeError):
            data = {}

    return {
        "street": addr_text(
            data.get("street_name") or data.get("street") or data.get("logradouro") or data.get("rua")
        ),
        "number": addr_text(
            data.get("street_number")
            or data.get("number")
            or data.get("address_number")
            or data.get("numero")
        ),
        "complement": addr_text(
            data.get("comment") or data.get("complement") or data.get("complemento")
        ),
        "neighborhood": addr_text(data.get("neighborhood") or data.get("bairro")),
        "city": addr_text(data.get("city") or data.get("cidade") or data.get("municipio")),
        "state": _uf(data.get("state") or data.get("uf")),
        "zip_code": addr_text(data.get("zip_code") or data.get("cep")),
    }

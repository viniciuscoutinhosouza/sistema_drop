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
import unicodedata
from typing import Any

__all__ = ["parse_buyer_address", "addr_text"]

# UF por nome por extenso → sigla. A Shopee manda o estado por extenso ("Minas Gerais") no
# recipient_address; o ML manda `{id:'BR-SP'}`. Ponto único do mapa (o eShip importa daqui, não
# duplica). Mapa FECHADO: nome desconhecido → '' (ver _uf) — nunca inventa UF inválida.
_UF_POR_NOME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS", "minas gerais": "MG",
    "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN", "rio grande do sul": "RS",
    "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}


def _norm_uf(s: str) -> str:
    """Normaliza p/ casar no _UF_POR_NOME: sem acento, minúsculo, sem espaços nas pontas."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().strip().lower()


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
    """Normaliza a UF para a sigla de 2 letras. Cobre:
    - ML `{"id": "BR-SP", "name": "São Paulo"}` → 'SP' (prefere o `id`, reduz 'BR-SP').
    - Sigla crua "SP"/"pr" → 'SP'/'PR'.
    - Nome por extenso "Rio Grande do Sul" (Shopee) → 'RS', via mapa FECHADO `_UF_POR_NOME`.

    Falha alto, não inventa: nome DESCONHECIDO → '' (nunca 'NÁ' ou o nome cru — devolver UF
    inválida só empurraria o erro para a rejeição da SEFAZ e estouraria o `_clip(state, 2)`)."""
    if isinstance(v, dict):
        s = str(v.get("id") or v.get("name") or "").strip()
    else:
        s = addr_text(v)
    su = s.upper()
    if len(su) == 2:
        return su
    if "-" in su:
        # 'BR-SP' / 'XX-SP' → 'SP' (só quando o sufixo é uma sigla de 2 letras)
        tail = su.rsplit("-", 1)[-1]
        if len(tail) == 2:
            return tail
    # Nome por extenso → sigla; desconhecido → '' (fail-loud, nunca inventa).
    return _UF_POR_NOME.get(_norm_uf(s), "")


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

    # Aliases Shopee (recipient_address) entram SEMPRE por ÚLTIMO em cada cadeia — as chaves do
    # ML/manual têm prioridade (o `or` curto-circuita no 1º truthy), então Shopee não sobrepõe ML.
    # A Shopee não separa rua/número: o logradouro vem inteiro em `full_address` (número/complemento
    # ficam vazios, aceitos na NF-e como "S/N"); bairro em `district`, município em `city`/`town`,
    # CEP em `zipcode`, estado por extenso em `state` (resolvido em `_uf`).
    return {
        "street": addr_text(
            data.get("street_name") or data.get("street") or data.get("logradouro") or data.get("rua")
            or data.get("address_line") or data.get("full_address")
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
        "neighborhood": addr_text(data.get("neighborhood") or data.get("bairro") or data.get("district")),
        "city": addr_text(data.get("city") or data.get("cidade") or data.get("municipio") or data.get("town")),
        "state": _uf(data.get("state") or data.get("uf")),
        "zip_code": addr_text(
            data.get("zip_code") or data.get("cep") or data.get("zipcode")
            or data.get("zip") or data.get("postal_code")
        ),
    }

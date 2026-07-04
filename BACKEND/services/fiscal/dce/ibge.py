"""Resolvedor de código IBGE do município (cidade + UF → código 7 díg.).

A DC-e exige o `cMun` do destinatário, mas o endereço do comprador vindo do ML só traz
cidade/UF em texto. Este resolvedor normaliza o nome e casa contra o cache `ibge_municipios`
(tabela seedada sob demanda da API pública do IBGE, por UF).

Fonte: https://servicodados.ibge.gov.br/api/v1/localidades/estados/{UF}/municipios
"""

from __future__ import annotations

import unicodedata

import httpx
from sqlalchemy import select

from models.fiscal import IbgeMunicipio
from services.fiscal.dce.exceptions import DceError

_IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"


def normalize_nome(nome: str) -> str:
    """Normaliza p/ casamento: sem acentos, maiúsculas, espaços colapsados."""
    if not nome:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.upper().split())


async def _seed_uf(db, uf: str) -> int:
    """Baixa os municípios da UF da API do IBGE e insere no cache. Retorna quantos inseridos."""
    url = _IBGE_URL.format(uf=uf.upper())
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise DceError(f"IBGE respondeu {resp.status_code} para UF {uf}")
        data = resp.json()
    except DceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DceError(f"Falha ao consultar municípios da UF {uf} no IBGE: {e}") from e

    inseridos = 0
    for m in data:
        codigo = str(m.get("id") or "")
        nome = m.get("nome") or ""
        if not codigo or not nome:
            continue
        exists = (
            await db.execute(select(IbgeMunicipio.codigo).where(IbgeMunicipio.codigo == codigo))
        ).first()
        if exists:
            continue
        db.add(
            IbgeMunicipio(codigo=codigo, uf=uf.upper(), nome=nome, nome_norm=normalize_nome(nome))
        )
        inseridos += 1
    await db.flush()
    return inseridos


async def resolve_municipio(db, uf: str, cidade: str) -> tuple[str, str]:
    """Retorna (codigo_ibge, nome_oficial) do município. Seed automático da UF se necessário.

    Levanta DceError se a UF/cidade não resolver — a DC-e não pode ser emitida sem o cMun.
    """
    if not uf or not cidade:
        raise DceError("UF e cidade do destinatário são obrigatórias para a DC-e (código IBGE).")
    uf = uf.strip().upper()
    alvo = normalize_nome(cidade)

    async def _buscar():
        return (
            await db.execute(
                select(IbgeMunicipio.codigo, IbgeMunicipio.nome).where(
                    IbgeMunicipio.uf == uf, IbgeMunicipio.nome_norm == alvo
                )
            )
        ).first()

    row = await _buscar()
    if row is None:
        # Cache vazio p/ esta UF? Seed e tenta de novo.
        has_uf = (
            await db.execute(select(IbgeMunicipio.codigo).where(IbgeMunicipio.uf == uf).limit(1))
        ).first()
        if not has_uf:
            await _seed_uf(db, uf)
            row = await _buscar()

    if row is None:
        raise DceError(
            f"Município '{cidade}/{uf}' não encontrado na tabela IBGE. Confira o endereço do comprador."
        )
    return str(row[0]), str(row[1])

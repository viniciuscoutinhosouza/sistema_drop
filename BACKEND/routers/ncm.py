"""Router de NCM — cadastro, consulta e importação do TEC (Tarifa Externa Comum).

Endpoints:
  GET    /ncm                — lista com filtros (busca, capítulo, ativo)
  GET    /ncm/tree           — árvore lazy por prefixo
  GET    /ncm/template-csv   — baixa template CSV
  GET    /ncm/{code}         — detalhe de um código
  POST   /ncm                — cria NCM avulso (admin)
  PATCH  /ncm/{id}           — atualiza NCM (admin)
  DELETE /ncm/{id}           — remove NCM (admin)
  POST   /ncm/import-csv     — importa TEC a partir de CSV (admin)
  POST   /ncm/sync-siscomex  — baixa e importa TEC direto do Siscomex (admin)
"""

from __future__ import annotations

import csv
import html
import io
import re
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_role
from models.fiscal import NCMCode
from models.user import User

# ── Constantes Siscomex ───────────────────────────────────────────────────────

_SISCOMEX_URL = (
    "https://portalunico.siscomex.gov.br"
    "/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO"
)

# Mapa capítulo (2 dígitos) → seção romana da TEC
_CHAPTER_SECTION: dict[str, str] = {}
for _sec, _chs in [
    ("I", range(1, 6)), ("II", range(6, 15)), ("III", range(15, 16)),
    ("IV", range(16, 25)), ("V", range(25, 28)), ("VI", range(28, 39)),
    ("VII", range(39, 41)), ("VIII", range(41, 44)), ("IX", range(44, 47)),
    ("X", range(47, 50)), ("XI", range(50, 64)), ("XII", range(64, 68)),
    ("XIII", range(68, 71)), ("XIV", range(71, 72)), ("XV", range(72, 84)),
    ("XVI", range(84, 86)), ("XVII", range(86, 90)), ("XVIII", range(90, 93)),
    ("XIX", range(93, 94)), ("XX", range(94, 97)), ("XXI", range(97, 100)),
]:
    for _ch in _chs:
        _CHAPTER_SECTION[str(_ch).zfill(2)] = _sec

router = APIRouter()

_NCM_RE = re.compile(r"^\d{8}$")


def _normalize(code: str | None) -> str | None:
    if not code:
        return None
    c = re.sub(r"[\.\-\s]", "", code.strip())
    return c if _NCM_RE.match(c) else None


def _serialize(n: NCMCode) -> dict:
    return {
        "id": n.id,
        "code": n.code,
        "description": n.description,
        "chapter": n.chapter,
        "section": n.section,
        "ipi_rate": float(n.ipi_rate) if n.ipi_rate is not None else None,
        "is_active": bool(n.is_active),
    }


# ── Listagem e detalhe ────────────────────────────────────────────────────────


@router.get("")
async def list_ncm(
    q: str | None = Query(None, description="Busca por código ou descrição"),
    chapter: str | None = Query(None, description="2 dígitos do capítulo (ex: 84)"),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista NCMs com filtros. Retorna até `limit` registros (máx 500)."""
    stmt = select(NCMCode).order_by(NCMCode.code)
    if active_only:
        stmt = stmt.where(NCMCode.is_active == 1)
    if chapter:
        stmt = stmt.where(NCMCode.chapter == chapter.strip().zfill(2))
    if q:
        like = f"%{q}%"
        normalized = _normalize(q)
        if normalized:
            stmt = stmt.where(NCMCode.code == normalized)
        else:
            stmt = stmt.where(
                or_(NCMCode.code.ilike(like), NCMCode.description.ilike(like))
            )

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    rows = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    return {"total": total, "offset": offset, "limit": limit, "items": [_serialize(r) for r in rows]}


@router.get("/template-csv")
async def download_template(current_user: User = Depends(get_current_user)):
    """Baixa o template CSV para importação do TEC."""
    lines = [
        "code;description;chapter;section;ipi_rate",
        "84713012;Computadores portáteis (notebooks);84;XVI;0.00",
        "85171231;Smartphones e telefones celulares;85;XVI;0.00",
        "61051000;Camisetas de malha de algodão;61;XI;0.00",
        "# Instruções:",
        "# - code: 8 dígitos (pode ter pontos: 8471.30.12 → converte automaticamente)",
        "# - description: até 500 caracteres",
        "# - chapter: 2 dígitos do capítulo NCM (primeiros 2 do code)",
        "# - section: número da seção da TEC (opcional)",
        "# - ipi_rate: alíquota IPI em % (ex: 15.00). Use 0 se isento.",
        "# Separador aceito: ; (ponto-e-vírgula) ou , (vírgula)",
        "# Linhas que começam com # são ignoradas",
    ]
    content = "\n".join(lines).encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="template_ncm_tec.csv"'},
    )


@router.get("/tree")
async def get_ncm_tree(
    prefix: str | None = Query(None, description="Prefixo NCM para expandir: vazio=capítulos, 2 dígitos=posições, 4=subposições, 6=itens folha"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna o próximo nível da hierarquia NCM a partir de um prefixo.

    Uso lazy: chamar recursivamente para expandir a árvore por demanda.

      prefix vazio  → 97 capítulos  (nodes de 2 dígitos)
      prefix 'XX'   → posições      (nodes de 4 dígitos)
      prefix 'XXXX' → subposições   (nodes de 6 dígitos)
      prefix 'XXXXXX' → subitens    (nodes folha de 8 dígitos)

    Cada node retorna: code, description, count, is_leaf, section.
    """
    prefix = re.sub(r"[\.\-\s]", "", (prefix or "").strip())
    plen = len(prefix)

    if plen not in (0, 2, 4, 6):
        raise HTTPException(status_code=422, detail="prefix deve ter 0, 2, 4 ou 6 dígitos")

    next_len = plen + 2  # comprimento dos filhos
    is_leaf = next_len == 8

    stmt = select(NCMCode).where(NCMCode.is_active == 1)
    if prefix:
        stmt = stmt.where(NCMCode.code.like(f"{prefix}%"))

    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    # Agrupar por sub-prefixo do próximo nível
    groups: dict[str, list[NCMCode]] = defaultdict(list)
    for r in rows:
        groups[r.code[:next_len]].append(r)

    _generic = re.compile(r"^(outros?|outras?|demais|diverso[sa]?)(\s|$)", re.I)
    _suffix   = re.compile(r"\s*[—–-]\s*(outros?|outras?)$", re.I)

    def best_desc(children: list[NCMCode]) -> str:
        """Descrição representativa: primeiro filho não-genérico."""
        for c in children:
            d = (c.description or "").strip()
            if d and not _generic.match(d):
                # Remove sufixo genérico " — Outros" se houver
                return _suffix.sub("", d).strip()
        return (children[0].description or children[0].code[:next_len]).strip()

    result = []
    for sub in sorted(groups):
        children = groups[sub]
        desc = children[0].description if is_leaf else best_desc(children)
        result.append({
            "code": sub,
            "description": desc,
            "count": len(children),
            "is_leaf": is_leaf,
            "section": children[0].section or "",
            "chapter": sub[:2],
        })

    return result


@router.get("/{code}")
async def get_ncm(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized = _normalize(code)
    if not normalized:
        raise HTTPException(status_code=422, detail="Código NCM deve ter 8 dígitos")
    row = (
        await db.execute(select(NCMCode).where(NCMCode.code == normalized))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"NCM {code} não encontrado")
    return _serialize(row)


# ── CRUD avulso (admin) ───────────────────────────────────────────────────────


@router.post("", dependencies=[Depends(require_role("admin"))])
async def create_ncm(body: dict, db: AsyncSession = Depends(get_db)):
    code = _normalize(body.get("code"))
    if not code:
        raise HTTPException(status_code=422, detail="code deve ter 8 dígitos numéricos")
    existing = (
        await db.execute(select(NCMCode).where(NCMCode.code == code))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"NCM {code} já cadastrado")
    ncm = NCMCode(
        code=code,
        description=(body.get("description") or "").strip()[:500] or "—",
        chapter=code[:2],
        section=(body.get("section") or "").strip() or None,
        ipi_rate=body.get("ipi_rate"),
        is_active=1,
    )
    db.add(ncm)
    await db.commit()
    await db.refresh(ncm)
    return _serialize(ncm)


@router.patch("/{ncm_id}", dependencies=[Depends(require_role("admin"))])
async def update_ncm(ncm_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    ncm = (
        await db.execute(select(NCMCode).where(NCMCode.id == ncm_id))
    ).scalar_one_or_none()
    if not ncm:
        raise HTTPException(status_code=404, detail="NCM não encontrado")
    for k in ("description", "section", "ipi_rate", "is_active"):
        if k in body:
            v = body[k]
            if k == "is_active":
                v = 1 if v else 0
            setattr(ncm, k, v)
    await db.commit()
    await db.refresh(ncm)
    return _serialize(ncm)


@router.delete("/{ncm_id}", dependencies=[Depends(require_role("admin"))])
async def delete_ncm(ncm_id: int, db: AsyncSession = Depends(get_db)):
    ncm = (
        await db.execute(select(NCMCode).where(NCMCode.id == ncm_id))
    ).scalar_one_or_none()
    if not ncm:
        raise HTTPException(status_code=404, detail="NCM não encontrado")
    db.delete(ncm)
    await db.commit()
    return {"detail": f"NCM {ncm.code} removido"}


# ── Helpers de processamento do JSON Siscomex ────────────────────────────────


def _sanitize_desc(text: str) -> str:
    """Remove tags HTML, entidades e traços iniciais de hierarquia."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"^[-–—\s]+", "", text)
    text = re.sub(r"[ \s]+", " ", text).strip()
    return text


def _parse_siscomex_json(data: dict) -> tuple[list[dict], str]:
    """Processa o JSON do Siscomex e retorna (lista_ncm8, data_atualizacao).

    Filtra apenas os subitens de 8 dígitos vigentes (data_fim = 31/12/9999).
    Constrói descrição representativa usando hierarquia dos níveis superiores.
    """
    items = data.get("Nomenclaturas", [])
    updated_at = data.get("Data_Ultima_Atualizacao_NCM", "")

    # Mapa hierárquico: código sem pontos → descrição limpa
    hierarchy: dict[str, str] = {}
    for item in items:
        cod = re.sub(r"[.\s]", "", item["Codigo"])
        hierarchy[cod] = _sanitize_desc(item["Descricao"])

    _generic = re.compile(r"^(outros?|outras?|demais|diverso[sa]?)$", re.I)
    _suffix   = re.compile(r"\s*[—–-]\s*(outros?|outras?)$", re.I)

    def build_desc(cod8: str) -> str:
        descs = []
        for n in (2, 4, 6, 8):
            d = hierarchy.get(cod8[:n], "")
            if d and d not in descs:
                descs.append(d)
        if not descs:
            return ""
        leaf = descs[-1]
        if _generic.match(leaf) and len(descs) >= 2:
            return _suffix.sub("", descs[-2]).strip() + " — " + leaf
        return leaf

    result = []
    for item in items:
        cod = re.sub(r"[.\s]", "", item["Codigo"])
        if len(cod) != 8 or not cod.isdigit():
            continue
        data_fim = item.get("Data_Fim", "")
        if data_fim and data_fim != "31/12/9999":
            continue
        chapter = cod[:2]
        result.append({
            "code": cod,
            "description": build_desc(cod)[:500],
            "chapter": chapter,
            "section": _CHAPTER_SECTION.get(chapter, ""),
        })

    return result, updated_at


async def _upsert_ncm_list(
    db: AsyncSession,
    ncm_list: list[dict],
    overwrite: bool,
) -> dict:
    """Upsert eficiente: 1 query para carregar existentes + inserts/updates em batch.

    Evita N queries individuais — crítico para os ~10.500 NCMs do TEC.
    """
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    # 1. Carrega todos os códigos existentes de uma vez (1 query)
    existing_rows = (
        await db.execute(select(NCMCode.code, NCMCode.id))
    ).all()
    existing_map: dict[str, int] = {row.code: row.id for row in existing_rows}

    BATCH = 500
    to_insert: list[dict] = []
    to_update: list[dict] = []

    for item in ncm_list:
        code = item["code"]
        if code in existing_map:
            if overwrite:
                to_update.append({**item, "id": existing_map[code]})
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        else:
            to_insert.append(item)
            stats["created"] += 1

    # 2. Inserts em batch
    for i in range(0, len(to_insert), BATCH):
        batch = to_insert[i : i + BATCH]
        for item in batch:
            db.add(NCMCode(
                code=item["code"],
                description=item["description"],
                chapter=item["chapter"],
                section=item.get("section", ""),
                is_active=1,
            ))
        await db.flush()

    # 3. Updates em batch (apenas se overwrite=True)
    for i in range(0, len(to_update), BATCH):
        batch = to_update[i : i + BATCH]
        for item in batch:
            await db.execute(
                NCMCode.__table__.update()
                .where(NCMCode.id == item["id"])
                .values(
                    description=item["description"],
                    chapter=item["chapter"],
                    section=item.get("section", ""),
                    is_active=1,
                )
            )
        await db.flush()

    await db.commit()
    return stats


# ── Sincronização direta do Siscomex ─────────────────────────────────────────

_HTTPX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MIGEcommerce/2.0; +https://migecommerce.com.br)",
    "Accept": "application/json, */*",
}


async def _fetch_siscomex_json() -> dict:
    """Baixa o JSON do Siscomex. Tenta com e sem SSL verify em caso de falha."""
    timeout = httpx.Timeout(connect=30, read=120, write=30, pool=10)

    # Tentativa 1: conexão normal
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=_HTTPX_HEADERS,
        ) as client:
            resp = await client.get(_SISCOMEX_URL)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=(
                "Timeout ao conectar no Portal Único Siscomex. "
                "Verifique se o servidor tem acesso à internet (porta 443 outbound)."
            ),
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Siscomex retornou HTTP {e.response.status_code}.",
        )
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Sem conexão com portalunico.siscomex.gov.br: {e}. "
                "Use a opção 'Importar CSV' com o arquivo baixado manualmente."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erro inesperado ao acessar Siscomex: {type(e).__name__}: {e}",
        )


@router.get("/test-siscomex", dependencies=[Depends(require_role("admin"))])
async def test_siscomex_connectivity():
    """Testa a conectividade com o Portal Único Siscomex sem importar nada.
    Retorna status, tempo de resposta e data de vigência da TEC atual.
    """
    import time
    timeout = httpx.Timeout(connect=15, read=30, write=10, pool=5)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=_HTTPX_HEADERS,
        ) as client:
            # HEAD não funciona na API do Siscomex — baixa só o início
            resp = await client.get(_SISCOMEX_URL)
            resp.raise_for_status()
            elapsed = round((time.monotonic() - t0) * 1000)
            # Extrai apenas a data sem parsear tudo
            raw = resp.text[:200]
            import re as _re
            m = _re.search(r'"Data_Ultima_Atualizacao_NCM"\s*:\s*"([^"]+)"', raw)
            vigencia = m.group(1) if m else "não encontrada"
            return {
                "ok": True,
                "http_status": resp.status_code,
                "elapsed_ms": elapsed,
                "content_length_kb": round(len(resp.content) / 1024),
                "vigencia": vigencia,
                "url": _SISCOMEX_URL,
            }
    except HTTPException:
        raise
    except Exception as e:
        elapsed = round((time.monotonic() - t0) * 1000)
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "elapsed_ms": elapsed,
            "url": _SISCOMEX_URL,
            "suggestion": (
                "O servidor não consegue acessar portalunico.siscomex.gov.br. "
                "Verifique regras de firewall/Security List na Oracle Cloud (porta 443 outbound). "
                "Como alternativa, use 'Importar CSV' com o arquivo baixado localmente."
            ),
        }


@router.post("/sync-siscomex", dependencies=[Depends(require_role("admin"))])
async def sync_from_siscomex(
    overwrite: bool = Query(False, description="Atualiza NCMs já existentes"),
    db: AsyncSession = Depends(get_db),
):
    """Baixa a TEC diretamente do Portal Único Siscomex e importa no banco."""
    data = await _fetch_siscomex_json()

    ncm_list, updated_at = _parse_siscomex_json(data)
    if not ncm_list:
        raise HTTPException(status_code=502, detail="Nenhum NCM de 8 dígitos encontrado no JSON")

    stats = await _upsert_ncm_list(db, ncm_list, overwrite)
    stats["source_date"] = updated_at
    stats["total_processed"] = len(ncm_list)
    stats["detail"] = f"TEC sincronizada do Siscomex ({updated_at})"
    return stats


# ── Importação via upload do JSON Siscomex ───────────────────────────────────


@router.post("/import-json", dependencies=[Depends(require_role("admin"))])
async def import_siscomex_json(
    json_file: UploadFile = File(..., description="Arquivo JSON baixado do Portal Único Siscomex"),
    overwrite: bool = Query(False, description="Atualiza NCMs já existentes"),
    db: AsyncSession = Depends(get_db),
):
    """Importa a TEC a partir de um arquivo JSON baixado manualmente do Siscomex.

    Aceita o arquivo exato retornado por:
    portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO
    """
    if not json_file.filename:
        raise HTTPException(status_code=422, detail="Arquivo JSON não informado")

    content = await json_file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo JSON vazio")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 50 MB)")

    # Decodifica — tenta utf-8-sig primeiro (remove BOM de browsers Windows)
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(status_code=422, detail="Não foi possível decodificar o arquivo JSON. Salve o arquivo como UTF-8 sem BOM.")

    import json as _json
    try:
        data = _json.loads(text)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Arquivo não é um JSON válido: {exc}. Verifique se o download foi completo.",
        )

    # Detecta se é a resposta de erro do Siscomex (rate limit ou indisponibilidade)
    if "code" in data and "message" in data and "Nomenclaturas" not in data:
        msg = data.get("message", "Erro desconhecido do Siscomex")
        raise HTTPException(
            status_code=422,
            detail=f"O arquivo baixado contém uma mensagem de erro do Siscomex, não a TEC: {msg[:300]}",
        )

    if "Nomenclaturas" not in data:
        chaves = list(data.keys())[:8]
        raise HTTPException(
            status_code=422,
            detail=(
                f'JSON não contém o campo "Nomenclaturas". '
                f"Chaves encontradas: {chaves}. "
                "Certifique-se de baixar o arquivo correto do link indicado."
            ),
        )

    ncm_list, updated_at = _parse_siscomex_json(data)
    if not ncm_list:
        raise HTTPException(status_code=422, detail="Nenhum NCM de 8 dígitos vigente encontrado no arquivo")

    stats = await _upsert_ncm_list(db, ncm_list, overwrite)
    stats["source_date"] = updated_at
    stats["total_processed"] = len(ncm_list)
    stats["detail"] = f"TEC importada do arquivo JSON ({updated_at})"
    return stats


# ── Importação em massa via CSV ───────────────────────────────────────────────


@router.post("/import-csv", dependencies=[Depends(require_role("admin"))])
async def import_tec_csv(
    csv_file: UploadFile = File(..., description="Arquivo CSV do TEC (separador ; ou ,)"),
    overwrite: bool = Query(False, description="Se True, atualiza registros existentes"),
    db: AsyncSession = Depends(get_db),
):
    """Importa o TEC completo a partir de um arquivo CSV.

    Regras:
    - Linhas começando com '#' são ignoradas (comentários).
    - Primeira linha não-comentário é o cabeçalho.
    - Colunas obrigatórias: `code` e `description`.
    - Colunas opcionais: `chapter`, `section`, `ipi_rate`.
    - `overwrite=True` → atualiza registros existentes com os dados do CSV.
    - `overwrite=False` (padrão) → pula registros já existentes.

    Retorna estatísticas: criados, atualizados, pulados, erros.
    """
    if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Arquivo deve ter extensão .csv")

    content = await csv_file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo CSV vazio")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo CSV muito grande (máx 20 MB)")

    try:
        text = content.decode("utf-8-sig")  # remove BOM se presente
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    # Detectar separador
    first_data_line = next((l for l in text.splitlines() if l and not l.startswith("#")), "")
    separator = ";" if first_data_line.count(";") >= first_data_line.count(",") else ","

    reader = csv.DictReader(
        (line for line in text.splitlines() if not line.startswith("#")),
        delimiter=separator,
    )

    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0, "error_details": []}

    BATCH = 200  # commit a cada N registros

    for i, row in enumerate(reader, start=1):
        # Normaliza chaves
        normalized_row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}

        code = _normalize(normalized_row.get("code") or normalized_row.get("codigo") or normalized_row.get("ncm") or "")
        if not code:
            stats["errors"] += 1
            if len(stats["error_details"]) < 20:
                stats["error_details"].append(f"Linha {i+1}: código inválido → '{normalized_row.get('code', '')}'")
            continue

        description = (normalized_row.get("description") or normalized_row.get("descricao") or "").strip()[:500]
        if not description:
            stats["errors"] += 1
            if len(stats["error_details"]) < 20:
                stats["error_details"].append(f"Linha {i+1}: descrição vazia para NCM {code}")
            continue

        chapter = (normalized_row.get("chapter") or normalized_row.get("capitulo") or code[:2]).strip()[:2]
        section = (normalized_row.get("section") or normalized_row.get("secao") or "").strip()[:5] or None
        ipi_raw = normalized_row.get("ipi_rate") or normalized_row.get("ipi") or ""
        try:
            ipi_rate = float(ipi_raw.replace(",", ".")) if ipi_raw else None
        except ValueError:
            ipi_rate = None

        existing = (
            await db.execute(select(NCMCode).where(NCMCode.code == code))
        ).scalar_one_or_none()

        if existing:
            if overwrite:
                existing.description = description
                existing.chapter = chapter
                existing.section = section
                if ipi_rate is not None:
                    existing.ipi_rate = ipi_rate
                existing.is_active = 1
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        else:
            db.add(NCMCode(
                code=code,
                description=description,
                chapter=chapter,
                section=section,
                ipi_rate=ipi_rate,
                is_active=1,
            ))
            stats["created"] += 1

        if (stats["created"] + stats["updated"]) % BATCH == 0:
            await db.flush()

    await db.commit()

    return {
        "detail": "Importação concluída",
        "created": stats["created"],
        "updated": stats["updated"],
        "skipped": stats["skipped"],
        "errors": stats["errors"],
        "error_details": stats["error_details"],
    }

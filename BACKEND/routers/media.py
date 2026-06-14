"""Endpoints de mídia por IA (Fase B). Geração de imagem via Gemini (Nano Banana).

Custo: cada chamada é paga — o frontend confirma com o usuário antes de chamar.
Auth: usuário autenticado (mesmo nível do upload de fotos de anúncio).
"""

import base64
import io
import ipaddress
import json
import logging
import os as _os
import socket
import uuid as _uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.integration import MarketplaceSetting, MediaClipJob
from models.messages import AIConfig
from models.user import User
from routers.marketplace_settings import DEFAULT_MEDIA_SPECS
from services import media_ai_service, product_brief

router = APIRouter(prefix="/api/v1/media", tags=["media"])
logger = logging.getLogger(__name__)

MAX_SOURCE_IMAGES = 4
MAX_PROMPT_CHARS = 4000
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
_DEST_DIR = "static/uploads/media"
_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# Prompt default para "estender" (outpaint) a imagem que o cliente já enviou
# com bordas brancas no aspecto alvo.
_DEFAULT_OUTPAINT_PROMPT = (
    "Esta imagem tem bordas brancas/vazias para atingir o formato desejado. "
    "Preencha essas bordas estendendo o cenário e o fundo de forma natural e realista, "
    "SEM cortar, mover ou distorcer o produto principal — mantenha o produto exatamente "
    "como está. Devolva a imagem completa preenchida."
)


def _decode_key(encoded: str | None) -> str:
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return ""


async def _load_media_ai(db: AsyncSession) -> tuple[str, str, str, str]:
    """Retorna (provider, api_key, image_model, instructions) da config de IA de mídia."""
    cfg = (await db.execute(select(AIConfig))).scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=400, detail="Configure a IA de mídia em Configuração de IA.")
    api_key = _decode_key(cfg.media_api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="Chave de IA de mídia não configurada.")
    return (
        cfg.media_provider or "google",
        api_key,
        cfg.media_image_model or "gemini-2.5-flash-image",
        (cfg.media_instructions or "").strip(),
    )


def _with_instructions(instructions: str, prompt: str) -> str:
    """Prefixa o perfil/instruções de mídia ao prompt (instruções primeiro)."""
    instructions = (instructions or "").strip()
    return f"{instructions}\n\n{prompt}" if instructions else prompt


def _with_instructions_budget(instructions: str, prompt: str, max_total: int = 1000) -> str:
    """Como _with_instructions, mas com orçamento total (p/ o cap de ~1024 do Veo):
    reserva espaço para o prompt do usuário e trunca as instruções para caber —
    assim instruções longas não 'comem' o prompt do clip."""
    instructions = (instructions or "").strip()
    if not instructions:
        return prompt[:max_total]
    room = max_total - len(prompt) - 2  # 2 = "\n\n"
    if room <= 40:  # quase sem espaço p/ instruções → preserva o prompt do usuário
        return prompt[:max_total]
    return f"{instructions[:room]}\n\n{prompt}"


def _truncate_bytes(text: str, max_bytes: int) -> str:
    """Trunca a string para caber em `max_bytes` em UTF-8 (a coluna Oracle conta
    bytes, não caracteres; acentos ocupam 2+ bytes)."""
    return (text or "").encode("utf-8")[:max_bytes].decode("utf-8", "ignore")


async def _rec_px_for(db: AsyncSession, marketplace: str | None) -> int:
    """Px recomendado (lado maior) do marketplace, para o upscale pós-IA."""
    if not marketplace:
        return 0
    rec = (DEFAULT_MEDIA_SPECS.get(marketplace, {}).get("image", {}) or {}).get("rec_px", 0)
    row = (
        await db.execute(
            select(MarketplaceSetting).where(MarketplaceSetting.marketplace == marketplace)
        )
    ).scalar_one_or_none()
    if row and row.settings_json:
        try:
            stored = (json.loads(row.settings_json).get("media", {}).get("image", {}) or {})
            if stored.get("rec_px"):
                rec = int(stored["rec_px"])
        except Exception:
            pass
    return int(rec or 0)


def _safe_static_path(url: str, exts: tuple = _IMG_EXTS) -> str | None:
    """Resolve uma URL /static/... para um caminho de arquivo SEGURO dentro de
    `static/` (bloqueia path traversal), restrito às extensões permitidas."""
    rel = url.split("?", 1)[0].lstrip("/")  # remove querystring e a barra inicial
    base = _os.path.realpath("static")
    full = _os.path.realpath(rel)  # rel já começa com 'static/'
    try:
        if _os.path.commonpath([base, full]) != base:
            return None  # tentou sair de static/
    except ValueError:
        return None  # drives diferentes no Windows, etc.
    if _os.path.splitext(full)[1].lower() not in exts:
        return None
    return full if _os.path.isfile(full) else None


def _is_public_https(url: str) -> bool:
    """Permite só https para host público (bloqueia SSRF a IPs privados/metadata)."""
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                return False
    except Exception:
        return False
    return True


async def _fetch_image(url: str) -> bytes | None:
    """Lê os bytes de uma imagem por URL com proteção contra path traversal (local)
    e SSRF (remoto). Aceita: arquivo local em static/ ou https público."""
    try:
        if url.startswith("/static/") or url.startswith("static/"):
            path = _safe_static_path(url)
            if not path:
                logger.warning("[media] caminho local rejeitado: %s", url[:120])
                return None
            with open(path, "rb") as f:
                return f.read()
        if url.startswith("https://"):
            if not _is_public_https(url):
                logger.warning("[media] URL remota rejeitada (SSRF guard): %s", url[:120])
                return None
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                r = await client.get(url)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ct.startswith("image/"):
                return r.content
    except Exception as exc:
        logger.warning("[media] falha ao ler imagem %s: %s", url[:80], exc)
    return None


def _save_image(data: bytes) -> tuple[str, int, int]:
    """Salva os bytes em static/uploads/media, detectando o formato real.
    Retorna (url, width, height)."""
    ext, w, h = ".jpg", 0, 0
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            fmt = (im.format or "JPEG").lower()
            ext = {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "gif": ".gif"}.get(fmt, ".jpg")
    except Exception:
        pass
    _os.makedirs(_DEST_DIR, exist_ok=True)
    filename = f"{_uuid.uuid4().hex}{ext}"
    try:
        with open(f"{_DEST_DIR}/{filename}", "wb") as out:
            out.write(data)
    except OSError as exc:
        logger.error("[media] falha ao salvar imagem: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao salvar a imagem gerada.") from exc
    return (f"/static/uploads/{_os.path.basename(_DEST_DIR)}/{filename}", w, h)


@router.post("/generate-image")
async def generate_image(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gera uma imagem por IA a partir de um prompt (+ fotos de referência e ficha
    técnica do produto, opcionais). Faz upscale ao px recomendado do marketplace.

    Body: { prompt, marketplace?, source_urls?[], product_type?, product_id?, include_brief? }
    """
    prompt = (body.get("prompt") or "").strip()[:MAX_PROMPT_CHARS]
    if not prompt:
        raise HTTPException(status_code=400, detail="Informe o prompt para gerar a imagem.")

    provider, api_key, model, instructions = await _load_media_ai(db)

    # Ficha técnica do produto (opcional) injetada como contexto.
    final_prompt = prompt
    if body.get("include_brief") and body.get("product_type") and body.get("product_id"):
        brief = await product_brief.build_product_brief(
            db, body["product_type"], int(body["product_id"])
        )
        if brief:
            final_prompt = (
                f"{prompt}\n\nUse as informações do produto a seguir como referência "
                f"(não as escreva na imagem):\n{brief}"
            )
    final_prompt = _with_instructions(instructions, final_prompt)

    # Imagens de referência (opcionais).
    images: list[bytes] = []
    for url in (body.get("source_urls") or [])[:MAX_SOURCE_IMAGES]:
        b = await _fetch_image(url)
        if b:
            images.append(b)

    raw = await media_ai_service.generate_image(
        provider=provider, api_key=api_key, model=model, prompt=final_prompt, images=images
    )

    # Upscale: usa o px recomendado do marketplace; sem marketplace (ex.: produto),
    # garante um mínimo de 1200px (padrão ML) para a imagem não sair pequena.
    rec_px = await _rec_px_for(db, body.get("marketplace")) or 1200
    raw = media_ai_service.upscale_to(raw, rec_px)

    url, w, h = _save_image(raw)
    return {"url": url, "width": w, "height": h}


@router.post("/ai-edit")
async def ai_edit(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    marketplace: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edita/estende (outpaint) uma imagem por IA. O cliente envia a imagem já no
    formato alvo (com bordas brancas, p/ a IA preencher). Faz upscale ao px do
    marketplace e salva. Custo por imagem — o frontend confirma antes de chamar.
    """
    ext = _os.path.splitext(file.filename or "")[1].lower()
    if ext not in _IMG_EXTS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido (use JPG/PNG/WEBP/GIF).")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Imagem muito grande (máx. 15 MB).")
    if not data:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    provider, api_key, model, instructions = await _load_media_ai(db)
    final_prompt = (prompt or "").strip()[:MAX_PROMPT_CHARS] or _DEFAULT_OUTPAINT_PROMPT
    final_prompt = _with_instructions(instructions, final_prompt)

    raw = await media_ai_service.generate_image(
        provider=provider, api_key=api_key, model=model, prompt=final_prompt, images=[data]
    )
    rec_px = await _rec_px_for(db, marketplace or None)
    if rec_px:
        raw = media_ai_service.upscale_to(raw, rec_px)

    url, w, h = _save_image(raw)
    return {"url": url, "width": w, "height": h}


# ─── Clips / vídeo (Veo, assíncrono) ─────────────────────────────────────────

def _save_video(data: bytes) -> str:
    _os.makedirs(_DEST_DIR, exist_ok=True)
    filename = f"{_uuid.uuid4().hex}.mp4"
    try:
        with open(f"{_DEST_DIR}/{filename}", "wb") as out:
            out.write(data)
    except OSError as exc:
        logger.error("[media] falha ao salvar vídeo: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao salvar o vídeo gerado.") from exc
    return f"/static/uploads/{_os.path.basename(_DEST_DIR)}/{filename}"


def _is_allowed_video_host(uri: str) -> bool:
    """URI do vídeo (vinda da resposta do Veo) deve ser https público de domínio Google."""
    if not _is_public_https(uri):
        return False
    host = urlparse(uri).hostname or ""
    return host.endswith(".googleapis.com") or host.endswith(".googleusercontent.com")


async def _clip_aspect(db: AsyncSession, marketplace: str | None) -> str:
    """Proporção do clip do marketplace → "16:9" (default) ou "9:16"."""
    asp = ""
    if marketplace:
        asp = (DEFAULT_MEDIA_SPECS.get(marketplace, {}).get("clip", {}) or {}).get("aspect", "")
        row = (
            await db.execute(
                select(MarketplaceSetting).where(MarketplaceSetting.marketplace == marketplace)
            )
        ).scalar_one_or_none()
        if row and row.settings_json:
            try:
                asp = (json.loads(row.settings_json).get("media", {}).get("clip", {}) or {}).get("aspect", asp)
            except Exception:
                pass
    return "9:16" if "9:16" in (asp or "") else "16:9"


@router.post("/generate-clip")
async def generate_clip(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Inicia a geração de um clip de vídeo por IA (Veo). Assíncrono: retorna um
    job_id; o cliente consulta /clip-status/{job_id}. Custo por segundo — confirmar antes.
    """
    prompt = (body.get("prompt") or "").strip()[:MAX_PROMPT_CHARS]
    if not prompt:
        raise HTTPException(status_code=400, detail="Informe o prompt para gerar o clip.")

    # Cota: limita clips em geração simultânea por usuário (controla custo/abuso).
    running = (
        await db.execute(
            select(func.count()).select_from(MediaClipJob).where(
                MediaClipJob.user_id == current_user.id, MediaClipJob.status == "running"
            )
        )
    ).scalar() or 0
    if running >= 3:
        raise HTTPException(
            status_code=429,
            detail="Você já tem 3 clips em geração. Aguarde concluírem antes de gerar mais.",
        )

    provider, api_key, _img_model, instructions = await _load_media_ai(db)
    cfg = (await db.execute(select(AIConfig))).scalar_one_or_none()
    model = (cfg.media_video_model if cfg else None) or "veo-3.1-fast-generate-preview"

    final_prompt = prompt
    if body.get("include_brief") and body.get("product_type") and body.get("product_id"):
        brief = await product_brief.build_product_brief(
            db, body["product_type"], int(body["product_id"])
        )
        if brief:
            final_prompt = f"{prompt}\n\nReferência do produto:\n{brief}"
    # Clip (Veo) tem cap de ~1024 chars — usa composição com orçamento.
    final_prompt = _with_instructions_budget(instructions, final_prompt)

    img_bytes = None
    if body.get("source_url"):
        img_bytes = await _fetch_image(body["source_url"])

    marketplace = body.get("marketplace") or None
    aspect = await _clip_aspect(db, marketplace)

    operation = await media_ai_service.start_video(
        api_key=api_key, model=model, prompt=final_prompt, image_bytes=img_bytes, aspect=aspect
    )

    _ptype = body.get("product_type") or None
    _pid = body.get("product_id")
    job = MediaClipJob(
        user_id=current_user.id, operation=operation, marketplace=marketplace,
        product_type=_ptype, product_id=int(_pid) if _pid else None,
        prompt=_truncate_bytes(final_prompt, 1000), status="running",
    )
    db.add(job)
    await db.flush()
    job_id = job.id
    await db.commit()
    return {"job_id": job_id, "status": "running"}


@router.get("/clip-status/{job_id}")
async def clip_status(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Consulta o job; quando o Veo termina, baixa e salva o mp4 e devolve a URL."""
    job = (
        await db.execute(select(MediaClipJob).where(MediaClipJob.id == job_id))
    ).scalar_one_or_none()
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Clip não encontrado.")
    if job.status in ("done", "failed"):
        return {"status": job.status, "url": job.video_url, "error": job.error}

    _provider, api_key, _m, _instr = await _load_media_ai(db)
    st = await media_ai_service.video_status(api_key, job.operation)
    if not st.get("done"):
        return {"status": "running"}

    # Re-checa o job (outro poll concorrente pode ter finalizado durante o await).
    await db.refresh(job)
    if job.status in ("done", "failed"):
        return {"status": job.status, "url": job.video_url, "error": job.error}

    if st.get("error"):
        job.status, job.error = "failed", st["error"]
        await db.commit()
        return {"status": "failed", "error": job.error}

    uri = st.get("uri") or ""
    if not _is_allowed_video_host(uri):
        job.status, job.error = "failed", "URI de vídeo rejeitada (host não permitido)."
        await db.commit()
        return {"status": "failed", "error": job.error}

    data = await media_ai_service.download_video(api_key, uri)
    job.video_url = _save_video(data)
    job.status = "done"
    await db.commit()
    return {"status": "done", "url": job.video_url}


@router.get("/clips")
async def list_clips(
    product_type: str | None = None,
    product_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista clips recentes. Sempre escopado ao usuário; se product_type+product_id
    vierem, filtra os clips daquele produto (recuperação após reload no form)."""
    stmt = select(MediaClipJob).where(MediaClipJob.user_id == current_user.id)
    if product_type and product_id:
        stmt = stmt.where(
            MediaClipJob.product_type == product_type,
            MediaClipJob.product_id == product_id,
        )
    rows = (await db.execute(stmt.order_by(MediaClipJob.id.desc()).limit(20))).scalars().all()
    return {
        "clips": [
            {"job_id": r.id, "status": r.status, "url": r.video_url, "error": r.error,
             "prompt": r.prompt, "marketplace": r.marketplace}
            for r in rows
        ]
    }


@router.delete("/clips/{job_id}")
async def delete_clip(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui um clip (registro + arquivo mp4). Só o dono pode excluir."""
    job = (
        await db.execute(
            select(MediaClipJob).where(
                MediaClipJob.id == job_id, MediaClipJob.user_id == current_user.id
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Clip não encontrado.")

    # Apaga o arquivo (caminho validado dentro de static/, extensão .mp4) — best-effort.
    if job.video_url:
        path = _safe_static_path(job.video_url, exts=(".mp4",))
        if path:
            try:
                _os.remove(path)
            except OSError:
                pass

    db.delete(job)
    await db.commit()
    return {"ok": True}

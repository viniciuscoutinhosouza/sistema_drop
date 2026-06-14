"""IA de mídia (imagens) — geração/edição via Gemini 2.5 Flash Image (Nano Banana).

Best-effort + custo: cada chamada é paga. Os chamadores devem confirmar a ação
com o usuário antes de invocar. Suporta provider 'google' (Gemini). 'openai'
(gpt-image-1) ainda não implementado.
"""

import base64
import io
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Geração de imagem exige v1beta (v1 não aceita generationConfig.responseModalities).
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Veo (vídeo) só existe em v1beta com operação long-running.
VEO_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_VIDEO_BYTES = 100 * 1024 * 1024  # 100 MB
TIMEOUT = 120  # geração de imagem é lenta; default do httpx (5s) é curto demais


async def generate_image(
    *,
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    images: list[bytes] | None = None,
) -> bytes:
    """Gera/edita uma imagem a partir de um prompt (+ imagens de referência opcionais).

    Retorna os bytes da imagem (PNG/JPEG). Levanta HTTPException em falha.
    """
    if not api_key:
        raise HTTPException(status_code=400, detail="Chave de IA de mídia não configurada.")
    if provider != "google":
        raise HTTPException(
            status_code=400,
            detail=f"Provider de imagem '{provider}' ainda não suportado (use 'google').",
        )
    return await _generate_gemini(api_key, model, prompt, images or [])


def _api_error_detail(resp, kind: str) -> str:
    """Extrai a mensagem de erro da API Google p/ mostrar algo acionável ao usuário
    (ex.: quota/billing em 429, argumento inválido em 400)."""
    try:
        msg = (resp.json().get("error") or {}).get("message") or ""
    except Exception:
        msg = ""
    if resp.status_code == 429:
        return (
            "Cota da IA esgotada. A geração de "
            f"{kind} (Gemini/Veo) não funciona no nível gratuito — habilite "
            "faturamento (billing) na chave do Google."
        )
    base = f"Erro na API de {kind} (IA) [{resp.status_code}]"
    return f"{base}: {msg[:200]}" if msg else base


async def _generate_gemini(api_key: str, model: str, prompt: str, images: list[bytes]) -> bytes:
    parts: list[dict] = [{"text": prompt}]
    for img in images:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(img).decode(),
            }
        })
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    url = GEMINI_URL.format(model=model)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Tempo esgotado na geração de imagem (IA).") from exc

    if resp.status_code != 200:
        logger.warning("[media-ai] gemini status=%s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail=_api_error_detail(resp, "imagem"))

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        # Pode vir bloqueado por safety (promptFeedback)
        fb = data.get("promptFeedback") or {}
        reason = fb.get("blockReason") or "sem candidates"
        raise HTTPException(status_code=502, detail=f"IA não gerou imagem ({reason}).")

    for part in candidates[0].get("content", {}).get("parts", []) or []:
        inline = part.get("inline_data") or part.get("inlineData")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])

    raise HTTPException(
        status_code=502,
        detail="A IA respondeu sem imagem (apenas texto). Refine o prompt e tente novamente.",
    )


# ─── Vídeo (Veo via Gemini API, long-running) ────────────────────────────────

async def start_video(
    *,
    api_key: str,
    model: str,
    prompt: str,
    image_bytes: bytes | None = None,
    aspect: str = "16:9",
    resolution: str = "720p",
) -> str:
    """Inicia a geração de vídeo (image-to-video). Retorna o nome da operação."""
    if not api_key:
        raise HTTPException(status_code=400, detail="Chave de IA de mídia não configurada.")
    instance: dict = {"prompt": (prompt or "")[:1024]}
    if image_bytes:
        # Veo (predictLongRunning) usa bytesBase64Encoded — NÃO inlineData (que é do generateContent).
        instance["image"] = {
            "bytesBase64Encoded": base64.b64encode(image_bytes).decode(),
            "mimeType": "image/jpeg",
        }
    body = {"instances": [instance], "parameters": {"aspectRatio": aspect, "resolution": resolution}}
    url = f"{VEO_BASE}/models/{model}:predictLongRunning"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url, headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=body
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Tempo esgotado ao iniciar o vídeo (IA).") from exc
    if resp.status_code != 200:
        logger.warning("[media-ai] veo start status=%s: %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail=_api_error_detail(resp, "vídeo"))
    name = resp.json().get("name")
    if not name:
        raise HTTPException(status_code=502, detail="Veo não retornou a operação.")
    return name


async def video_status(api_key: str, operation: str) -> dict:
    """Consulta a operação long-running. Retorna {done, uri?} ou {done, error?}."""
    url = f"{VEO_BASE}/{operation}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"x-goog-api-key": api_key})
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Tempo esgotado ao consultar o vídeo.") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar status do vídeo: {resp.status_code}")
    data = resp.json()
    if not data.get("done"):
        return {"done": False}
    if data.get("error"):
        return {"done": True, "error": str(data["error"].get("message", "Falha na geração"))[:400]}
    try:
        sample = data["response"]["generateVideoResponse"]["generatedSamples"][0]
        uri = sample["video"]["uri"]
        return {"done": True, "uri": uri}
    except (KeyError, IndexError, TypeError):
        return {"done": True, "error": "Vídeo não disponível na resposta (possível bloqueio)."}


_GOOGLE_HOST_SUFFIXES = (".googleapis.com", ".googleusercontent.com")


def _video_host_ok(url: str) -> bool:
    """Só https de domínio Google e IP público — chamado a CADA salto de redirect
    para não vazar a x-goog-api-key (que vai no header) para host arbitrário."""
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        return False
    if not p.hostname.endswith(_GOOGLE_HOST_SUFFIXES):
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
    except Exception:
        return False
    return True


async def download_video(api_key: str, uri: str) -> bytes:
    """Baixa o vídeo com limite de tamanho. Segue redirects MANUALMENTE validando
    o host de cada salto (allowlist Google + IP público) antes de reenviar a chave."""
    url = uri
    try:
        async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
            for _ in range(5):
                if not _video_host_ok(url):
                    raise HTTPException(status_code=502, detail="URI de vídeo rejeitada (host não permitido).")
                async with client.stream("GET", url, headers={"x-goog-api-key": api_key}) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise HTTPException(status_code=502, detail="Redirect de vídeo sem destino.")
                        url = loc
                        continue
                    if resp.status_code != 200:
                        raise HTTPException(status_code=502, detail=f"Erro ao baixar vídeo: {resp.status_code}")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            raise HTTPException(status_code=502, detail="Vídeo gerado excede o tamanho máximo.")
                        chunks.append(chunk)
                    return b"".join(chunks)
        raise HTTPException(status_code=502, detail="Muitos redirects ao baixar o vídeo.")
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Tempo esgotado ao baixar o vídeo.") from exc


def upscale_to(image_bytes: bytes, target_long_px: int) -> bytes:
    """Amplia a imagem para que o lado MAIOR tenha pelo menos `target_long_px`,
    preservando a proporção. Se já for >= alvo, retorna como está. Usa Pillow.

    Motivo: o Gemini devolve imagens com ~1024px no lado maior; marketplaces como
    o ML exigem >= 1200px para o zoom funcionar.
    """
    if not target_long_px or target_long_px <= 0:
        return image_bytes
    try:
        from PIL import Image
    except Exception:
        return image_bytes  # Pillow indisponível — devolve original
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        long_side = max(w, h)
        if long_side >= target_long_px:
            return image_bytes
        scale = target_long_px / long_side
        new_size = (round(w * scale), round(h * scale))
        img = img.convert("RGB").resize(new_size, Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92)
        return out.getvalue()
    except Exception as exc:
        logger.warning("[media-ai] upscale falhou: %s", exc)
        return image_bytes

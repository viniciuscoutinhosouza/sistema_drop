"""Upload de imagem raster para /static (avatar do usuário, logo do galpão…).

Ponto único do padrão: valida por MAGIC BYTES (a extensão do nome do usuário é ignorada; SVG é
recusado porque serve inline em /static e viraria XSS), nome com UUID (anti path traversal) e
limpeza do arquivo anterior só DENTRO do diretório-base (anti traversal na remoção)."""
from __future__ import annotations

import os
import uuid as _uuid

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def sniff_image_ext(data: bytes) -> str | None:
    """Extensão real pelo magic byte (não confia na extensão do nome). None se não for jpg/png/webp."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def save_image(data: bytes, base_dir: str, ext: str) -> str:
    """Grava a imagem em `base_dir` com nome UUID; devolve a URL pública (`/base_dir/uuid.ext`)."""
    os.makedirs(base_dir, exist_ok=True)
    filename = f"{_uuid.uuid4().hex}{ext}"
    with open(os.path.join(base_dir, filename), "wb") as out:
        out.write(data)
    return f"/{base_dir}/{filename}"


def delete_upload_file(url: str | None, base_dir: str) -> None:
    """Apaga o arquivo de upload do disco (best-effort). Só toca arquivos dentro de `base_dir`."""
    if not url:
        return
    name = os.path.basename(url)
    path = os.path.join(base_dir, name)
    try:
        if (
            name
            and os.path.commonpath([os.path.abspath(path), os.path.abspath(base_dir)])
            == os.path.abspath(base_dir)
            and os.path.isfile(path)
        ):
            os.remove(path)
    except (OSError, ValueError):
        pass

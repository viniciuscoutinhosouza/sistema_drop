"""Cliente do Google Drive — OAuth2 de usuário + upload de imagens (ADR a criar).

Padrão replicado do projeto MIG (C:/sistemas/MIG): REST puro sobre httpx (sem as libs oficiais
do Google, que trariam ~15 dependências transitivas para 3 chamadas HTTP). Conta GRATUITA exige
OAuth de usuário (Service Account só grava em Shared Drive, que não existe fora do Workspace).

Escopo `drive.file` — acesso só aos arquivos que ESTE sistema cria → NÃO sensível, dispensa a
verificação do app pelo Google. NÃO trocar por `drive`/`drive.readonly`.

⚠️ O app precisa estar PUBLICADO no Console; em modo Testing o refresh_token expira em 7 dias.

Diferenças p/ o Sistema Drop: o refresh_token fica CIFRADO (Fernet, services/crypto); a sessão é
o AsyncSyncSession (await db.execute/commit; db.add síncrono); a raiz é a pasta GOOGLE_DRIVE_ROOT
(`Ecommerce_Imagens`), criada via API ao conectar; subpastas por área são criadas sob ela.
"""
from __future__ import annotations

import io
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from config import get_settings
from models.google_drive import GoogleDriveAccount
from services import crypto

logger = logging.getLogger(__name__)
settings = get_settings()

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

ESCOPO = "https://www.googleapis.com/auth/drive.file"
MIME_PASTA = "application/vnd.google-apps.folder"
TIMEOUT = 30
MARGEM_RENOVACAO = timedelta(seconds=120)


class DriveNaoConfigurado(Exception):
    """GOOGLE_CLIENT_ID/SECRET ausentes no .env do servidor."""


class DriveNaoConectado(Exception):
    """Ninguém autorizou ainda, ou o acesso foi revogado."""


# ── Configuração / conexão ────────────────────────────────────────────────────

def configurado() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def _exigir_config() -> tuple[str, str]:
    if not configurado():
        raise DriveNaoConfigurado(
            "Google Drive não configurado. Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET "
            "no .env do servidor."
        )
    return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET


async def active_account(db) -> GoogleDriveAccount | None:
    return (
        await db.execute(
            select(GoogleDriveAccount)
            .where(GoogleDriveAccount.is_active == 1)
            .order_by(GoogleDriveAccount.id.desc())
        )
    ).scalars().first()


def authorize_url(state: str = "drop") -> str:
    """URL para onde a tela manda o usuário autorizar.

    `access_type=offline` + `prompt=consent` garantem o REFRESH TOKEN (sem eles o Google só
    devolve um access_token de 1h e a conexão morreria no mesmo dia)."""
    client_id, _ = _exigir_config()
    from urllib.parse import urlencode

    return AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": ESCOPO,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })


async def exchange_code(db, code: str, created_by: int | None = None) -> GoogleDriveAccount:
    """Troca o `code` do callback pelo par de tokens e grava a conexão (refresh CIFRADO)."""
    client_id, client_secret = _exigir_config()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    if r.status_code != 200:
        raise DriveNaoConectado(f"Google recusou a autorização: {r.text[:300]}")
    dados = r.json()
    refresh = dados.get("refresh_token")
    if not refresh:
        raise DriveNaoConectado(
            "O Google não devolveu refresh_token. Revogue o acesso em "
            "myaccount.google.com/permissions e autorize novamente."
        )
    email = await _email_do_token(dados.get("access_token"))

    # Desativa conexões anteriores (uma ativa por vez).
    for antiga in (
        await db.execute(select(GoogleDriveAccount).where(GoogleDriveAccount.is_active == 1))
    ).scalars().all():
        antiga.is_active = 0
    await db.flush()

    conta = GoogleDriveAccount(
        email=email,
        refresh_token_enc=crypto.encrypt(refresh),
        access_token=dados.get("access_token"),
        expires_at=datetime.now(UTC) + timedelta(seconds=int(dados.get("expires_in") or 3600)),
        root_folder_name=settings.GOOGLE_DRIVE_ROOT_FOLDER,
        scope=dados.get("scope") or ESCOPO,
        is_active=1,
        created_by=created_by,
    )
    db.add(conta)
    await db.commit()
    await db.refresh(conta)
    logger.info("Google Drive conectado: %s", email)
    return conta


async def _email_do_token(access_token: str | None) -> str | None:
    if not access_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code == 200:
            return r.json().get("email")
    except Exception:
        pass
    return None


async def disconnect(db) -> bool:
    """Revoga o acesso no Google e desativa a conexão local (desativa mesmo se a revogação
    remota falhar — o objetivo é parar de usar, e rede não pode prender o sistema)."""
    conta = await active_account(db)
    if not conta:
        return False
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            await c.post(REVOKE_URL, data={"token": crypto.decrypt(conta.refresh_token_enc)})
    except Exception as e:
        logger.warning("Falha ao revogar no Google (desativando local): %s", e)
    conta.is_active = 0
    await db.commit()
    return True


# ── Token de acesso ────────────────────────────────────────────────────────────

async def access_token(db) -> str:
    """Devolve um access_token válido, renovando pelo refresh quando falta pouco p/ expirar."""
    client_id, client_secret = _exigir_config()
    conta = await active_account(db)
    if not conta:
        raise DriveNaoConectado(
            "Nenhuma conta do Google Drive conectada. Vá em Configurações > Google Drive e "
            "clique em Conectar."
        )
    now = datetime.now(UTC)
    exp = conta.expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if conta.access_token and exp and exp - MARGEM_RENOVACAO > now:
        return conta.access_token

    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(TOKEN_URL, data={
            "refresh_token": crypto.decrypt(conta.refresh_token_enc),
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        })
    if r.status_code != 200:
        conta.last_error = f"Renovação falhou: {r.text[:400]}"
        await db.commit()
        if "invalid_grant" in r.text:
            raise DriveNaoConectado(
                "O acesso ao Google Drive expirou ou foi revogado. Reconecte em Configurações > "
                "Google Drive. Se isso se repetir toda semana, o app não foi PUBLICADO no Console."
            )
        raise DriveNaoConectado(f"Não foi possível renovar o acesso: {r.text[:200]}")
    dados = r.json()
    conta.access_token = dados.get("access_token")
    conta.expires_at = now + timedelta(seconds=int(dados.get("expires_in") or 3600))
    conta.last_used_at = now
    conta.last_error = None
    await db.commit()
    return conta.access_token


async def _headers(db) -> dict:
    return {"Authorization": f"Bearer {await access_token(db)}"}


# ── Pastas (raiz Ecommerce_Imagens + subpastas por área) ───────────────────────

async def ensure_folder(db, nome: str, parent_id: str | None = None) -> str:
    """Devolve o id da pasta, criando-a se não existir. Idempotente por (nome, pai)."""
    headers = await _headers(db)
    nome_escapado = nome.replace("'", r"\'")
    q = f"name = '{nome_escapado}' and mimeType = '{MIME_PASTA}' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{API}/files", headers=headers,
                        params={"q": q, "fields": "files(id,name)", "pageSize": 1})
        if r.status_code == 200 and r.json().get("files"):
            return r.json()["files"][0]["id"]
        corpo: dict = {"name": nome, "mimeType": MIME_PASTA}
        if parent_id:
            corpo["parents"] = [parent_id]
        r = await c.post(f"{API}/files", headers=headers, json=corpo, params={"fields": "id"})
    if r.status_code not in (200, 201):
        raise DriveNaoConectado(f"Falha ao criar a pasta {nome!r}: {r.text[:200]}")
    return r.json()["id"]


async def ensure_root(db) -> str:
    """Garante a pasta raiz (`Ecommerce_Imagens`) e memoriza o id na conexão."""
    conta = await active_account(db)
    if not conta:
        raise DriveNaoConectado("Conecte o Google Drive primeiro.")
    if conta.root_folder_id:
        return conta.root_folder_id
    nome = conta.root_folder_name or settings.GOOGLE_DRIVE_ROOT_FOLDER
    fid = await ensure_folder(db, nome, parent_id=None)
    conta.root_folder_id = fid
    conta.root_folder_name = nome
    await db.commit()
    return fid


async def folder_for_area(db, area: str | None) -> str:
    """Id da subpasta da área (ex.: 'Separacao') sob a raiz. Sem área → a própria raiz."""
    root = await ensure_root(db)
    if not area:
        return root
    return await ensure_folder(db, area, parent_id=root)


# ── Upload / download / exclusão ────────────────────────────────────────────────

async def upload(db, conteudo: bytes, nome: str, mime: str, area: str | None = None) -> dict:
    """Envia o arquivo (multipart) para a subpasta da área. Devolve id/nome/tamanho/link."""
    pasta = await folder_for_area(db, area)
    headers = await _headers(db)
    import json as _json

    files = {
        "metadata": ("metadata", _json.dumps({"name": nome, "parents": [pasta]}),
                     "application/json; charset=UTF-8"),
        "file": (nome, io.BytesIO(conteudo), mime or "application/octet-stream"),
    }
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{UPLOAD_API}/files", headers=headers,
                         params={"uploadType": "multipart", "fields": "id,name,size,webViewLink"},
                         files=files)
    if r.status_code not in (200, 201):
        if r.status_code == 403 and "storageQuota" in r.text:
            raise DriveNaoConectado("O espaço do Google Drive acabou. Libere arquivos ou contrate o Google One.")
        raise DriveNaoConectado(f"Falha ao enviar {nome!r}: {r.text[:300]}")
    d = r.json()
    return {
        "id": d.get("id"),
        "nome": d.get("name"),
        "tamanho": int(d.get("size") or len(conteudo)),
        "link": d.get("webViewLink"),
    }


async def download(db, file_id: str) -> bytes:
    """Baixa o conteúdo — usado para SERVIR o arquivo pelo sistema (sem expor o Drive)."""
    headers = await _headers(db)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(f"{API}/files/{file_id}", headers=headers, params={"alt": "media"})
    if r.status_code != 200:
        raise DriveNaoConectado(f"Falha ao baixar do Drive: {r.text[:200]}")
    return r.content


async def delete(db, file_id: str) -> bool:
    """Move o arquivo para a lixeira do Drive (recuperável por 30 dias)."""
    headers = await _headers(db)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.patch(f"{API}/files/{file_id}", headers=headers, json={"trashed": True})
    if r.status_code == 404:
        return False
    if r.status_code not in (200, 204):
        raise DriveNaoConectado(f"Falha ao excluir no Drive: {r.text[:200]}")
    return True


async def quota(db) -> dict:
    """Espaço usado/disponível da conta (15 GB grátis são COMPARTILHADOS com Gmail/Fotos)."""
    headers = await _headers(db)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{API}/about", headers=headers, params={"fields": "storageQuota,user"})
    if r.status_code != 200:
        raise DriveNaoConectado(f"Falha ao consultar a cota: {r.text[:200]}")
    d = r.json()
    q = d.get("storageQuota", {})
    limite = int(q.get("limit") or 0)
    usado = int(q.get("usage") or 0)
    return {
        "email": (d.get("user") or {}).get("emailAddress"),
        "limite_bytes": limite,
        "usado_bytes": usado,
        "limite_gb": round(limite / 1024 ** 3, 2) if limite else None,
        "usado_gb": round(usado / 1024 ** 3, 2),
        "percentual": round(usado / limite * 100, 1) if limite else None,
        "alerta": bool(limite and usado / limite >= 0.8),
    }

"""Bling ERP (API v3) — integração por CMIG via OAuth 2.0.

Cada CMIG conecta a SUA conta Bling (o Bling é o ERP da empresa, não um canal de venda). Molde:
integração Google Drive (ADR-0038) — tokens CIFRADOS em repouso (Fernet, `services/crypto`), tabela
dedicada (`cmig_bling_accounts`, UMA por CMIG), renovação pelo refresh. Ver skill `bling-api`.

Fluxo OAuth (Authorization Code):
  authorize_url(state) → usuário autoriza no Bling → callback com ?code=&state=
  exchange_code(db, code, cmig_id) troca o code (Basic auth, server-side) e faz UPSERT da conexão
  get_valid_token(db, cmig_id) devolve um access_token válido (refresh SOB LOCK por-CMIG)

⚠️ O `code` do Bling expira em 30s; o refresh_token dura ~30 dias e ROTACIONA a cada refresh (por
isso o refresh grava o novo par). O Bling migra token opaco → JWT: tokens podem ser grandes (CLOB).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from config import get_settings
from models.bling import CMIGBlingAccount
from services import crypto

logger = logging.getLogger(__name__)
settings = get_settings()

# Host de autorização (tela de consentimento) e de token. A API de recursos (v3) é api.bling.com.br.
AUTH_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
REVOKE_URL = "https://www.bling.com.br/Api/v3/oauth/revoke"
API_BASE = "https://api.bling.com.br/Api/v3"

TIMEOUT = 30
MARGEM_RENOVACAO = timedelta(seconds=120)   # renova quando falta < 2 min p/ expirar
STATE_TTL_SECONDS = 900                      # o state (CSRF + cmig_id) vale 15 min
# Escopos do roadmap (catálogo). O Bling usa os escopos do CADASTRO do app; mandamos por cortesia.
ESCOPO_PADRAO = ""

# Throttle conservador: o Bling limita ~3 req/s por conta. Para a Fase 1 (conexão) as chamadas são
# esparsas; um intervalo mínimo por-processo já protege. Refinar p/ token-bucket por-CMIG nas fases
# de sincronização.
_MIN_INTERVALO = 1.0 / 3.0
_ultimo_call = 0.0
_throttle_lock = asyncio.Lock()
# Lock de refresh POR CMIG (não global — não serializa CMIGs distintas).
_refresh_locks: dict[int, asyncio.Lock] = {}


class BlingNaoConfigurado(Exception):
    """BLING_CLIENT_ID/SECRET ausentes no .env do servidor."""


class BlingNaoConectado(Exception):
    """A CMIG não autorizou ainda, ou o acesso expirou/foi revogado."""


# ── Configuração ──────────────────────────────────────────────────────────────

def configurado() -> bool:
    return bool(settings.BLING_CLIENT_ID and settings.BLING_CLIENT_SECRET)


def _exigir_config() -> tuple[str, str]:
    if not configurado():
        raise BlingNaoConfigurado(
            "Bling não configurado. Defina BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env do servidor."
        )
    return settings.BLING_CLIENT_ID, settings.BLING_CLIENT_SECRET


def _basic_auth_header() -> str:
    cid, secret = _exigir_config()
    raw = f"{cid}:{secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


# ── State (anti-CSRF + carrega o cmig_id para o callback, que não tem login) ────

def encode_state(cmig_id: int, user_id: int | None = None) -> str:
    """Cifra {cmig_id, user_id, nonce, ts} (Fernet) — o callback (sem login) decifra e extrai o
    cmig_id SEM confiar no path (anti-IDOR). Fernet já é base64 URL-safe → serve como query param."""
    import secrets as _secrets

    payload = json.dumps({
        "cmig_id": int(cmig_id),
        "user_id": int(user_id) if user_id else None,
        "nonce": _secrets.token_hex(8),
        "ts": int(time.time()),
    })
    return crypto.encrypt(payload)


def decode_state(state: str) -> dict:
    """Valida/decifra o state e devolve {cmig_id, user_id}. Rejeita adulterado ou expirado."""
    try:
        payload = json.loads(crypto.decrypt(state))
    except Exception as e:  # noqa: BLE001 — adulterado/ilegível
        raise BlingNaoConectado("Parâmetro de segurança (state) inválido.") from e
    ts = int(payload.get("ts") or 0)
    if ts <= 0 or (time.time() - ts) > STATE_TTL_SECONDS:
        raise BlingNaoConectado("A autorização expirou (state vencido). Tente conectar novamente.")
    cmig_id = payload.get("cmig_id")
    if not isinstance(cmig_id, int):
        raise BlingNaoConectado("Parâmetro de segurança (state) inválido.")
    return {"cmig_id": cmig_id, "user_id": payload.get("user_id")}


# ── Conexão (por CMIG) ──────────────────────────────────────────────────────────

async def active_account(db, cmig_id: int) -> CMIGBlingAccount | None:
    return (
        await db.execute(
            select(CMIGBlingAccount).where(CMIGBlingAccount.cmig_id == cmig_id)
        )
    ).scalar_one_or_none()


def authorize_url(state: str) -> str:
    """URL de consentimento do Bling para onde a tela manda o usuário."""
    cid, _ = _exigir_config()
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": cid,
        "state": state,
        "redirect_uri": settings.BLING_REDIRECT_URI,
    }
    if ESCOPO_PADRAO:
        params["scope"] = ESCOPO_PADRAO
    return AUTH_URL + "?" + urlencode(params)


async def exchange_code(db, code: str, cmig_id: int, connected_by: int | None = None) -> CMIGBlingAccount:
    """Troca o `code` do callback pelos tokens (Basic auth, server-side) e faz UPSERT da conexão da
    CMIG (UMA por CMIG — reconexão atualiza a linha, não cria 2ª)."""
    _exigir_config()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"grant_type": "authorization_code", "code": code},
        )
    if r.status_code != 200:
        raise BlingNaoConectado(f"O Bling recusou a autorização: {r.text[:300]}")
    dados = r.json()
    access = dados.get("access_token")
    refresh = dados.get("refresh_token")
    if not access or not refresh:
        raise BlingNaoConectado("O Bling não devolveu os tokens esperados (access/refresh).")
    expires_at = datetime.now(UTC) + timedelta(seconds=int(dados.get("expires_in") or 21600))

    conta = await active_account(db, cmig_id)
    if conta is None:
        conta = CMIGBlingAccount(cmig_id=cmig_id, connected_by_user_id=connected_by)
        db.add(conta)
    conta.access_token_enc = crypto.encrypt(access)
    conta.refresh_token_enc = crypto.encrypt(refresh)
    conta.token_expires_at = expires_at
    conta.scope = dados.get("scope") or ESCOPO_PADRAO or None
    conta.connected_at = datetime.now(UTC)
    conta.last_error = None
    if connected_by and not conta.connected_by_user_id:
        conta.connected_by_user_id = connected_by
    await db.flush()
    # Best-effort: já busca a empresa Bling para exibir o nome na tela (não derruba a conexão).
    try:
        emp = await _fetch_empresa(crypto.decrypt(conta.access_token_enc))
        if emp:
            conta.bling_company_id = emp.get("id")
            conta.bling_company_name = emp.get("nome")
    except Exception as e:  # noqa: BLE001
        logger.warning("Bling: empresa não lida no connect (cmig=%s): %s", cmig_id, e)
    await db.commit()
    await db.refresh(conta)
    logger.info("Bling conectado para CMIG %s (empresa=%s)", cmig_id, conta.bling_company_name)
    return conta


async def disconnect(db, cmig_id: int) -> bool:
    """Revoga no Bling (best-effort) e remove a conexão local. Remove SEMPRE mesmo se a revogação
    remota falhar (o objetivo é parar de usar; rede não pode prender o sistema)."""
    conta = await active_account(db, cmig_id)
    if not conta:
        return False
    if conta.refresh_token_enc:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                await c.post(
                    REVOKE_URL,
                    headers={"Authorization": _basic_auth_header()},
                    data={"token": crypto.decrypt(conta.refresh_token_enc), "token_type_hint": "refresh_token"},
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Bling: falha ao revogar (removendo local) cmig=%s: %s", cmig_id, e)
    db.delete(conta)
    await db.commit()
    return True


# ── Token válido (refresh sob lock por-CMIG) ────────────────────────────────────

def _lock_for(cmig_id: int) -> asyncio.Lock:
    lock = _refresh_locks.get(cmig_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[cmig_id] = lock
    return lock


async def get_valid_token(db, cmig_id: int) -> str:
    """access_token válido da CMIG, renovando pelo refresh quando falta pouco p/ expirar."""
    _exigir_config()
    conta = await active_account(db, cmig_id)
    if not conta or not conta.refresh_token_enc:
        raise BlingNaoConectado("Esta CMIG não está conectada ao Bling. Conecte na tela da CMIG.")
    now = datetime.now(UTC)
    exp = conta.token_expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if conta.access_token_enc and exp and exp - MARGEM_RENOVACAO > now:
        try:
            return crypto.decrypt(conta.access_token_enc)
        except Exception:  # noqa: BLE001 — cifrado corrompido → renova
            pass
    async with _lock_for(cmig_id):
        # Re-checa dentro do lock: outra corrotina pode ter renovado enquanto esperávamos.
        conta = await active_account(db, cmig_id)
        if not conta or not conta.refresh_token_enc:
            raise BlingNaoConectado("Esta CMIG não está conectada ao Bling.")
        exp = conta.token_expires_at
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if conta.access_token_enc and exp and exp - MARGEM_RENOVACAO > datetime.now(UTC):
            try:
                return crypto.decrypt(conta.access_token_enc)
            except Exception:  # noqa: BLE001
                pass
        return await _refresh(db, conta)


async def _refresh(db, conta: CMIGBlingAccount) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"grant_type": "refresh_token", "refresh_token": crypto.decrypt(conta.refresh_token_enc)},
        )
    if r.status_code != 200:
        conta.last_error = f"Renovação falhou: {r.text[:400]}"
        await db.commit()
        if "invalid_grant" in r.text:
            raise BlingNaoConectado(
                "O acesso ao Bling expirou ou foi revogado (refresh de 30 dias). Reconecte a CMIG."
            )
        raise BlingNaoConectado(f"Não foi possível renovar o acesso ao Bling: {r.text[:200]}")
    dados = r.json()
    access = dados.get("access_token")
    refresh = dados.get("refresh_token")  # ROTACIONA — persistir o novo
    if not access:
        raise BlingNaoConectado("O Bling não devolveu um novo access_token na renovação.")
    conta.access_token_enc = crypto.encrypt(access)
    if refresh:
        conta.refresh_token_enc = crypto.encrypt(refresh)
    conta.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(dados.get("expires_in") or 21600))
    conta.last_used_at = datetime.now(UTC)
    conta.last_error = None
    await db.commit()
    return access


# ── Chamadas à API (throttle + retry + 401→refresh→replay) ──────────────────────

async def _throttle() -> None:
    global _ultimo_call
    async with _throttle_lock:
        espera = _MIN_INTERVALO - (time.monotonic() - _ultimo_call)
        if espera > 0:
            await asyncio.sleep(espera)
        _ultimo_call = time.monotonic()


async def _fetch_empresa(access_token: str) -> dict | None:
    """GET /empresas — usado p/ smoke e p/ nome da empresa. Tolerante à forma do retorno."""
    await _throttle()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{API_BASE}/empresas", headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        return None
    body = r.json()
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None


async def company_info(db, cmig_id: int) -> dict | None:
    """Prova de ponta a ponta p/ o /test: token válido + GET /empresas."""
    token = await get_valid_token(db, cmig_id)
    return await _fetch_empresa(token)


async def request(db, cmig_id: int, method: str, path: str, *, params=None, json_body=None, _retry=True):
    """Chamada autenticada à API do Bling (throttle + refresh em 401 + retry em 429/5xx).

    `path` começa com '/'. Devolve o JSON (ou levanta HTTPException para o router propagar)."""
    await _throttle()
    token = await get_valid_token(db, cmig_id)
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.request(
            method, url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params, json=json_body,
        )
    if r.status_code == 401 and _retry:
        # token pode ter virado inválido antes de expirar → força refresh (SOB LOCK por-CMIG: o
        # refresh do Bling rotaciona o refresh_token; dois refresh concorrentes invalidariam a
        # conexão). Re-check dentro do lock: se outra corrotina já renovou, não renova de novo.
        async with _lock_for(cmig_id):
            conta = await active_account(db, cmig_id)
            if conta and conta.refresh_token_enc:
                exp = conta.token_expires_at
                if exp is not None and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=UTC)
                ja_renovado = bool(conta.access_token_enc and exp and exp - MARGEM_RENOVACAO > datetime.now(UTC))
                if not ja_renovado:
                    await _refresh(db, conta)
        return await request(db, cmig_id, method, path, params=params, json_body=json_body, _retry=False)
    if r.status_code == 429 and _retry:
        await asyncio.sleep(1.0)
        return await request(db, cmig_id, method, path, params=params, json_body=json_body, _retry=False)
    if r.status_code >= 400:
        raise HTTPException(status_code=502 if r.status_code >= 500 else r.status_code,
                            detail=f"Bling {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


# ── LEGADO (DEPRECADO) ──────────────────────────────────────────────────────────
# Bling v1/v2 por "API key" estática. Ainda referenciado por routers/integrations.py
# (POST /accounts/{id}/bling/connect). NÃO usar em código novo — a conexão v3 é por CMIG via OAuth
# (acima). Mantido só para não quebrar o endpoint legado; candidato a remoção numa limpeza futura.

BLING_API_BASE = "https://www.bling.com.br/Api/v3"  # legado


async def validate_api_key(api_key: str) -> dict:
    """[DEPRECADO] Valida uma API key estática (fluxo antigo). Prefira o OAuth por CMIG."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BLING_API_BASE}/empresas",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Chave API Bling inválida")
    return resp.json()


async def sync_product(api_key: str, product_data: dict) -> dict:
    """[DEPRECADO] Cria/atualiza produto via API key estática. Prefira o OAuth por CMIG."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BLING_API_BASE}/produtos",
            headers={"Authorization": f"Bearer {api_key}"},
            json=product_data,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Erro ao sincronizar produto Bling: {resp.text}")
    return resp.json()

"""Cliente da API ASAAS (gateway de pagamento) — Fase 2 (ADR-0032).

Cada Galpão tem sua conta ASAAS (conta de recebimento `is_primary`), com API Key cifrada
(services/crypto). Aqui resolvemos a conta, decifrámos a key e falamos com o ASAAS:
  base sandbox  https://api-sandbox.asaas.com/v3
  base produção https://api.asaas.com/v3
  auth: header `access_token: <API_KEY>`

Falha alto (AsaasError) em: sem conta principal, master key ausente, key inválida, erro do ASAAS.
Os endpoints mapeiam AsaasError → 400/409/502 (nunca 500 silencioso).
"""

import hashlib
import secrets

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.warehouse import WarehouseBankAccount
from services import crypto

_SANDBOX_BASE = "https://api-sandbox.asaas.com/v3"
_PROD_BASE = "https://api.asaas.com/v3"
_TIMEOUT = 20.0


class AsaasError(Exception):
    """Falha de configuração/comunicação com o ASAAS (mapeada para HTTP no router)."""


def token_hash(token: str) -> str:
    """SHA-256 (hex) do authToken — o que guardamos (nunca o token em claro)."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _base_url(bank: WarehouseBankAccount) -> str:
    return _SANDBOX_BASE if bank.is_sandbox else _PROD_BASE


def _api_key(bank: WarehouseBankAccount) -> str:
    if not bank.api_key_encrypted:
        raise AsaasError("Conta sem API Key do ASAAS cadastrada.")
    try:
        return crypto.decrypt(bank.api_key_encrypted)
    except crypto.CryptoError as e:
        raise AsaasError(f"Não foi possível decifrar a API Key: {e}") from e


def _headers(bank: WarehouseBankAccount) -> dict:
    return {"access_token": _api_key(bank), "Content-Type": "application/json"}


async def resolve_primary_bank(db: AsyncSession, warehouse_id: int) -> WarehouseBankAccount:
    """Conta de recebimento ASAAS principal e ativa do galpão. 409 (AsaasError) se não houver."""
    bank = (
        await db.execute(
            select(WarehouseBankAccount)
            .where(
                WarehouseBankAccount.warehouse_id == warehouse_id,
                WarehouseBankAccount.provider == "asaas",
                WarehouseBankAccount.is_active == True,  # noqa: E712
                WarehouseBankAccount.is_primary == True,  # noqa: E712
            )
            .order_by(WarehouseBankAccount.id)
        )
    ).scalars().first()
    if not bank:
        raise AsaasError(
            "O Galpão não tem conta de recebimento ASAAS principal e ativa configurada."
        )
    return bank


async def _request(bank, method: str, path: str, *, json_body=None, params=None) -> dict:
    url = f"{_base_url(bank)}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                method, url, headers=_headers(bank), json=json_body, params=params
            )
    except httpx.HTTPError as e:
        raise AsaasError(f"Falha de comunicação com o ASAAS: {e}") from e
    if resp.status_code in (401, 403):
        raise AsaasError("ASAAS recusou a API Key (não autorizado) — confira a chave da conta.")
    if resp.status_code >= 400:
        detail = resp.text[:400]
        try:
            body = resp.json()
            if isinstance(body, dict) and body.get("errors"):
                detail = "; ".join(err.get("description", "") for err in body["errors"])[:400]
        except Exception:
            pass
        raise AsaasError(f"ASAAS retornou erro {resp.status_code}: {detail}")
    try:
        return resp.json()
    except Exception:
        return {}


async def test_connection(bank: WarehouseBankAccount) -> dict:
    """Valida a API Key (GET /myAccount). Devolve dados básicos da conta ou levanta AsaasError."""
    data = await _request(bank, "GET", "/myAccount")
    return {
        "ok": True,
        "name": data.get("name") or data.get("companyName"),
        "email": data.get("email"),
        "sandbox": bool(bank.is_sandbox),
    }


async def ensure_webhook(bank: WarehouseBankAccount, webhook_url: str) -> str:
    """Registra no ASAAS o webhook desta conta apontando para `webhook_url`, com um authToken
    gerado por nós (alta entropia). Retorna o token em CLARO (o chamador guarda só o hash).

    IDEMPOTENTE: antes de criar, remove TODO webhook já existente desta conta que aponte para a
    mesma URL. Sem isso, reconfigurar deixaria 2+ webhooks com authTokens distintos — e como só
    guardamos o hash do último, os antigos entregariam com token velho e tomariam 401 para sempre
    (tempestade de retries no ASAAS). Garante exatamente um webhook por URL.
    """
    try:
        existing = await _request(bank, "GET", "/webhooks")
        for w in existing.get("data") or []:
            if w.get("url") == webhook_url and w.get("id"):
                try:
                    await _request(bank, "DELETE", f"/webhooks/{w['id']}")
                except AsaasError:
                    pass  # best-effort: seguimos para recriar
    except AsaasError:
        pass  # conta sem listagem de webhooks ainda — só cria

    # A API nova do ASAAS exige `email` no webhook (p/ avisar falhas de entrega). NÃO precisa ser
    # cadastrado no sistema — usamos o e-mail da PRÓPRIA conta ASAAS (GET /myAccount).
    email = None
    try:
        acc = await _request(bank, "GET", "/myAccount")
        email = acc.get("email")
    except AsaasError:
        pass
    if not email:
        raise AsaasError(
            "Não foi possível obter o e-mail da conta ASAAS (GET /myAccount). Verifique se a API "
            "Key é válida e se a conta tem e-mail cadastrado no ASAAS."
        )

    token = secrets.token_urlsafe(32)  # ~43 chars, dentro de 32-255 do ASAAS
    body = {
        "name": "Sistema Drop - pagamentos",
        "url": webhook_url,
        "email": email,
        "enabled": True,
        "interrupted": False,
        "authToken": token,
        "sendType": "SEQUENTIALLY",
        "events": ["PAYMENT_CONFIRMED", "PAYMENT_RECEIVED", "PAYMENT_OVERDUE", "PAYMENT_REFUNDED"],
    }
    await _request(bank, "POST", "/webhooks", json_body=body)
    return token


async def upsert_customer(bank: WarehouseBankAccount, person: dict) -> str:
    """Acha (por CPF/CNPJ) ou cria o cliente no ASAAS. Retorna o id do cliente ASAAS."""
    doc = "".join(c for c in (person.get("document") or "") if c.isdigit())
    if not doc:
        raise AsaasError("Cliente sem CPF/CNPJ — necessário para a cobrança.")
    found = await _request(bank, "GET", "/customers", params={"cpfCnpj": doc})
    items = found.get("data") or []
    if items:
        return items[0].get("id")
    created = await _request(
        bank,
        "POST",
        "/customers",
        json_body={
            "name": person.get("name") or "Cliente",
            "cpfCnpj": doc,
            "email": person.get("email") or None,
            "phone": person.get("phone") or None,
        },
    )
    cid = created.get("id")
    if not cid:
        raise AsaasError("ASAAS não retornou o id do cliente.")
    return cid


async def create_payment(bank: WarehouseBankAccount, payload: dict) -> dict:
    """Cria a cobrança (POST /payments). `payload`: customer, billingType, value, dueDate,
    description, externalReference. Devolve o dict do ASAAS (id, invoiceUrl, bankSlipUrl, status)."""
    data = await _request(bank, "POST", "/payments", json_body=payload)
    if not data.get("id"):
        raise AsaasError("ASAAS não retornou o id da cobrança.")
    return data


async def get_pix_qr(bank: WarehouseBankAccount, payment_id: str) -> dict:
    """QR/copia-e-cola do Pix da cobrança (best-effort — vazio se não aplicável)."""
    try:
        return await _request(bank, "GET", f"/payments/{payment_id}/pixQrCode")
    except AsaasError:
        return {}


async def get_payment(bank: WarehouseBankAccount, payment_id: str) -> dict:
    """Estado atual da cobrança no ASAAS (para reconciliar status)."""
    return await _request(bank, "GET", f"/payments/{payment_id}")


async def cancel_payment(bank: WarehouseBankAccount, payment_id: str) -> dict:
    """Cancela/remove a cobrança no ASAAS (DELETE /payments/{id}).

    Usado quando o operador gerou uma cobrança com valor/forma errados — o desenho reentrante
    reusa a cobrança viva, então sem cancelar ficaria preso a ela. Devolve {deleted: bool}.
    """
    return await _request(bank, "DELETE", f"/payments/{payment_id}")

"""Testes da integração Bling (OAuth2 por CMIG). Funções puras + upsert da conexão.

O fluxo HTTP real (troca de code/refresh contra o Bling) é validado ponta a ponta em produção com
credenciais reais — aqui cobrimos o que é crítico e testável sem rede: state (anti-IDOR/frescor),
Basic auth, montagem da URL de autorização, config, e o UPSERT (reconexão não cria 2ª linha).
"""
import os

# Precisam existir ANTES de montar o Settings (cifragem do state usa NFE_CERT_MASTER_KEY).
os.environ.setdefault("NFE_CERT_MASTER_KEY", "bling-test-master-key-0123456789abcdef")
os.environ.setdefault("BLING_CLIENT_ID", "test_client_id")
os.environ.setdefault("BLING_CLIENT_SECRET", "test_client_secret")

import base64

import pytest

from config import get_settings

get_settings.cache_clear()  # releitura do env com as chaves do Bling/cifragem

from models.bling import CMIGBlingAccount  # noqa: E402
from services import bling_service as bling  # noqa: E402

bling.settings = get_settings()  # o módulo capturou settings no import — realinha com o env do teste


def test_configurado_true():
    assert bling.configurado() is True


def test_basic_auth_header_format():
    h = bling._basic_auth_header()
    assert h.startswith("Basic ")
    raw = base64.b64decode(h[len("Basic "):]).decode()
    assert raw == "test_client_id:test_client_secret"


def test_authorize_url_carrega_params():
    url = bling.authorize_url("STATE123")
    assert bling.AUTH_URL in url
    assert "response_type=code" in url
    assert "client_id=test_client_id" in url
    assert "state=STATE123" in url
    # redirect_uri vai urlencoded
    assert "redirect_uri=" in url


def test_state_roundtrip_carrega_cmig_e_user():
    s = bling.encode_state(7, user_id=42)
    out = bling.decode_state(s)
    assert out["cmig_id"] == 7
    assert out["user_id"] == 42


def test_state_adulterado_rejeitado():
    s = bling.encode_state(7)
    i = len(s) // 2
    trocado = "A" if s[i] != "A" else "B"
    tampered = s[:i] + trocado + s[i + 1:]  # flip no meio → HMAC do Fernet falha
    with pytest.raises(bling.BlingNaoConectado):
        bling.decode_state(tampered)


def test_state_de_outra_origem_rejeitado():
    with pytest.raises(bling.BlingNaoConectado):
        bling.decode_state("nao-e-um-state-valido")


def test_state_expirado_rejeitado(monkeypatch):
    s = bling.encode_state(7)
    agora = bling.time.time()
    monkeypatch.setattr(bling.time, "time", lambda: agora + bling.STATE_TTL_SECONDS + 10)
    with pytest.raises(bling.BlingNaoConectado):
        bling.decode_state(s)


def test_nao_configurado(monkeypatch):
    monkeypatch.setattr(bling.settings, "BLING_CLIENT_ID", "")
    assert bling.configurado() is False
    with pytest.raises(bling.BlingNaoConfigurado):
        bling._exigir_config()


# ── UPSERT da conexão (auditoria item 3: UNIQUE(cmig_id) → reconexão atualiza, não duplica) ──

class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


class _FakeClient:
    """Fake httpx.AsyncClient: devolve um token fixo no POST e nada no resto."""
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        return _Resp(200, {
            "access_token": "AT-xyz", "refresh_token": "RT-xyz",
            "expires_in": 21600, "scope": "produtos",
        })


@pytest.mark.asyncio
async def test_exchange_code_upsert(monkeypatch, mock_db):
    # sem GET /empresas (evita rede): a leitura da empresa é best-effort
    async def _no_empresa(_token):
        return None
    monkeypatch.setattr(bling, "_fetch_empresa", _no_empresa)
    monkeypatch.setattr(bling.httpx, "AsyncClient", _FakeClient)

    # 1ª conexão: active_account retorna None → cria linha nova
    mock_db.set_result(None)
    conta = await bling.exchange_code(mock_db, "CODE1", cmig_id=5, connected_by=9)
    assert conta.cmig_id == 5
    assert conta.access_token_enc and conta.access_token_enc != "AT-xyz"   # cifrado
    assert conta.refresh_token_enc and conta.refresh_token_enc != "RT-xyz"
    assert mock_db.added and mock_db.committed
    # os tokens decifram de volta
    from services import crypto
    assert crypto.decrypt(conta.access_token_enc) == "AT-xyz"

    # reconexão: active_account retorna a MESMA linha → UPDATE in-place (não adiciona outra)
    mock_db.reset()
    mock_db.set_result(conta)
    conta2 = await bling.exchange_code(mock_db, "CODE2", cmig_id=5, connected_by=9)
    assert conta2 is conta                 # mesma linha, atualizada
    assert mock_db.added == []             # NÃO criou 2ª linha

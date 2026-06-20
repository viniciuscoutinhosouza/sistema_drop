"""API local do coletor — roda na máquina Windows (IP residencial), na .venv-camoufox.

O backend (servidor Oracle) chama esta API para obter a busca livre do ML que a
API oficial bloqueou. Esta API roda o Camoufox LOCALMENTE e devolve os itens.

⚠️ Reachability: o servidor Oracle precisa ALCANÇAR esta API. Como a máquina local
costuma ficar atrás de NAT/CGNAT, exponha via túnel (Cloudflare Tunnel/ngrok) ou
port-forward + DDNS. O túnel carrega só o tráfego de controle; o Camoufox continua
saindo pelo IP residencial. A URL pública do túnel vai em COLLECTOR_API_URL no
`.env` do backend.

Rodar:
    .venv-camoufox\\Scripts\\python.exe -m uvicorn tools.collector.collector_api:app --host 0.0.0.0 --port 8777
ou:
    .venv-camoufox\\Scripts\\python.exe tools\\collector\\collector_api.py
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

# Permite importar plugins_src._shared.* e tools.collector.* rodando da raiz.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402

from tools.collector.config import config  # noqa: E402

# A coleta roda em SUBPROCESSO (ml_search.py): o Playwright sync do Camoufox NÃO
# pode rodar dentro do event loop do uvicorn. O subprocesso tem interpretador
# próprio, sem event loop, e isola crashes do browser da API.
_ML_SEARCH = _REPO_ROOT / "tools" / "collector" / "ml_search.py"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("collector_api")

app = FastAPI(title="Sistema Drop — Coletor ML local", version="1.0.0")

# Camoufox/Playwright sync API bloqueia: um navegador por vez.
_BROWSER_LOCK = asyncio.Lock()
# Janela deslizante de timestamps p/ rate limit (anti-DoS / protege o IP residencial).
_RATE_HITS: deque[float] = deque()


async def require_token(authorization: str = Header(default="")) -> None:
    """Autentica via Bearer token compartilhado (padrão webhook do projeto: secret, não usuário)."""
    if not config.API_TOKEN:
        raise HTTPException(status_code=503, detail="COLLECTOR_API_TOKEN não configurado no .env")
    expected = f"Bearer {config.API_TOKEN}"
    # Comparação em tempo constante (evita timing attack — quality-guardian CRITICAL-2).
    if not hmac.compare_digest((authorization or "").strip(), expected):
        raise HTTPException(status_code=401, detail="token inválido")


def _check_rate_limit() -> None:
    """Janela deslizante: rejeita se exceder RATE_MAX coletas em RATE_WINDOW_S."""
    now = time.monotonic()
    while _RATE_HITS and (now - _RATE_HITS[0]) > config.RATE_WINDOW_S:
        _RATE_HITS.popleft()
    if len(_RATE_HITS) >= config.RATE_MAX:
        raise HTTPException(status_code=429, detail="rate limit excedido, tente mais tarde")
    _RATE_HITS.append(now)


async def _run_collect_subprocess(query: str, limit: int, headless: bool) -> dict:
    """Roda ml_search.py como subprocesso e lê o JSON do resultado.

    Necessário porque o Playwright sync do Camoufox não roda dentro do event loop
    do uvicorn. O subprocesso tem interpretador próprio (sem loop) e isola o browser.
    """
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="ml_collect_")
    os.close(fd)
    args = [sys.executable, str(_ML_SEARCH), query,
            "--limit", str(limit), "--result-file", tmp]
    if headless:
        args.append("--headless")
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=str(_REPO_ROOT),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=config.SUBPROCESS_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise HTTPException(status_code=504, detail="coleta excedeu o tempo limite") from None

        if not Path(tmp).exists() or Path(tmp).stat().st_size == 0:
            tail = (out or b"").decode("utf-8", "replace")[-400:]
            raise HTTPException(status_code=500, detail=f"coleta não produziu resultado: {tail}")

        return json.loads(Path(tmp).read_text(encoding="utf-8"))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ml-collector", "headless_default": config.DEFAULT_HEADLESS}


@app.post("/collect", dependencies=[Depends(require_token)])
async def collect_endpoint(body: dict) -> dict:
    """Recebe {query, limit?, headless?} → roda Camoufox local → devolve itens raspados."""
    query = (body or {}).get("query") or ""
    query = str(query).strip()
    if not query:
        raise HTTPException(status_code=422, detail="campo 'query' é obrigatório")

    try:
        limit = int((body or {}).get("limit") or config.DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="'limit' deve ser inteiro") from None
    limit = max(1, min(limit, config.MAX_LIMIT))
    headless = bool((body or {}).get("headless", config.DEFAULT_HEADLESS))

    # Rate limit + recusa rápida se já há coleta em andamento (evita fila travando no lock).
    _check_rate_limit()
    if _BROWSER_LOCK.locked():
        raise HTTPException(status_code=429, detail="coleta em andamento, tente novamente em instantes")

    logger.info("collect query=%r limit=%s headless=%s", query, limit, headless)

    # Serializa o navegador (um por vez) e roda em subprocesso (fora do event loop).
    async with _BROWSER_LOCK:
        try:
            result = await _run_collect_subprocess(query, limit, headless)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("collect falhou")
            raise HTTPException(status_code=500, detail=f"coleta falhou: {e}") from e

    # Não vaza caminho local de arquivo pro servidor remoto.
    result.pop("_saved_to", None)
    result.pop("screenshot", None)
    return result


if __name__ == "__main__":
    import uvicorn

    # Windows: o Proactor loop é necessário para asyncio.create_subprocess_exec
    # (o Selector loop não suporta subprocessos). Garante o policy correto.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    uvicorn.run(app, host=config.HOST, port=config.PORT)

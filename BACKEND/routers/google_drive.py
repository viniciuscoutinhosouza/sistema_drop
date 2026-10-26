"""Google Drive — conexão OAuth + status (armazenamento de imagens).

Fluxo da autorização:
  1. tela chama GET /integrations/google-drive/authorize → devolve a URL do Google
  2. usuário autoriza no Google
  3. Google redireciona para GET /integrations/google-drive/callback?code=...  (ÚNICA rota SEM
     autenticação — quem chama é o Google, que não carrega o JWT; só aceita um `code` de uso único)
  4. o código é trocado por refresh_token (cifrado) e a conexão fica gravada

Config/estado são admin-only (integração do sistema). O download dos arquivos é servido PELO
sistema (sem expor o link do Drive) — importante p/ foto com dado do cliente (LGPD).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from dependencies import get_current_user
from models.user import User
from services import google_drive_service as gd
from services.data_scope import is_global

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _require_admin(current_user: User) -> None:
    if not is_global(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores configuram o Google Drive")


def _erro(e: Exception) -> HTTPException:
    if isinstance(e, gd.DriveNaoConfigurado):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, gd.DriveNaoConectado):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=502, detail=str(e))


@router.get("/status")
async def status(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Estado da integração para a tela de configuração (nunca deixa a cota derrubar a resposta)."""
    _require_admin(current_user)
    conta = await gd.active_account(db)
    saida = {
        "configurado": gd.configurado(),
        "conectado": bool(conta),
        "email": conta.email if conta else None,
        "conectado_em": conta.connected_at.isoformat() if (conta and conta.connected_at) else None,
        "ultimo_uso": conta.last_used_at.isoformat() if (conta and conta.last_used_at) else None,
        "ultimo_erro": conta.last_error if conta else None,
        "pasta_raiz_id": conta.root_folder_id if conta else None,
        "pasta_raiz_nome": (conta.root_folder_name if conta else None) or settings.GOOGLE_DRIVE_ROOT_FOLDER,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "escopo": gd.ESCOPO,
        "cota": None,
        "aviso": None,
    }
    if not gd.configurado():
        saida["aviso"] = "Faltam GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env do servidor."
        return saida
    if conta:
        try:
            saida["cota"] = await gd.quota(db)
        except Exception as e:  # noqa: BLE001
            saida["aviso"] = f"Conectado, mas a cota não pôde ser lida: {e}"
    return saida


@router.get("/authorize")
async def authorize(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Devolve a URL para onde a tela deve mandar o usuário autorizar."""
    _require_admin(current_user)
    try:
        return {"url": gd.authorize_url()}
    except Exception as e:  # noqa: BLE001
        raise _erro(e)


@router.get("/callback", response_class=HTMLResponse)
async def callback(code: str | None = None, error: str | None = None, state: str | None = None,
                   db: AsyncSession = Depends(get_db)):
    """Retorno do Google (SEM autenticação — quem chama é o Google). Página que se fecha sozinha."""
    if error:
        return _pagina(False, f"Autorização cancelada ou negada pelo Google ({error}).")
    if not code:
        return _pagina(False, "O Google não devolveu o código de autorização.")
    try:
        conta = await gd.exchange_code(db, code)
    except Exception as e:  # noqa: BLE001
        logger.exception("Falha no callback do Google Drive")
        return _pagina(False, str(e))
    return _pagina(True, f"Conectado como {conta.email or 'conta do Google'}.")


def _pagina(ok: bool, mensagem: str) -> HTMLResponse:
    cor = "#1b8a4b" if ok else "#c0392b"
    titulo = "Google Drive conectado" if ok else "Não foi possível conectar"
    fechar = "<script>setTimeout(function(){window.close()},2500)</script>" if ok else ""
    return HTMLResponse(f"""<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><title>{titulo}</title></head>
<body style="font-family:system-ui,Segoe UI,Roboto,sans-serif;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;background:#f4f6f9">
  <div style="background:#fff;padding:32px 40px;border-radius:8px;max-width:520px;
box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center">
    <h2 style="color:{cor};margin:0 0 12px">{titulo}</h2>
    <p style="color:#444;line-height:1.5;margin:0 0 20px">{mensagem}</p>
    <p style="color:#888;font-size:13px;margin:0">Pode fechar esta aba e voltar ao sistema.</p>
  </div>{fechar}</body></html>""")


@router.delete("/connection")
async def disconnect(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Revoga o acesso. Os arquivos JÁ ENVIADOS continuam no Drive (são do usuário)."""
    _require_admin(current_user)
    if not await gd.disconnect(db):
        raise HTTPException(status_code=404, detail="Nenhuma conta conectada.")
    return {"ok": True, "aviso": "Os arquivos já enviados permanecem no seu Drive."}


@router.post("/test")
async def test(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Prova de ponta a ponta: garante a pasta raiz (Ecommerce_Imagens) e lê a cota."""
    _require_admin(current_user)
    try:
        pasta = await gd.ensure_root(db)
        c = await gd.quota(db)
        return {
            "ok": True,
            "pasta_raiz_id": pasta,
            "pasta_raiz_nome": settings.GOOGLE_DRIVE_ROOT_FOLDER,
            "conta": c.get("email"),
            "espaco": f"{c['usado_gb']} GB de {c['limite_gb']} GB usados" if c.get("limite_gb") else None,
            "percentual": c.get("percentual"),
        }
    except Exception as e:  # noqa: BLE001
        raise _erro(e)

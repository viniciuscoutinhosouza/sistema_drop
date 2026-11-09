"""Bling (ERP) — conexão OAuth2 POR CMIG + status/test/disconnect.

Duas superfícies:
  - `router` (autenticado, escopado por CMIG): montado em `/api/v1/cmigs/{cmig_id}/bling`
    (espelha fiscal_config). Capacidade = permissão `bling_gerenciar` AND acesso à CMIG
    (`assert_cmig_access`, ADR-0036).
  - `public_router` (callback SEM login — quem chama é o Bling): `/api/v1/integrations/bling/callback`.
    O `cmig_id` vem do `state` cifrado (anti-IDOR), nunca do path.

Molde: routers/google_drive.py (ADR-0038). O download/sincronização de dados é fase seguinte.
"""
import html
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from dependencies import get_current_user, require_permission
from models.cmig import CMIG
from models.user import User
from services import bling_service as bling

logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter()
settings = get_settings()


def _erro(e: Exception) -> HTTPException:
    if isinstance(e, bling.BlingNaoConfigurado):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, bling.BlingNaoConectado):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=502, detail=str(e))


async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession) -> CMIG:
    cmig = (await db.execute(select(CMIG).where(CMIG.id == cmig_id))).scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")
    from services.data_scope import assert_cmig_access

    await assert_cmig_access(cmig, user, db)
    return cmig


# ── Rotas autenticadas (por CMIG) ──────────────────────────────────────────────

@router.get("/status")
async def status(
    cmig_id: int,
    current_user: User = Depends(require_permission("bling_gerenciar")),
    db: AsyncSession = Depends(get_db),
):
    """Estado da integração Bling desta CMIG (só leitura do banco — nunca toca a API)."""
    await _check_cmig_access(cmig_id, current_user, db)
    conta = await bling.active_account(db, cmig_id)
    configurado = await bling.configurado_para(db, cmig_id)
    conectado = bool(conta and conta.refresh_token_enc)
    saida = {
        "configurado": configurado,
        "conectado": conectado,
        # credenciais do app Bling desta CMIG (client_id em claro; secret NUNCA sai do servidor)
        "client_id": conta.client_id if conta else None,
        "credenciais_proprias": bool(conta and conta.client_id and conta.client_secret_enc),
        "secret_configurado": bool(conta and conta.client_secret_enc),
        "empresa_id": conta.bling_company_id if conectado else None,
        "empresa_nome": conta.bling_company_name if conectado else None,
        "conectado_em": conta.connected_at.isoformat() if (conectado and conta.connected_at) else None,
        "ultimo_uso": conta.last_used_at.isoformat() if (conta and conta.last_used_at) else None,
        "ultimo_erro": conta.last_error if conta else None,
        "escopo": conta.scope if conectado else None,
        "redirect_uri": settings.BLING_REDIRECT_URI,
        "aviso": None,
    }
    if not configurado:
        saida["aviso"] = ("Cadastre o Client ID e o Secret do app Bling desta CMIG abaixo "
                          "(ou configure um app padrão no servidor).")
    return saida


@router.patch("/credentials")
async def save_credentials(
    cmig_id: int,
    body: dict,
    current_user: User = Depends(require_permission("bling_gerenciar")),
    db: AsyncSession = Depends(get_db),
):
    """Salva as credenciais PRÓPRIAS do app Bling desta CMIG. `client_secret` vazio mantém o atual."""
    await _check_cmig_access(cmig_id, current_user, db)
    client_id = (body.get("client_id") or "").strip()
    client_secret = body.get("client_secret")  # pode vir vazio = manter
    if not client_id:
        raise HTTPException(status_code=422, detail="Client ID é obrigatório.")
    try:
        conta = await bling.save_credentials(db, cmig_id, client_id, client_secret, connected_by=current_user.id)
    except Exception as e:  # noqa: BLE001
        raise _erro(e)
    return {"ok": True, "client_id": conta.client_id, "secret_configurado": bool(conta.client_secret_enc)}


@router.get("/authorize")
async def authorize(
    cmig_id: int,
    current_user: User = Depends(require_permission("bling_gerenciar")),
    db: AsyncSession = Depends(get_db),
):
    """Devolve a URL de consentimento do Bling (com state cifrado carregando esta CMIG)."""
    await _check_cmig_access(cmig_id, current_user, db)
    try:
        cid, _ = await bling.resolve_creds(db, cmig_id)
        state = bling.encode_state(cmig_id, current_user.id)
        return {"url": bling.authorize_url(state, cid)}
    except Exception as e:  # noqa: BLE001
        raise _erro(e)


@router.post("/test")
async def test(
    cmig_id: int,
    current_user: User = Depends(require_permission("bling_gerenciar")),
    db: AsyncSession = Depends(get_db),
):
    """Prova de ponta a ponta: token válido + GET /empresas (confirma a conexão viva)."""
    await _check_cmig_access(cmig_id, current_user, db)
    try:
        emp = await bling.company_info(db, cmig_id)
        return {"ok": True, "empresa": (emp or {}).get("nome"), "empresa_id": (emp or {}).get("id")}
    except Exception as e:  # noqa: BLE001
        raise _erro(e)


@router.delete("/connection")
async def disconnect(
    cmig_id: int,
    current_user: User = Depends(require_permission("bling_gerenciar")),
    db: AsyncSession = Depends(get_db),
):
    """Revoga no Bling (best-effort) e remove a conexão local desta CMIG."""
    await _check_cmig_access(cmig_id, current_user, db)
    try:
        if not await bling.disconnect(db, cmig_id):
            raise HTTPException(status_code=404, detail="Esta CMIG não está conectada ao Bling.")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _erro(e)
    return {"ok": True}


# ── Importação de catálogo (ADR-0040 Fase 2) ───────────────────────────────────

@router.get("/categories")
async def bling_categories(
    cmig_id: int,
    current_user: User = Depends(require_permission("bling_importar")),
    db: AsyncSession = Depends(get_db),
):
    """Lista as categorias de produto do Bling desta CMIG (para o preview da importação)."""
    await _check_cmig_access(cmig_id, current_user, db)
    try:
        from services import bling_import_service as imp
        return {"categorias": await imp.list_categories(db, cmig_id)}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _erro(e)


@router.get("/products")
async def bling_products(
    cmig_id: int,
    pagina: int = 1,
    limite: int = 100,
    id_categoria: int | None = None,
    current_user: User = Depends(require_permission("bling_importar")),
    db: AsyncSession = Depends(get_db),
):
    """Preview paginado dos produtos do Bling desta CMIG."""
    await _check_cmig_access(cmig_id, current_user, db)
    try:
        from services import bling_import_service as imp
        return await imp.list_products(db, cmig_id, pagina=pagina, limite=limite, id_categoria=id_categoria)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _erro(e)


@router.post("/import")
async def bling_import(
    cmig_id: int,
    body: dict,
    current_user: User = Depends(require_permission("bling_importar")),
    db: AsyncSession = Depends(get_db),
):
    """Inicia a importação (job assíncrono). body: {target:'cmig'|'pg', on_conflict:'skip'|'update',
    options:{product_ids?[], images?, kits?}}. Devolve o id do job p/ acompanhar em GET /import/{id}."""
    await _check_cmig_access(cmig_id, current_user, db)
    target = (body.get("target") or "").strip()
    on_conflict = (body.get("on_conflict") or "skip").strip()
    options = body.get("options") or {}
    try:
        from services import bling_import_service as imp
        job = await imp.start_import(db, cmig_id=cmig_id, target=target, on_conflict=on_conflict,
                                     options=options, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _erro(e)
    return {"job_id": job.id, "status": job.status}


@router.get("/import/{job_id}")
async def bling_import_status(
    cmig_id: int,
    job_id: int,
    current_user: User = Depends(require_permission("bling_importar")),
    db: AsyncSession = Depends(get_db),
):
    """Status/progresso do job de importação."""
    await _check_cmig_access(cmig_id, current_user, db)
    from models.bling import BlingImportJob
    job = (await db.execute(
        select(BlingImportJob).where(BlingImportJob.id == job_id, BlingImportJob.cmig_id == cmig_id)
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job de importação não encontrado")
    return {
        "id": job.id, "status": job.status, "progresso": job.progress_step, "total": job.total,
        "criados": job.created_count, "atualizados": job.updated_count,
        "pulados": job.skipped_count, "falhas": job.failed_count, "erro": job.error,
        "target": job.target, "on_conflict": job.on_conflict,
    }


# ── Callback público (SEM login — quem chama é o Bling) ─────────────────────────

@public_router.get("/callback", response_class=HTMLResponse)
async def callback(code: str | None = None, state: str | None = None, error: str | None = None,
                   db: AsyncSession = Depends(get_db)):
    """Retorno do Bling. O cmig_id vem do `state` cifrado (não do path). Página que se fecha sozinha."""
    if error:
        return _pagina(False, f"Autorização cancelada ou negada pelo Bling ({error}).")
    if not code or not state:
        return _pagina(False, "O Bling não devolveu o código/estado de autorização.")
    try:
        st = bling.decode_state(state)
        conta = await bling.exchange_code(db, code, st["cmig_id"], connected_by=st.get("user_id"))
    except Exception as e:  # noqa: BLE001
        logger.exception("Falha no callback do Bling")
        return _pagina(False, str(e))
    return _pagina(True, f"Conectado à empresa {conta.bling_company_name or 'Bling'}.")


def _pagina(ok: bool, mensagem: str) -> HTMLResponse:
    # `mensagem` pode conter texto vindo da API do Bling (nome da empresa, str(e) com r.text) → ESCAPAR
    # antes de injetar no HTML (dado externo → sink HTML). titulo é fixo, mas escapamos por simetria.
    cor = "#1b8a4b" if ok else "#c0392b"
    titulo = html.escape("Bling conectado" if ok else "Não foi possível conectar")
    mensagem = html.escape(mensagem or "")
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

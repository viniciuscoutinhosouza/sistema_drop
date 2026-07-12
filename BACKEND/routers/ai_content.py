"""Geração de conteúdo de produto por IA (descrição).

Reusa a infra que já existe — NÃO fala com o LLM diretamente:
- `services/ai_service.complete()` (OpenAI/Anthropic)
- `AIConfig` (singleton ativo; chave em base64) — mesmo padrão de `routers/messages.py`
- `services/product_brief.build_product_brief()` — ficha técnica do produto, já sanitizada
  contra prompt-injection, usada como contexto quando o produto já existe.
"""

import base64
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.messages import AIConfig
from models.user import User
from services import ai_service as ai_svc
from services.product_brief import build_product_brief

router = APIRouter(prefix="/api/v1/ai", tags=["ai-content"])
logger = logging.getLogger(__name__)

# Teto de saída: descrição de produto é texto de vitrine, não um tratado. Também protege o
# limite de 4000 chars de CMIGProduct.description (o PG é CLOB).
_MAX_TOKENS = 1500

_SYSTEM_PROMPT = """Você é um copywriter especialista em e-commerce brasileiro (Mercado Livre e Shopee).
Sua tarefa é escrever a DESCRIÇÃO de um anúncio de produto.

Regras:
- Escreva em português do Brasil, em texto corrido e/ou tópicos curtos, pronto para colar no anúncio.
- Foque em benefícios para o comprador, características objetivas e uso do produto.
- NÃO invente especificações (medidas, materiais, voltagem, compatibilidade) que não foram informadas.
- NÃO inclua preço, prazo de entrega, frete, garantia ou dados de contato.
- NÃO use markdown (nada de #, *, **), pois o texto vai direto para o campo de descrição.
- Responda APENAS com o texto da descrição — sem preâmbulo, sem comentários, sem aspas."""


async def _load_active_ai_config(db: AsyncSession) -> tuple[str, str, str, str]:
    """(provider, api_key, model, global_instructions) do AIConfig ATIVO. 400 se não houver."""
    cfg = (
        await db.execute(select(AIConfig).where(AIConfig.is_active == True))  # noqa: E712
    ).scalar_one_or_none()
    if not cfg or not cfg.api_key:
        raise HTTPException(
            status_code=400,
            detail="IA não configurada ou inativa. Configure em Administração > Configuração de IA.",
        )
    try:
        api_key = base64.b64decode(cfg.api_key.encode()).decode()
    except Exception:  # noqa: BLE001 — chave corrompida no banco
        raise HTTPException(status_code=400, detail="Chave da IA inválida. Reconfigure em Configuração de IA.")
    return cfg.provider, api_key, cfg.model_name, (cfg.global_instructions or "")


@router.post("/product-description")
async def generate_product_description(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gera a descrição de um produto a partir de um prompt livre.

    Body:
      - `prompt` (obrigatório): o que o usuário quer.
      - `previous_response` (opcional): resposta anterior da IA, reenviada como CONTEXTO
        (é o checkbox "usar a resposta como contexto do próximo prompt").
      - `product_type` ('pg'|'cmig') + `product_id` (opcional): quando o produto já existe,
        a ficha técnica dele entra como contexto automaticamente.
    """
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Informe o que a IA deve escrever (prompt).")

    provider, api_key, model, global_instructions = await _load_active_ai_config(db)

    parts: list[str] = []

    # 1) Ficha técnica do produto (só quando ele já existe — no cadastro novo não há id).
    product_type = body.get("product_type")
    product_id = body.get("product_id")
    if product_type in ("pg", "cmig") and product_id:
        try:
            brief = await build_product_brief(db, product_type, int(product_id))
        except (TypeError, ValueError):
            brief = ""
        if brief:
            parts.append(f"FICHA TÉCNICA DO PRODUTO:\n{brief}")

    # 2) Resposta anterior como contexto (o checkbox do modal).
    previous = (body.get("previous_response") or "").strip()
    if previous:
        parts.append(
            "DESCRIÇÃO GERADA ANTERIORMENTE (use como base/contexto e ajuste conforme o pedido "
            f"abaixo):\n{previous[:6000]}"
        )

    # 3) O pedido do usuário.
    parts.append(f"PEDIDO DO USUÁRIO:\n{prompt}")

    system_prompt = _SYSTEM_PROMPT
    if global_instructions.strip():
        system_prompt += f"\n\nInstruções gerais da empresa:\n{global_instructions.strip()}"

    try:
        text = await ai_svc.complete(
            provider=provider,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_content="\n\n".join(parts),
            max_tokens=_MAX_TOKENS,
            timeout=90,
        )
    except httpx.TimeoutException:
        # ai_service não trata timeout — sem isto vazaria como 500.
        raise HTTPException(status_code=504, detail="A IA demorou demais para responder. Tente novamente.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ai] falha ao gerar descrição: %s", exc)
        raise HTTPException(status_code=502, detail="Falha ao gerar a descrição com a IA.")

    return {"description": (text or "").strip(), "model": f"{provider}:{model}"}

"""
AI service para geração de respostas de atendimento.
Suporta OpenAI e Anthropic (Claude).
"""

import logging

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024
TIMEOUT = 30


def _build_history(messages: list[dict]) -> list[dict]:
    """Converte mensagens do sistema para formato compatível com OpenAI/Anthropic."""
    result = []
    for msg in messages:
        role = "user" if msg["from_role"] == "buyer" else "assistant"
        if msg.get("text"):
            result.append({"role": role, "content": msg["text"]})
    return result


async def generate_reply(
    provider: str,
    api_key: str,
    model: str,
    global_instructions: str,
    custom_instructions: str | None,
    conversation_history: list[dict],
) -> str:
    """
    Gera uma sugestão de resposta para a conversa usando IA.

    conversation_history: lista de dicts com {from_role, text}
    Retorna o texto sugerido.
    """
    system_prompt = global_instructions or ""
    if custom_instructions:
        system_prompt = f"{system_prompt}\n\n{custom_instructions}".strip()

    history = _build_history(conversation_history)
    if not history:
        raise HTTPException(
            status_code=400, detail="Histórico de conversa vazio para gerar resposta."
        )

    # Garante que a última mensagem é do comprador
    if history[-1]["role"] != "user":
        history.append({"role": "user", "content": "(aguardando resposta)"})

    if provider == "openai":
        return await _generate_openai(api_key, model, system_prompt, history)
    elif provider == "anthropic":
        return await _generate_anthropic(api_key, model, system_prompt, history)
    else:
        raise HTTPException(status_code=400, detail=f"Provedor de IA desconhecido: {provider}")


async def complete(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_content: str,
    *,
    max_tokens: int = 4000,
    timeout: int = 90,
) -> str:
    """Completion genérico (1 mensagem do usuário). Usado por features que precisam de
    saída longa/estruturada (ex.: Análise de Concorrência). Retorna o texto puro."""
    history = [{"role": "user", "content": user_content}]
    if provider == "openai":
        return await _generate_openai(api_key, model, system_prompt, history, max_tokens, timeout)
    elif provider == "anthropic":
        return await _generate_anthropic(api_key, model, system_prompt, history, max_tokens, timeout)
    raise HTTPException(status_code=400, detail=f"Provedor de IA desconhecido: {provider}")


async def _generate_openai(
    api_key: str, model: str, system_prompt: str, history: list[dict],
    max_tokens: int = DEFAULT_MAX_TOKENS, timeout: int = TIMEOUT
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )

    if resp.status_code != 200:
        logger.warning("OpenAI error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=f"Erro na API OpenAI: {resp.status_code}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def _generate_anthropic(
    api_key: str, model: str, system_prompt: str, history: list[dict],
    max_tokens: int = DEFAULT_MAX_TOKENS, timeout: int = TIMEOUT
) -> str:
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": history,
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if resp.status_code != 200:
        logger.warning("Anthropic error %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=f"Erro na API Anthropic: {resp.status_code}")

    data = resp.json()
    return data["content"][0]["text"].strip()


async def test_connection(provider: str, api_key: str, model: str) -> bool:
    """Testa se a API key e modelo estão funcionando."""
    try:
        result = await generate_reply(
            provider=provider,
            api_key=api_key,
            model=model,
            global_instructions="Responda apenas 'OK'.",
            custom_instructions=None,
            conversation_history=[{"from_role": "buyer", "text": "teste"}],
        )
        return bool(result)
    except Exception as e:
        logger.warning("AI test failed: %s", e)
        raise

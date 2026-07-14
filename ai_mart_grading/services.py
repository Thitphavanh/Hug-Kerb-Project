"""
OpenRouter API client (Scope 2.4)
ໃຊ້ຮ່ວມກັນລະຫວ່າງ ai_mart_grading ແລະ resell_pricing_engine

ຕັ້ງຄ່າໃນ .env:
    OPENROUTER_API_KEY=sk-or-...
    OPENROUTER_MODEL=anthropic/claude-sonnet-5
"""

import json
import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"
DEFAULT_MAX_TOKENS = 2000
MAX_OUTPUT_TOKEN_CAP = 4096
# slug ເກົ່າທີ່ OpenRouter ປົດອອກແລ້ວ — map ໄປ model ປັດຈຸບັນ ກັນ .env ເກົ່າຄ້າງ
MODEL_ALIASES = {
    "anthropic/claude-3-5-sonnet": DEFAULT_MODEL,
    "anthropic/claude-3.5-sonnet": DEFAULT_MODEL,
    "anthropic/claude-3.5-sonnet:beta": DEFAULT_MODEL,
}


class OpenRouterError(Exception):
    pass


def _resolve_max_tokens(max_tokens=None):
    raw_value = (
        max_tokens
        if max_tokens is not None
        else os.environ.get("OPENROUTER_MAX_TOKENS", DEFAULT_MAX_TOKENS)
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_TOKENS
    return max(256, min(value, MAX_OUTPUT_TOKEN_CAP))


def _resolve_model(model=None):
    configured_model = (
        model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    ).strip()
    return MODEL_ALIASES.get(configured_model, configured_model or DEFAULT_MODEL)


def _error_detail(response):
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return response.text[:500]
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:500]
    return response.text[:500]


def chat(
    messages,
    model=None,
    temperature=0.2,
    max_tokens=None,
    timeout=90,
    response_format=None,
):
    """ສົ່ງ messages ໄປ OpenRouter ແລ້ວຄືນ (ຂໍ້ຄວາມຕອບ, response ດິບ)"""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY ຍັງບໍ່ໄດ້ຕັ້ງໃນ .env")

    model = _resolve_model(model)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": _resolve_max_tokens(max_tokens),
    }
    if response_format:
        payload["response_format"] = response_format

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code == 404 and model != DEFAULT_MODEL:
        payload["model"] = DEFAULT_MODEL
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    if response.status_code != 200:
        raise OpenRouterError(
            f"OpenRouter ຕອບ {response.status_code}: {_error_detail(response)}"
        )
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenRouterError(f"ຮູບແບບຄຳຕອບບໍ່ຖືກຕ້ອງ: {data}") from exc
    return content, data


def chat_json(messages, model=None, temperature=0.2, max_tokens=None, timeout=90):
    """ຄືກັບ chat() ແຕ່ parse ຄຳຕອບເປັນ JSON (ສຳລັບ grading/pricing ທີ່ຕ້ອງການ structured output)"""
    content, data = chat(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        response_format={"type": "json_object"},
    )
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text), data
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"AI ບໍ່ໄດ້ຕອບເປັນ JSON: {content[:500]}") from exc

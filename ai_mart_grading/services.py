"""
OpenRouter API client (Scope 2.4)
ໃຊ້ຮ່ວມກັນລະຫວ່າງ ai_mart_grading ແລະ resell_pricing_engine

ຕັ້ງຄ່າໃນ .env:
    OPENROUTER_API_KEY=sk-or-...
    OPENROUTER_MODEL=anthropic/claude-sonnet-5
"""

import json
import os
import re

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
    detail = (
        str(error["message"])
        if isinstance(error, dict) and error.get("message")
        else response.text
    )
    # Provider messages sometimes append a key-management URL. It is not
    # useful to staff and can expose an internal key identifier in the UI.
    detail = re.split(r"\s+To increase, visit\s+", detail, maxsplit=1)[0]
    return detail[:500]


def _credit_safe_max_tokens(response, requested_tokens):
    """Return a smaller output limit when OpenRouter reports an affordable cap."""
    if response.status_code != 402:
        return None
    match = re.search(
        r"can only afford\s+([\d,]+)",
        _error_detail(response),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    affordable = int(match.group(1).replace(",", ""))
    # Keep a small buffer because the available credit can change between calls.
    retry_tokens = min(requested_tokens - 1, affordable - 64)
    return retry_tokens if retry_tokens >= 256 else None


def chat(
    messages,
    model=None,
    temperature=0.2,
    max_tokens=None,
    timeout=90,
    response_format=None,
    reasoning=None,
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
    if reasoning is not None:
        payload["reasoning"] = reasoning

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
    retry_tokens = _credit_safe_max_tokens(response, payload["max_tokens"])
    if retry_tokens is not None:
        payload["max_tokens"] = retry_tokens
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
    try:
        data = response.json()
    except (ValueError, TypeError) as exc:
        raise OpenRouterError("OpenRouter ຕອບກັບມາບໍ່ແມ່ນ JSON") from exc
    try:
        choice = data["choices"][0]
        content = choice["message"].get("content")
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise OpenRouterError("ຮູບແບບຄຳຕອບຈາກ OpenRouter ບໍ່ຖືກຕ້ອງ") from exc
    if not isinstance(content, str) or not content.strip():
        choice_error = choice.get("error") or {}
        error_message = (
            choice_error.get("message") if isinstance(choice_error, dict) else None
        )
        finish_reason = choice.get("finish_reason") or "unknown"
        detail = error_message or (
            "AI ບໍ່ໄດ້ສົ່ງເນື້ອຫາກັບມາ "
            f"(finish_reason={finish_reason})"
        )
        raise OpenRouterError(detail)
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
        # Condition grading only needs a compact structured answer. Disabling
        # reasoning preserves the output budget for the actual JSON response.
        reasoning={"effort": "none", "exclude": True},
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

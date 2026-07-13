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


class OpenRouterError(Exception):
    pass


def chat(messages, model=None, temperature=0.2, timeout=90):
    """ສົ່ງ messages ໄປ OpenRouter ແລ້ວຄືນ (ຂໍ້ຄວາມຕອບ, response ດິບ)"""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY ຍັງບໍ່ໄດ້ຕັ້ງໃນ .env")

    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise OpenRouterError(
            f"OpenRouter ຕອບ {response.status_code}: {response.text[:500]}"
        )
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenRouterError(f"ຮູບແບບຄຳຕອບບໍ່ຖືກຕ້ອງ: {data}") from exc
    return content, data


def chat_json(messages, model=None, temperature=0.2, timeout=90):
    """ຄືກັບ chat() ແຕ່ parse ຄຳຕອບເປັນ JSON (ສຳລັບ grading/pricing ທີ່ຕ້ອງການ structured output)"""
    content, data = chat(messages, model=model, temperature=temperature, timeout=timeout)
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text), data
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"AI ບໍ່ໄດ້ຕອບເປັນ JSON: {content[:500]}") from exc

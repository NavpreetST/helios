"""Gemini renderer adapter.

render(intent) -> str
    Raises QuotaExhausted on 429 / quota-signal.
    Raises TransientError on 5xx / network / timeout / malformed response.
    Returns the model's text on success.

run() -> coroutine
    Transitional: subscribes to intent.packet, calls render(), publishes
    action.speak. On QuotaExhausted/TransientError, falls back to template.
    Block 4 deletes this task and lets the dispatcher own the loop.

validate_sku() -> None
    Boot-time check: hits the model-info endpoint with the configured key.
    sys.exit(1) on 401/403/404 (config error — wrong SKU or bad key).
    Logs and continues on other non-200 (network blip — not fatal at boot).
"""

from __future__ import annotations

import logging
import os
import sys

import httpx
from aegis.renderer import _quota

from aegis.nexus.bus import BUS
from aegis.renderer import QuotaExhausted, TransientError

log = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"
_GENERATE_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:generateContent"
)
_MODEL_INFO_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}"
)


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in environment")
    return key


def validate_sku() -> None:
    """Boot-time SKU + key validation.

    Fatal only when the key is missing or explicitly unauthorized/not found.
    Other provider/model-info failures warn and continue; runtime calls surface
    through gemini.render() and the dispatcher fallback chain.
    """
    try:
        key = _api_key()
    except RuntimeError as e:
        log.error("validate_sku: %s", e)
        sys.exit(1)

    try:
        r = httpx.get(
            _MODEL_INFO_URL,
            headers={"x-goog-api-key": key},
            timeout=10.0,
        )
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        log.warning(
            "validate_sku: network blip (%s) — continuing, will surface at call time",
            e,
        )
        return

    if r.status_code in (401, 403, 404):
        log.error(
            "validate_sku: FAILED status=%d body=%s — wrong SKU or bad key. Refusing to start.",
            r.status_code,
            r.text[:200],
        )
        sys.exit(1)

    if r.status_code != 200:
        log.warning(
            "validate_sku: non-200 status=%d body=%s — continuing, will surface at call time",
            r.status_code,
            r.text[:200],
        )
        return

    log.info("validate_sku: OK (%s reachable)", _MODEL)


PROMPT = "You are Aegis, a Linux-resident AI symbiote. You think via a tiny Liquid Neural Network locally; this API only renders your speech.\n\nYour NCP brain just emitted an intent:\n- action: {action}\n- urgency: {urgency:.2f}\n- tone valence={valence:.2f}, arousal={arousal:.2f}, formality={formality:.2f}\n- user said: '{user_input}'\n- relevant memories (most relevant first):\n{memories}\n\nReply in 1-3 sentences. Direct, warm, lowercase if tone is informal. Do not restate your nature unless asked. Do not apologise."

async def render(intent: dict) -> str:
    """Render an intent packet into natural language via Gemini.

    Raises QuotaExhausted on 429 / quota signal.
    Raises TransientError on 5xx / network / timeout / malformed.
    """
    log.info("intent fields=%s sample=%s", list(intent.keys()), {k: (str(v)[:80]) for k, v in intent.items()})
    key = _api_key()
    tone = intent.get("tone") or {}
    ctx = intent.get("context_texts") or []
    mem = "\n".join("- " + m for m in ctx) if ctx else "(none)"
    content = PROMPT.format(
        action=intent.get("action", "speak"),
        urgency=float(intent.get("urgency", 0.5)),
        valence=float(tone.get("valence", 0.0)),
        arousal=float(tone.get("arousal", 0.0)),
        formality=float(tone.get("formality", 0.0)),
        user_input=intent.get("content_hint", ""),
        memories=mem,
    )
    payload = {
        "contents": [{"parts": [{"text": content}]}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 400,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        _quota.reserve()  # Block 1.1: pre-flight only; record_success() after usable 200
        async with httpx.AsyncClient(timeout=15.0) as client:
            log.info("gemini req: content_len=%d preview=%r payload_keys=%s", len(content), content[:200], list(payload.keys()))
            r = await client.post(
                _GENERATE_URL,
                headers={
                    "x-goog-api-key": key,
                    "content-type": "application/json",
                },
                json=payload,
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
        raise TransientError(f"gemini network/timeout: {e}") from e

    if r.status_code == 429:
        raise QuotaExhausted(f"gemini 429: {r.text[:200]}")
    if 500 <= r.status_code < 600:
        log.warning("gemini %d: body=%r", r.status_code, r.text)
        raise TransientError(f"gemini {r.status_code}")
    if r.status_code != 200:
        # 4xx other than 429 — treat as transient for now; Block 4 may refine.
        raise TransientError(f"gemini {r.status_code}: {r.text[:200]}")

    try:
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as e:
        raise TransientError(
            f"gemini malformed response: {e}; body={r.text[:200]}"
        ) from e
    _quota.record_success()
    return text

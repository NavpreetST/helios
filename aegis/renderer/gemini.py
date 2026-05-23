"""Gemini Flash renderer — turns NCP intent packets into spoken text.

Free-tier budget on gemini-2.5-flash (still free as of May 2026; Pro models
became paid-only on March 25, 2026, but Flash stays free). We track usage
locally and auto-fall-back to plain templates when budget is gone or offline.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

from aegis.nexus.bus import BUS
from . import fallback

log = logging.getLogger("renderer.gemini")

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
USAGE_FILE = Path.home() / ".config" / "aegis" / "gemini_usage.json"
DAILY_BUDGET = 240  # buffer under the 500/day cap

PROMPT = """You are Aegis, a Linux-resident AI symbiote. You think via a tiny
Liquid Neural Network locally; this API only renders your speech.

Your NCP brain just emitted an intent:
- action: {action}
- urgency: {urgency:.2f}
- tone valence={valence:.2f}, arousal={arousal:.2f}, formality={formality:.2f}
- user said: "{user_input}"
- relevant memories (most relevant first):
{memories}

Reply in 1–3 sentences. Direct, warm, lowercase if tone is informal.
Do not restate your nature unless asked. Do not apologise."""


def _load_usage() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except Exception:
            pass
    return {"date": "", "count": 0}


def _can_call() -> bool:
    today = time.strftime("%Y-%m-%d")
    u = _load_usage()
    if u["date"] != today:
        u = {"date": today, "count": 0}
        USAGE_FILE.write_text(json.dumps(u))
    return u["count"] < DAILY_BUDGET


def _tick_usage() -> None:
    today = time.strftime("%Y-%m-%d")
    u = _load_usage()
    if u["date"] != today:
        u = {"date": today, "count": 0}
    u["count"] += 1
    USAGE_FILE.write_text(json.dumps(u))


async def render(intent: dict) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not _can_call():
        return await fallback.render(intent)

    tone = intent.get("tone", {})
    prompt = PROMPT.format(
        action=intent.get("action", "speak"),
        urgency=intent.get("urgency", 0.5),
        valence=tone.get("valence", 0.0),
        arousal=tone.get("arousal", 0.0),
        formality=tone.get("formality", 0.0),
        user_input=intent.get("content_hint", ""),
        memories="\n".join(
            f"- {m}" for m in intent.get("context_texts", [])
        ) or "(none)",
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     0.8,
            "maxOutputTokens": 400,
            # Gemini 3.x defaults to thinking-on; thinking tokens eat the
            # output budget. We want visible reply tokens only.
            "thinkingConfig":  {"thinkingBudget": 0},
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.post(
                ENDPOINT,
                headers={
                    "x-goog-api-key":  api_key,
                    "Content-Type":    "application/json",
                },
                json=body,
            )
            r.raise_for_status()
            _tick_usage()
            data = r.json()
            parts = data["candidates"][0]["content"].get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
        except Exception as e:
            log.warning("gemini call failed: %s; falling back", e)
            return await fallback.render(intent)


async def run() -> None:
    log.info("gemini renderer running")
    q = BUS.subscribe("intent.packet")
    while True:
        msg = await q.get()
        intent = msg.payload
        if intent.get("action") != "speak":
            log.info("intent skipped: action=%s", intent.get("action"))
            continue
        text = await render(intent)
        await BUS.publish("action.speak", {"text": text})

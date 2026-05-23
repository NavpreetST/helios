"""Offline / rate-limited template fallback.

Plain str.format() — no Jinja dependency. Kept deliberately dumb;
this only runs when Gemini is unavailable or the daily budget is gone.
"""
import random

GREETING = [
    "hey. heard you: {0}",
    "i'm here. you said: {0}",
    "noted: {0}",
]
ACK = ["got it.", "ok.", "noted."]


async def render(intent: dict) -> str:
    u = intent.get("content_hint", "").strip()
    if u:
        return random.choice(GREETING).format(u)
    return random.choice(ACK)

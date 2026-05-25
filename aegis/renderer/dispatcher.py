"""Dispatcher — renderer chain owner (Block 4).

Owns the renderer fallback CHAIN at module level.
Subscribes to intent.packet, walks each adapter, publishes action.speak.

This replaces gemini.run() as the BUS task. Individual provider modules expose
async render(intent: dict) -> str and raise renderer-tier exceptions when they
cannot produce usable speech.

Initial chain:
    Gemini -> Template

Block 5 will insert Groq:
    Gemini -> Groq -> Template
"""

from __future__ import annotations

import logging

from aegis.nexus.bus import BUS
from aegis.renderer import QuotaExhausted, TransientError
from aegis.renderer import fallback, gemini

log = logging.getLogger(__name__)


class Gemini:
    """Thin wrapper around gemini.render()."""

    name = "gemini"

    async def render(self, intent: dict) -> str:
        return await gemini.render(intent)


class Template:
    """Thin wrapper around fallback.render(). Never raises — chain terminator."""

    name = "template"

    async def render(self, intent: dict) -> str:
        return await fallback.render(intent)


# Block 5 inserts Groq before Template:
#   from aegis.renderer import groq
#
#   class Groq:
#       name = "groq"
#       async def render(self, intent: dict) -> str:
#           return await groq.render(intent)
#
#   CHAIN = [Gemini, Groq, Template]

CHAIN = [Gemini, Template]


async def run() -> None:
    """Subscribe to intent.packet, walk CHAIN, publish action.speak."""
    q = BUS.subscribe("intent.packet")
    while True:
        msg = await q.get()
        intent = msg.payload

        if intent.get("action") != "speak":
            log.info("dispatcher: intent skipped: action=%s", intent.get("action"))
            continue

        text = await _render_with_chain(intent)
        await BUS.publish("action.speak", {"text": text})


async def _render_with_chain(intent: dict) -> str:
    """Try each adapter class in CHAIN order."""
    for adapter_cls in CHAIN:
        adapter = adapter_cls()
        try:
            text = await adapter.render(intent)
            if text:
                log.info("dispatcher: rendered via %s", adapter.name)
                return text
            log.warning("dispatcher: %s returned empty string, advancing", adapter.name)
        except QuotaExhausted as e:
            log.warning("dispatcher: %s quota exhausted — %s", adapter.name, e)
            continue
        except TransientError as e:
            log.warning("dispatcher: %s transient error — %s", adapter.name, e)
            continue

    # Unreachable while Template remains the final adapter.
    log.error("dispatcher: all adapters exhausted — returning empty string")
    return ""


# TODO(test): mock gemini.render to raise QuotaExhausted and verify Template
# is reached and action.speak is published with template text.

"""Dispatcher — renderer chain owner (Block 4).

Replaces gemini.run()'s transitional BUS task. Owns CHAIN at module level,
subscribes to intent.packet, walks each adapter, publishes action.speak.

Cutover for main.py (aegis/main.py):
    # BEFORE (transitional — delete these lines):
    from aegis.renderer import gemini
    tasks.append(asyncio.create_task(gemini.run()))

    # AFTER (dispatcher owns the loop):
    from aegis.renderer import dispatcher
    tasks.append(asyncio.create_task(dispatcher.run()))

Once the cutover ships and smoke passes:
    - Delete gemini.run() from aegis/renderer/gemini.py.
    - Remove `from aegis.renderer import fallback` from gemini.py.
"""

from __future__ import annotations

import logging

from aegis.nexus.bus import BUS
from aegis.renderer import QuotaExhausted, TransientError
from aegis.renderer import gemini, fallback, groq

log = logging.getLogger(__name__)


class Gemini:
    """Thin wrapper around gemini.render()."""
    name = "gemini"

    async def render(self, intent: dict) -> str:
        return await gemini.render(intent)


class Groq:
    """Thin wrapper around groq.render()."""
    name = "groq"

    async def render(self, intent: dict) -> str:
        return await groq.render(intent)


class Template:
    """Thin wrapper around fallback.render(). Never raises — chain terminator."""
    name = "template"

    async def render(self, intent: dict) -> str:
        return await fallback.render(intent)


CHAIN = [Gemini, Groq, Template]


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
            log.warning(
                "dispatcher: %s returned empty string, advancing", adapter.name
            )
        except QuotaExhausted as e:
            log.warning("dispatcher: %s quota exhausted — %s", adapter.name, e)
            continue
        except TransientError as e:
            log.warning("dispatcher: %s transient error — %s", adapter.name, e)
            continue

    log.error("dispatcher: all adapters exhausted — returning empty string")
    return ""


# TODO(test): mock gemini.render to raise QuotaExhausted on the first call
# and TransientError on the second; verify fallback.render is reached and
# action.speak is published with the template text on the BUS.
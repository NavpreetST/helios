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
import time

from aegis.nexus.bus import BUS
from aegis.renderer import QuotaExhausted, TransientError, RendererError
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

        result = await _render_with_chain(intent)
        await BUS.publish("action.speak", result)


async def _render_with_chain(intent: dict) -> dict:
    """Try each adapter class in CHAIN order.

    Returns {"text": str, "provider": str, "fallback_fired": bool,
             "error_class": str|None, "render_ms": int}.
    Also calls record_provider_attempt() for renderer_state.json.
    """
    from aegis.observability.renderer_state import record_provider_attempt

    t0 = time.perf_counter()
    fallback_fired = False
    last_error_class = None
    chain_names = [a.name for a in [cls() for cls in CHAIN]]
    for adapter_cls in CHAIN:
        adapter = adapter_cls()
        try:
            text = await adapter.render(intent)
            if text:
                render_ms = int((time.perf_counter() - t0) * 1000)
                log.info("dispatcher: rendered via %s", adapter.name)
                result = {
                    "text": text,
                    "provider": adapter.name,
                    "fallback_fired": fallback_fired,
                    "error_class": last_error_class if fallback_fired else None,
                    "render_ms": render_ms,
                }
                record_provider_attempt(
                    chain_order=chain_names,
                    rendered_by=adapter.name,
                    fallback_fired=fallback_fired,
                    fallback_from=chain_names[0] if fallback_fired else None,
                    fallback_to=adapter.name if fallback_fired else None,
                    error_class=last_error_class,
                )
                return result
            if not fallback_fired:
                fallback_fired = True
            log.warning("dispatcher: %s returned empty string, advancing", adapter.name)
        except RendererError as e:
            if not fallback_fired:
                fallback_fired = True
                last_error_class = type(e).__name__
            if isinstance(e, QuotaExhausted):
                log.warning("dispatcher: %s quota exhausted", adapter.name)
            else:
                log.warning("dispatcher: %s renderer error — %s", adapter.name, e)
            continue
        except Exception as e:
            if not fallback_fired:
                fallback_fired = True
                last_error_class = "unexpected"
            log.warning("dispatcher: %s unexpected error — %s", adapter.name, e)
            continue

    render_ms = int((time.perf_counter() - t0) * 1000)
    log.error("dispatcher: all adapters exhausted — returning empty string")
    result = {
        "text": "",
        "provider": "template",
        "fallback_fired": True,
        "error_class": last_error_class,
        "render_ms": render_ms,
    }
    record_provider_attempt(
        chain_order=chain_names,
        rendered_by="template",
        fallback_fired=True,
        fallback_from=chain_names[0],
        fallback_to="template",
        error_class=last_error_class,
    )
    return result


# TODO(test): mock gemini.render to raise QuotaExhausted on the first call
# and TransientError on the second; verify fallback.render is reached and
# action.speak is published with the template text on the BUS.
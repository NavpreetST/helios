"""Groq renderer adapter (Block 5).

Free-tier model: llama-3.3-70b-versatile (~14,400 RPD).
Endpoint speaks OpenAI /v1/chat/completions format.
"""

from __future__ import annotations

from aegis.renderer.openai_compat import OpenAICompatRenderer

_renderer = OpenAICompatRenderer(
    model="llama-3.3-70b-versatile",
    endpoint_url="https://api.groq.com/openai/v1/chat/completions",
    api_key_env="GROQ_API_KEY",
    name="groq",
)


async def render(intent: dict) -> str:
    """Render an intent packet via Groq.

    Public signature matches gemini.render() and fallback.render()
    so the dispatcher adapter can call it transparently.
    """
    return await _renderer.render(intent)

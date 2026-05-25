"""Shared OpenAI-compatible renderer base (Block 5).

Reusable across Groq, Cerebras, and any other provider that speaks the
OpenAI /v1/chat/completions format. Each concrete adapter instantiates
this with model name, endpoint URL, and the env var holding its API key.
"""

from __future__ import annotations

import logging
import os

import httpx

from aegis.renderer import QuotaExhausted, TransientError
from aegis.renderer.gemini import PROMPT

log = logging.getLogger(__name__)


class OpenAICompatRenderer:
    """Async renderer for any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        *,
        model: str,
        endpoint_url: str,
        api_key_env: str,
        name: str,
        timeout: float = 15.0,
    ) -> None:
        self.model = model
        self.endpoint_url = endpoint_url
        self.api_key_env = api_key_env
        self.name = name
        self.timeout = timeout

    def _api_key(self) -> str:
        key = os.getenv(self.api_key_env)
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} not set in environment"
            )
        return key

    async def render(self, intent: dict) -> str:
        """Render an intent packet via the OpenAI-compatible endpoint.

        Raises QuotaExhausted on 429.
        Raises TransientError on 5xx / network / timeout / malformed.
        """
        key = self._api_key()
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
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 400,
            "temperature": 0.8,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    self.endpoint_url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ) as e:
            raise TransientError(
                f"{self.name} network/timeout: {e}"
            ) from e

        if r.status_code == 429:
            raise QuotaExhausted(f"{self.name} 429: {r.text[:200]}")
        if 500 <= r.status_code < 600:
            log.warning("%s %d: body=%r", self.name, r.status_code, r.text)
            raise TransientError(f"{self.name} {r.status_code}")
        if r.status_code != 200:
            raise TransientError(
                f"{self.name} {r.status_code}: {r.text[:200]}"
            )

        try:
            data = r.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise TransientError(
                f"{self.name} malformed response: {e}; body={r.text[:200]}"
            ) from e
        return text

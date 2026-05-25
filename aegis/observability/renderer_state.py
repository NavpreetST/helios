"""Provider state writer — atomic JSON, no raw keys, live quota."""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

from aegis.observability.paths import RENDERER_STATE_PATH, atomic_write_json
from aegis.renderer import _quota

log = logging.getLogger(__name__)


def _key_fingerprint(env_var: str) -> str | None:
    key = os.getenv(env_var)
    if not key:
        return None
    return f"sha256:{hashlib.sha256(key.encode()).hexdigest()[:8]}"


def _gemini_used() -> int | None:
    try:
        usage = _quota._load()
        return int(usage.get("count", 0))
    except Exception:
        return None


def record_provider_attempt(
    *,
    chain_order: list[str],
    rendered_by: str,
    fallback_fired: bool,
    fallback_from: str | None = None,
    fallback_to: str | None = None,
    error_class: str | None = None,
    gemini_budget: int | None = None,
) -> None:
    try:
        now = datetime.now(timezone.utc).isoformat()
        budget = gemini_budget if gemini_budget is not None else _quota.DAILY_BUDGET
        used = _gemini_used()
        state = {
            "updated_at": now,
            "chain": chain_order,
            "last_success": {"provider": rendered_by, "ts": now},
            "providers": {
                "gemini": {
                    "enabled": True,
                    "local_daily_budget": budget,
                    "local_daily_used": used,
                    "quota_window": "America/Los_Angeles",
                },
                "groq": {
                    "enabled": True,
                    "model": "llama-3.3-70b-versatile",
                    "key_fingerprint": _key_fingerprint("GROQ_API_KEY"),
                },
                "template": {"enabled": True, "local_only": True},
            },
        }
        if fallback_fired and fallback_from:
            state["last_fallback"] = {
                "from": fallback_from,
                "to": fallback_to or rendered_by,
                "reason": error_class or "unknown",
                "ts": now,
            }
        atomic_write_json(RENDERER_STATE_PATH, state)
    except (OSError, ValueError) as e:
        log.warning("observability: failed to write renderer_state — %s", e)

"""Block 1.1 — belt-and-braces daily budget cap for the Gemini renderer.

The Gemini free-tier daily quota is provider-anchored to Pacific Time, not UTC.
Use a named IANA zone so PDT/PST transitions are handled by the stdlib.

Accounting is split deliberately:
- reserve() is a pre-flight check only; it does not increment.
- record_success() increments only after a usable provider response.

That split prevents failed provider calls (429/5xx/network/malformed responses)
from burning the local safety budget.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from aegis.renderer import QuotaExhausted

DAILY_BUDGET = int(os.getenv("AEGIS_GEMINI_DAILY_BUDGET", "240"))
_USAGE_PATH = Path.home() / ".local" / "share" / "aegis" / "gemini_usage.json"
_PROVIDER_TZ = ZoneInfo("America/Los_Angeles")


def _today_pacific(now: datetime | None = None) -> str:
    """Return the provider quota-window date in America/Los_Angeles.

    Test anchors:
    - Mid-PDT UTC midnight: 2026-05-25 00:30 UTC -> 2026-05-24 PT.
    - DST-forward day: 2026-03-08 stays 2026-03-08 across the skipped hour.
    - DST-back day: 2026-11-01 stays 2026-11-01 across the repeated hour.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_PROVIDER_TZ).strftime("%Y-%m-%d")


def _load() -> dict:
    today = _today_pacific()
    try:
        data = json.loads(_USAGE_PATH.read_text())
        if data.get("date") != today:
            return {"date": today, "count": 0}
        return {"date": today, "count": int(data.get("count", 0))}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return {"date": today, "count": 0}


def _save(usage: dict) -> None:
    _USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USAGE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(usage))
    tmp.replace(_USAGE_PATH)


def reserve() -> None:
    """Pre-flight budget check.

    Does not increment. Call record_success() only after the provider returns a
    usable response.
    """
    usage = _load()
    if usage["count"] >= DAILY_BUDGET:
        raise QuotaExhausted(
            f"local daily budget exhausted: {usage['count']}/{DAILY_BUDGET} on {usage['date']}"
        )


def record_success() -> None:
    """Increment local usage after a successful Gemini render."""
    usage = _load()
    usage["count"] += 1
    _save(usage)

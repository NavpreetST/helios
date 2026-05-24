"""Block 1.1 — belt-and-braces daily budget cap for the Gemini renderer."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from aegis.renderer import QuotaExhausted

DAILY_BUDGET = int(os.getenv("AEGIS_GEMINI_DAILY_BUDGET", "240"))
_USAGE_PATH = Path.home() / ".local" / "share" / "aegis" / "gemini_usage.json"


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    today = _today_utc()
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
    usage = _load()
    if usage["count"] >= DAILY_BUDGET:
        raise QuotaExhausted(
            f"local daily budget exhausted: {usage['count']}/{DAILY_BUDGET} on {usage['date']}"
        )
    usage["count"] += 1
    _save(usage)

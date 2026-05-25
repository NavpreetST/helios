"""Shared state paths and atomic JSON helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path

STATE_DIR = Path(os.getenv("AEGIS_STATE_DIR", "/var/lib/aegis"))

TURNS_PATH = STATE_DIR / "turns.jsonl"
RENDERER_STATE_PATH = STATE_DIR / "renderer_state.json"
NEUROBUS_STATE_PATH = STATE_DIR / "neurobus_state.json"


def atomic_write_json(path: Path, data: dict | list) -> None:
    """Write JSON atomically via temp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)

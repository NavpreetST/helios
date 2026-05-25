"""B2 turn-log writer — JSONL subscriber on the Bus."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from aegis.nexus.bus import BUS
from aegis.observability.paths import TURNS_PATH

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 50 * 1024 * 1024

_current_turn: dict = {}
_turn_start: float = 0.0


def _warn_if_large() -> None:
    try:
        size = TURNS_PATH.stat().st_size
        if size > MAX_FILE_BYTES:
            log.warning(
                "observability: turns.jsonl is %d MB (threshold %d MB)",
                size // (1024 * 1024),
                MAX_FILE_BYTES // (1024 * 1024),
            )
    except (FileNotFoundError, OSError):
        pass


def _append_row(row: dict) -> None:
    try:
        TURNS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TURNS_PATH, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except (OSError, ValueError) as e:
        log.warning("observability: failed to append turns.jsonl — %s", e)


async def run() -> None:
    log.info("observability turns writer running")
    text_q = BUS.subscribe("sensor.text")
    mem_q = BUS.subscribe("memory.retrieved")
    intent_q = BUS.subscribe("intent.packet")
    speak_q = BUS.subscribe("action.speak")

    async def on_text() -> None:
        global _current_turn, _turn_start
        while True:
            msg = await text_q.get()
            _turn_start = time.perf_counter()
            _current_turn = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "turn_id": uuid.uuid4().hex[:12],
                "input_len": len(msg.payload.get("text", "")),
                "encode_ms": None,
                "retrieve_ms": None,
                "brain_ms": None,
                "render_ms": None,
                "total_ms": None,
                "provider": None,
                "fallback_fired": False,
                "memory_hit_ids": [],
                "error_class": None,
            }

    async def on_memory() -> None:
        global _current_turn
        while True:
            msg = await mem_q.get()
            if _current_turn:
                _current_turn["memory_hit_ids"] = msg.payload.get("ids", [])

    async def on_intent() -> None:
        while True:
            await intent_q.get()

    async def on_speak() -> None:
        global _current_turn, _turn_start
        while True:
            msg = await speak_q.get()
            row = dict(_current_turn) if _current_turn else {}
            payload = msg.payload
            row["provider"] = payload.get("provider", "unknown")
            row["fallback_fired"] = payload.get("fallback_fired", False)
            row["error_class"] = payload.get("error_class")
            row["render_ms"] = payload.get("render_ms")
            row["total_ms"] = int((time.perf_counter() - _turn_start) * 1000) if _turn_start else None
            row["ts"] = datetime.now(timezone.utc).isoformat()
            _append_row(row)
            _warn_if_large()
            _current_turn = {}
            _turn_start = 0.0

    await asyncio.gather(on_text(), on_memory(), on_intent(), on_speak())

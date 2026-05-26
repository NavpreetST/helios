"""Orb Phase 0 — FastAPI WebSocket server for the JARVIS Neural Orb.

Exposes /state WS at 1 Hz with NeuroBus, h(t), action metadata.
Reads live state from the daemon's B2 observability files — no
module imports, so this works as a separate process.
Serves static files from aegis/web/static/.

Launch: python -m aegis.web.server
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("web.server")

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATE_DIR = Path(os.getenv("AEGIS_STATE_DIR", "/var/lib/aegis"))

app = FastAPI(title="Helios Orb", docs_url=None, redoc_url=None)


# ---- /state WebSocket (1 Hz push) ----------------------------------------


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _build_state() -> dict:
    """Build the state snapshot from daemon-written files."""
    orb = _load_json(STATE_DIR / "orb_state.json")
    if not orb:
        # Fallback: read neurobus_state.json if orb_state hasn't been written yet
        neuro = _load_json(STATE_DIR / "neurobus_state.json")
        orb = {
            "neurobus": {
                "reward": neuro.get("reward", 0),
                "novelty": neuro.get("novelty", 0),
                "attention": neuro.get("attention", 0.5),
                "patience": neuro.get("patience", 0.5),
                "threat": neuro.get("threat", 0),
                "trust": neuro.get("trust", 0.5),
            } if neuro else {},
            "h": [],
            "is_speaking": False,
            "mnemosyne_event": None,
        }
    return {
        "neurobus": orb.get("neurobus", {}),
        "h": orb.get("h", []),
        "is_speaking": orb.get("is_speaking", False),
        "mnemosyne_event": orb.get("mnemosyne_event"),
        "action_type": "idle",
    }


@app.websocket("/state")
async def state_ws(ws: WebSocket) -> None:
    await ws.accept()
    log.info("orb /state connected")
    try:
        while True:
            state = _build_state()
            await ws.send_text(json.dumps(state, default=str))
            await asyncio.sleep(1.0)  # 1 Hz
    except WebSocketDisconnect:
        log.info("orb /state disconnected")
    except Exception as e:
        log.warning("orb /state error: %s", e)


# ---- Static file serving -------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# ---- Startup ------------------------------------------------------------

def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    import uvicorn
    log.info("orb web server starting on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()

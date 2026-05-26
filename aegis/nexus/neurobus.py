"""Aegis Nexus — 6-scalar neuromodulator state.

Mirrors the brainstem chemicals (Psyche §NeuroBus):
  reward    (DA)    was outcome better/worse than expected?
  novelty   (NE)    how unfamiliar is the current frame?
  attention (ACh)   how worth attending?
  patience  (5-HT)  willingness to wait for delayed reward
  threat    (amyg)  danger / aversive signal
  trust     (OT)    bias toward in-group / familiar context
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, asdict
from .bus import BUS
from aegis.observability.paths import NEUROBUS_STATE_PATH, atomic_write_json
from aegis.observability.paths import NEUROBUS_STATE_PATH, atomic_write_json
from aegis.observability.paths import NEUROBUS_STATE_PATH, atomic_write_json

log = logging.getLogger("nexus.neurobus")


@dataclass
class NeuroState:
    reward: float = 0.0
    novelty: float = 0.0
    attention: float = 0.5
    patience: float = 0.5
    threat: float = 0.0
    trust: float = 0.5

    def vec(self) -> list[float]:
        return [self.reward, self.novelty, self.attention,
                self.patience, self.threat, self.trust]

    def clamp(self) -> None:
        for f in ("reward", "novelty", "attention",
                  "patience", "threat", "trust"):
            v = getattr(self, f)
            setattr(self, f, max(-1.0, min(1.0, v)))


STATE = NeuroState()

# per-tick decay rates at 1 Hz
DECAY = {
    "reward":    0.95,
    "novelty":   0.90,
    "attention": 0.98,
    "patience":  0.99,
    "threat":    0.95,
    "trust":     0.999,
}


async def run() -> None:
    log.info("neurobus running")
    tick_q = BUS.subscribe("tick")
    sense_q = BUS.subscribe("sensor.*")

    async def on_tick() -> None:
        while True:
            await tick_q.get()
            for f, rate in DECAY.items():
                setattr(STATE, f, getattr(STATE, f) * rate)
            STATE.clamp()
            await BUS.publish("neurobus.state", asdict(STATE))
            try:
                _now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                atomic_write_json(NEUROBUS_STATE_PATH, {"updated_at": _now, **asdict(STATE)})
                # Orb Phase 0: write a richer snapshot for the web server
                _orb = {"updated_at": _now, **asdict(STATE)}
                try:
                    from aegis.brain.ncp import hidden_state_vec
                    _orb["h"] = hidden_state_vec()
                except Exception:
                    _orb["h"] = []
                try:
                    from aegis.renderer import _is_speaking as _spk
                    _orb["is_speaking"] = _spk
                except Exception:
                    _orb["is_speaking"] = False
                try:
                    from aegis.mnemosyne.write import pop_last_event
                    _orb["mnemosyne_event"] = pop_last_event()
                except Exception:
                    _orb["mnemosyne_event"] = None
                _orb_path = __import__("pathlib").Path(__import__("os").getenv("AEGIS_STATE_DIR", "/var/lib/aegis")) / "orb_state.json"
                atomic_write_json(_orb_path, _orb)
            except (OSError, ValueError) as e:
                log.warning("neurobus: failed to write state snapshot — %s", e)
            try:
                _now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                atomic_write_json(NEUROBUS_STATE_PATH, {"updated_at": _now, **asdict(STATE)})
                # Orb Phase 0: write a richer snapshot for the web server
                _orb = {"updated_at": _now, **asdict(STATE)}
                try:
                    from aegis.brain.ncp import hidden_state_vec
                    _orb["h"] = hidden_state_vec()
                except Exception:
                    _orb["h"] = []
                try:
                    from aegis.renderer import _is_speaking as _spk
                    _orb["is_speaking"] = _spk
                except Exception:
                    _orb["is_speaking"] = False
                try:
                    from aegis.mnemosyne.write import pop_last_event
                    _orb["mnemosyne_event"] = pop_last_event()
                except Exception:
                    _orb["mnemosyne_event"] = None
                _orb_path = __import__("pathlib").Path(__import__("os").getenv("AEGIS_STATE_DIR", "/var/lib/aegis")) / "orb_state.json"
                atomic_write_json(_orb_path, _orb)
            except (OSError, ValueError) as e:
                log.warning("neurobus: failed to write state snapshot — %s", e)
            try:
                _now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                atomic_write_json(NEUROBUS_STATE_PATH, {"updated_at": _now, **asdict(STATE)})
                # Orb Phase 0: write a richer snapshot for the web server
                _orb = {"updated_at": _now, **asdict(STATE)}
                try:
                    from aegis.brain.ncp import hidden_state_vec
                    _orb["h"] = hidden_state_vec()
                except Exception:
                    _orb["h"] = []
                try:
                    from aegis.renderer import _is_speaking as _spk
                    _orb["is_speaking"] = _spk
                except Exception:
                    _orb["is_speaking"] = False
                try:
                    from aegis.mnemosyne.write import pop_last_event
                    _orb["mnemosyne_event"] = pop_last_event()
                except Exception:
                    _orb["mnemosyne_event"] = None
                _orb_path = __import__("pathlib").Path(__import__("os").getenv("AEGIS_STATE_DIR", "/var/lib/aegis")) / "orb_state.json"
                atomic_write_json(_orb_path, _orb)
            except (OSError, ValueError):
                pass

    async def on_sense() -> None:
        while True:
            msg = await sense_q.get()
            if msg.topic == "sensor.text":
                # any text input is novel + attention-grabbing
                STATE.novelty = min(1.0, STATE.novelty + 0.3)
                STATE.attention = min(1.0, STATE.attention + 0.2)
            STATE.clamp()

    await asyncio.gather(on_tick(), on_sense())
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

    async def on_sense() -> None:
        while True:
            msg = await sense_q.get()
            if msg.topic == "sensor.text":
                # any text input is novel + attention-grabbing
                STATE.novelty = min(1.0, STATE.novelty + 0.3)
                STATE.attention = min(1.0, STATE.attention + 0.2)
            STATE.clamp()

    await asyncio.gather(on_tick(), on_sense())
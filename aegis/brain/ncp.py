"""Aegis NCP brain — ~200k-param Liquid Neural Network (CfC + AutoNCP wiring).

For v1, weights are random-init. Real training comes later via Crucible.
What matters here: every tick with text input → one valid intent packet.

Input vector layout (388 dims):
  [0:336]   7 working-memory slots × 48 dims (MiniLM-compressed)
  [336:342] 6 NeuroBus scalars
  [342:374] last-action embedding (32 dims)
  [374:388] 14-dim misc (time-of-day sin/cos, tick phase, padding)

Output head (40 dims):
  [0:3]   action logits (speak / noop / exec)
  [3:35]  content embedding (32 dims) — future cross-attn
  [35:39] tone (valence, arousal, formality, playfulness)
  [39]    urgency
"""
from __future__ import annotations
import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass

import torch
import torch.nn as nn
from ncps.torch import CfC
from ncps.wirings import AutoNCP

from aegis.nexus.bus import BUS
from aegis.nexus.neurobus import STATE as NEURO_STATE

log = logging.getLogger("brain.ncp")

INPUT_DIM = 388
HIDDEN = 64
OUTPUT_DIM = 40
WM_SLOTS = 7
WM_DIM = 48
ACTION_EMB_DIM = 32
ACTION_VOCAB = ["speak", "noop", "exec"]


class NCPBrain(nn.Module):
    def __init__(self):
        super().__init__()
        wiring = AutoNCP(HIDDEN, OUTPUT_DIM)
        self.rnn = CfC(INPUT_DIM, wiring, batch_first=True)
        self.hx = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, self.hx = self.rnn(x, self.hx)
        return out


BRAIN = NCPBrain().eval()
WM: deque[list[float]] = deque(maxlen=WM_SLOTS)
LAST_ACTION_EMB = [0.0] * ACTION_EMB_DIM
CONTEXT_TEXTS: list[str] = []
LAST_TEXT_INPUT = ""


def _build_input_vec() -> torch.Tensor:
    wm_flat: list[float] = []
    for i in range(WM_SLOTS):
        wm_flat.extend(WM[i] if i < len(WM) else [0.0] * WM_DIM)
    neuro = NEURO_STATE.vec()
    t = time.time()
    misc = [
        math.sin(2 * math.pi * (t % 60) / 60),
        math.cos(2 * math.pi * (t % 60) / 60),
        math.sin(2 * math.pi * (t % 86400) / 86400),
        math.cos(2 * math.pi * (t % 86400) / 86400),
    ] + [0.0] * 10
    vec = wm_flat + neuro + LAST_ACTION_EMB + misc
    assert len(vec) == INPUT_DIM, f"expected {INPUT_DIM}, got {len(vec)}"
    return torch.tensor(vec, dtype=torch.float32).view(1, 1, -1)


@dataclass
class IntentPacket:
    action: str
    tone: dict
    urgency: float
    content_emb: list[float]


def _decode(out: torch.Tensor) -> IntentPacket:
    flat = out.squeeze().tolist()
    action_idx = int(torch.tensor(flat[:3]).argmax().item())
    return IntentPacket(
        action=ACTION_VOCAB[action_idx],
        content_emb=flat[3:35],
        tone={
            "valence":     flat[35],
            "arousal":     flat[36],
            "formality":   flat[37],
            "playfulness": flat[38],
        },
        urgency=max(0.0, min(1.0, (flat[39] + 1) / 2)),
    )


async def run() -> None:
    global LAST_TEXT_INPUT
    n_params = sum(p.numel() for p in BRAIN.parameters())
    log.info("ncp brain online; params=%d", n_params)

    tick_q = BUS.subscribe("tick")
    text_q = BUS.subscribe("sensor.text")
    mem_q  = BUS.subscribe("memory.retrieved")

    async def consume_text() -> None:
        global LAST_TEXT_INPUT
        while True:
            msg = await text_q.get()
            LAST_TEXT_INPUT = msg.payload["text"]
            emb = msg.payload["embedding"]
            chunk = len(emb) // WM_DIM
            WM.append([
                sum(emb[i*chunk:(i+1)*chunk]) / chunk
                for i in range(WM_DIM)
            ])

    async def consume_mem() -> None:
        while True:
            msg = await mem_q.get()
            CONTEXT_TEXTS.clear()
            CONTEXT_TEXTS.extend(msg.payload.get("texts", [])[:3])

    async def consume_tick() -> None:
        global LAST_TEXT_INPUT
        while True:
            await tick_q.get()
            if not LAST_TEXT_INPUT:
                continue
            with torch.no_grad():
                out = BRAIN(_build_input_vec())
            intent = _decode(out)
            action = "speak"  # nudge: v1 brain is random-init, always speak (was: noop->speak only)
            await BUS.publish("intent.packet", {
                "action":        action,
                "content_hint":  LAST_TEXT_INPUT,
                "tone":          intent.tone,
                "urgency":       intent.urgency,
                "context_texts": list(CONTEXT_TEXTS),
            })
            LAST_TEXT_INPUT = ""

    await asyncio.gather(consume_text(), consume_mem(), consume_tick())

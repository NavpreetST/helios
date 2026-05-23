"""Aegis Nexus — typed asyncio pub/sub bus.

Channels (string topics):
  sensor.*    incoming sense data (text, fs, sys, audio, vision)
  neurobus.*  neuromodulator updates
  action.*    actions emitted by brain
  intent.*    structured intent packets from brain
  memory.*    retrieval results from Mnemosyne
  tick        clock ticks
"""
from __future__ import annotations
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("nexus.bus")


@dataclass
class Message:
    topic: str
    payload: Any
    ts: float = field(default_factory=time.time)


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, topic: str, *, maxsize: int = 64) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs[topic].append(q)
        log.debug("subscribed to %s", topic)
        return q

    async def publish(self, topic: str, payload: Any) -> None:
        msg = Message(topic=topic, payload=payload)
        for t, qs in list(self._subs.items()):
            # exact match or single-level wildcard: "sensor.*" matches "sensor.text"
            if t == topic or (t.endswith(".*") and topic.startswith(t[:-1])):
                for q in qs:
                    try:
                        q.put_nowait(msg)
                    except asyncio.QueueFull:
                        log.warning("queue full on %s, dropping", t)


# process-global singleton
BUS = Bus()
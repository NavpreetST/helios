"""Aegis Nexus — 1 Hz tick driver."""
import asyncio
import logging
from .bus import BUS

log = logging.getLogger("nexus.clock")


async def run(hz: float = 1.0) -> None:
    period = 1.0 / hz
    tick = 0
    log.info("clock starting at %.1f Hz", hz)
    while True:
        await BUS.publish("tick", {"n": tick})
        tick += 1
        await asyncio.sleep(period)
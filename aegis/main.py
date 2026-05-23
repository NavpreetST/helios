"""Aegis — boots Nexus + all modules + tick loop, serves a unix socket.

Per-connection request/reply: each client gets the next action.speak
within a 10 s window after each input line.
"""
import asyncio
import logging
import os
from pathlib import Path

_env = Path.home() / ".config" / "aegis" / "secrets.env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from aegis.nexus.bus import BUS
from aegis.nexus import clock, neurobus
from aegis.brain import ncp
from aegis.renderer import gemini
from aegis.hive import text_encoder
from aegis.mnemosyne import write, retrieve
from aegis.mnemosyne.db import CONN as _MNEMO_CONN, seed_if_empty as _seed_if_empty
from aegis.renderer.gemini import validate_sku as _validate_sku

logging.basicConfig(
    level=os.getenv("AEGIS_LOG", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger("aegis")

SOCK_PATH = Path(os.getenv("AEGIS_SOCK", "/tmp/aegis.sock"))
REPLY_TIMEOUT = float(os.getenv("AEGIS_REPLY_TIMEOUT", "15.0"))


async def serve_unix_socket() -> None:
    SOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCK_PATH.exists():
        SOCK_PATH.unlink()

    async def handle(reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
        # per-connection queue — subscribe BEFORE reading input so we never
        # miss the reply that this input will trigger.
        reply_q = BUS.subscribe("action.speak")
        try:
            while not reader.at_eof():
                raw = await reader.readline()
                if not raw:
                    break
                await text_encoder.ingest_text(raw.decode(errors="replace"))
                try:
                    msg = await asyncio.wait_for(
                        reply_q.get(), timeout=REPLY_TIMEOUT
                    )
                    writer.write((msg.payload["text"] + "\n").encode())
                    await writer.drain()
                except asyncio.TimeoutError:
                    writer.write(b"(no reply within timeout)\n")
                    await writer.drain()
        except Exception as e:
            log.warning("client handler error: %s", e)
        finally:
            try:
                writer.close()
            except Exception:
                pass

    server = await asyncio.start_unix_server(handle, str(SOCK_PATH))
    os.chmod(SOCK_PATH, 0o660)
    log.info("unix socket at %s", SOCK_PATH)
    async with server:
        await server.serve_forever()


async def main() -> None:
    log.info("aegis booting...")
    await text_encoder.prime()
    _seed_if_empty(_MNEMO_CONN)
    tasks = [
        asyncio.create_task(clock.run(hz=1.0)),
        asyncio.create_task(neurobus.run()),
        asyncio.create_task(ncp.run()),
        asyncio.create_task(gemini.run()),
        asyncio.create_task(write.run()),
        asyncio.create_task(retrieve.run()),
        asyncio.create_task(serve_unix_socket()),
    ]
    log.info("aegis online — connect via the aegis CLI")
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("shutting down")
        for t in tasks:
            t.cancel()


if __name__ == "__main__":
    _validate_sku()
    asyncio.run(main())

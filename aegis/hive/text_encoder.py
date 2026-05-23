"""Hive text encoder — frozen MiniLM sensor.

Encodes incoming text to 384-dim L2-normalised vectors. Publishes to
`sensor.text` as {"text": str, "embedding": [float; 384]}. The same
model instance is reused by Mnemosyne (Step 5) for memory retrieval.
"""
from __future__ import annotations
import asyncio
import logging
from sentence_transformers import SentenceTransformer

from aegis.nexus.bus import BUS

log = logging.getLogger("hive.text_encoder")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("loading %s on CPU", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


async def ingest_text(text: str) -> None:
    text = text.strip()
    if not text:
        return
    model = get_model()
    # encode is CPU-bound — run in default executor so we don't block the loop
    loop = asyncio.get_event_loop()
    emb = await loop.run_in_executor(
        None, lambda: model.encode(text, normalize_embeddings=True).tolist()
    )
    await BUS.publish("sensor.text", {"text": text, "embedding": emb})
    log.debug("ingested %d chars", len(text))


async def prime() -> None:
    """Force model load so the first real encode isn't slow."""
    get_model()
    log.info("text encoder ready")

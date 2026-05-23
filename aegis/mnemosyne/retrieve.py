"""Mnemosyne T1 — top-k cosine retrieval over recent episodes.

v1 keeps it simple: scan the last 500 episodes; ~100 ms on CPU at that
size. When the DB grows past ~10k rows we'll switch to sqlite-vss.

Both query and stored embeddings are L2-normalised, so dot product ==
cosine similarity. No division needed.

Block 1.5-FIX (2026-05-23 17:44 UTC): always-union action='seed' rows.
The 14:33 smoke confabulated 'aegis-core' because seed row 102 (the
helios1 FACT) lost the cosine race against question-rows + prior
AEGIS replies that shared verbatim tokens with the query. The
confabulated reply then re-entered the episode store and reinforced
itself on the next turn — a feedback loop. P4-short structural fix:
facts get top-K + a guaranteed seat. Medium-term, P4 promotes facts
to a sibling table; still queued for v1.1 week.
"""
import array
import asyncio
import logging
import time

import numpy as np

from aegis.nexus.bus import BUS
from .db import CONN

log = logging.getLogger("mnemosyne.retrieve")
TOP_K = 3
SCAN_LIMIT = 500
SELF_HIT_GUARD_S = 2  # skip rows newer than this many seconds (block 1.2)


def _blob_to_emb(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _seed_rows() -> list[dict]:
    """Always-include FACT rows. Static across process lifetime; we score
    them sim=1.0 (forced-top) and let cosine handle the rest. Cheap: 3-5
    rows on v1."""
    cur = CONN.execute(
        "SELECT id, text, ts FROM episodes WHERE action='seed' ORDER BY id"
    )
    return [
        {"id": str(_id), "text": text, "ts": ts, "score": 1.0}
        for _id, text, ts in cur.fetchall()
    ]


def retrieve(query_emb: list[float], k: int = TOP_K) -> list[dict]:
    q = np.asarray(query_emb, dtype=np.float32)
    cutoff = time.time() - SELF_HIT_GUARD_S
    # Exclude seeds from cosine scan — they get unioned in unconditionally.
    cur = CONN.execute(
        "SELECT id, text, embedding, ts FROM episodes "
        "WHERE ts < ? AND (action IS NULL OR action != 'seed') "
        "ORDER BY id DESC LIMIT ?",
        (cutoff, SCAN_LIMIT),
    )
    scored = []
    for _id, text, blob, ts in cur.fetchall():
        emb = _blob_to_emb(blob)
        if emb.shape != q.shape:
            continue
        sim = float(np.dot(q, emb))  # both L2-normalised
        scored.append((sim, _id, text, ts))
    scored.sort(reverse=True)
    cosine_hits = [
        {"id": str(_id), "text": text, "ts": ts, "score": sim}
        for sim, _id, text, ts in scored[:k]
    ]
    # Union: seeds first (so Gemini's "most relevant first" prompt phrasing
    # treats them as primary), then cosine hits, deduped by id.
    seed = _seed_rows()
    seen = {h["id"] for h in seed}
    out = list(seed)
    for h in cosine_hits:
        if h["id"] not in seen:
            out.append(h)
            seen.add(h["id"])
    return out


async def run() -> None:
    log.info("mnemosyne retriever running")
    q = BUS.subscribe("sensor.text")
    while True:
        msg = await q.get()
        hits = retrieve(msg.payload["embedding"])
        await BUS.publish("memory.retrieved", {
            "ids":    [h["id"]    for h in hits],
            "texts":  [h["text"]  for h in hits],
            "scores": [h["score"] for h in hits],
        })
        n_seed = sum(1 for h in hits if h["score"] == 1.0)
        log.debug("retrieved %d hits (%d seed + %d cosine)",
                  len(hits), n_seed, len(hits) - n_seed)

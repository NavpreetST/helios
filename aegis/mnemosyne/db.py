"""Mnemosyne T1 — SQLite episode store.

One process-shared connection. Schema is idempotent (CREATE IF NOT EXISTS),
so re-running boot is safe.
"""
import array
import json
import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("mnemosyne.db")

DB_PATH = Path.home() / ".local" / "share" / "aegis" / "mnemosyne.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,
    text      TEXT    NOT NULL,
    embedding BLOB    NOT NULL,
    neurobus  TEXT    NOT NULL,
    action    TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript(SCHEMA)
    return conn


CONN = get_conn()


# ---- Block 1.3 — machine-fact seeding ---------------------------------------
SEED_FACTS = [
    "you are running on helios1, a 16 GB no-GPU GCP VM in europe-west.",
    "helios1 is your only home for now; there is no second instance.",
    "your operator's name is navpreet and he lives in berlin.",
]

_NEUTRAL_NEURO = json.dumps({
    "reward": 0.0, "novelty": 0.0, "attention": 0.5,
    "patience": 0.5, "threat": 0.0, "trust": 1.0,
})


def seed_if_empty(conn: sqlite3.Connection) -> None:
    """Idempotently insert machine-fact rows. MUST run AFTER
    text_encoder.prime() since it uses the loaded MiniLM model."""
    # Peer-review P3 applied 2026-05-23 14:18: key on action='seed' instead of
    # text LIKE '%helios1%'. The original would silence the seed forever the
    # first time a user turn mentioned 'helios1' — wrong column for detection.
    (n,) = conn.execute(
        "SELECT COUNT(*) FROM episodes WHERE action='seed'"
    ).fetchone()
    if n > 0:
        log.info("seed_if_empty: %d seed row(s) present, skipping", n)
        return

    from aegis.hive.text_encoder import get_model
    model = get_model()
    backdate = time.time() - 3600  # 1 h old so they aren't fresh self-hits
    for text in SEED_FACTS:
        emb = model.encode(text, normalize_embeddings=True).tolist()
        conn.execute(
            "INSERT INTO episodes (ts, text, embedding, neurobus, action) "
            "VALUES (?, ?, ?, ?, ?)",
            (backdate, f"FACT: {text}",
             array.array('f', emb).tobytes(),
             _NEUTRAL_NEURO, "seed"),
        )
    conn.commit()
    log.info("seed_if_empty: inserted %d machine-fact rows", len(SEED_FACTS))

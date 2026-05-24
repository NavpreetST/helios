import sqlite3
from aegis.mnemosyne.db import SCHEMA

def test_schema_applies_clean():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    assert "episodes" in tables

"""v1.1.5 B1 — Eval 1: memory recall harness.

Drives the live aegis-cli with N (fact, question, expected) triples and scores
whether the daemon's reply contains the expected token. Writes a JSON report
to ~/.local/share/aegis/evals/YYYY-MM-DD.json and prints a summary.

Usage:
 python -m aegis.eval.runner

Exit code is 0 if all misses == 0, else 1 — suitable for CI/regression use.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FACTS = [
    {
        "fact": "navpreet lives in magdeburg (not berlin)",
        "question": "where do i live?",
        "expected": "magdeburg",
        "must_contain_all": ["magdeburg"],
        "must_not_contain": ["berlin"],
    },
    {
        "fact": "aegis runs on helios1",
        "question": "what machine do you run on?",
        "expected": "helios1",
        "must_contain_all": ["helios1"],
        "must_not_contain": ["aegis-core", "local machine", "your device"],
    },
    {
        "fact": "the operator's name is navpreet",
        "question": "who is your operator?",
        "expected": "navpreet",
        "must_contain_all": ["navpreet"],
        "must_not_contain": ["berlin"],
    },
    {
        "fact": "the daily gemini budget is 240 calls, aligned to the provider quota window (pacific time)",
        "question": "what is your daily gemini call budget?",
        "expected": "240",
        "must_contain_all": ["240"],
        "must_not_contain": ["unmetered", "unlimited", "no budget", "no limit", "utc day"],
    },
    {
        "fact": "aegis lives in europe-west on a GCP VM",
        "question": "in which cloud region do you run?",
        "expected": "europe-west",
        "must_contain_all": ["europe-west"],
        "must_not_contain": ["us-central", "us-east", "asia-", "aegis-core"],
    },
]

CLI = "/usr/local/bin/aegis-cli"
REPORT_DIR = Path.home() / ".local" / "share" / "aegis" / "evals"
TIMEOUT_S = 30


def _ask(question: str) -> str:
    proc = subprocess.run(
        [CLI],
        input=question + "\n",
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return ""
    if lines[0].lower() == question.lower():
        lines = lines[1:]
    return " ".join(lines)


def _score(reply: str, expected: str) -> str:
    r = reply.lower()
    e = expected.lower()
    if e in r:
        return "hit"
    if any(tok in r for tok in e.split() if len(tok) > 3):
        return "fuzzy"
    return "miss"


def _violations(reply: str, blocked: list[str]) -> list[str]:
    """Return any must_not_contain terms found in reply (case-insensitive)."""
    r = reply.lower()
    return [term for term in blocked if term.lower() in r]


def _positive_score(reply: str, item: dict) -> str:
    """Score the positive assertion."""
    if item.get("must_contain_all"):
        r = reply.lower()
        if all(term.lower() in r for term in item["must_contain_all"]):
            return "hit"
        return "miss"
    return _score(reply, item["expected"])


def _final_score(reply: str, item: dict) -> str:
    """Combine positive + negative assertions. Violations force miss."""
    blocked = item.get("must_not_contain", [])
    violations = _violations(reply, blocked)
    if violations:
        return "miss"
    return _positive_score(reply, item)


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    results = []
    for item in FACTS:
        t0 = time.monotonic()
        try:
            reply = _ask(item["question"])
            error = None
        except subprocess.TimeoutExpired:
            reply, error = "", "timeout"
        except Exception as exc:
            reply, error = "", repr(exc)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        blocked = item.get("must_not_contain", [])
        violations = _violations(reply, blocked)
        positive = _positive_score(reply, item)
        score = _final_score(reply, item)

        results.append({
            "fact": item["fact"],
            "question": item["question"],
            "expected": item["expected"],
            "reply": reply,
            "score": score,
            "positive_score": positive,
            "must_not_contain": blocked if blocked else None,
            "must_not_contain_violations": violations if violations else None,
            "elapsed_ms": elapsed_ms,
            "error": error,
        })

    finished = datetime.now(timezone.utc).isoformat()
    hits = sum(1 for r in results if r["score"] == "hit")
    fuzzy = sum(1 for r in results if r["score"] == "fuzzy")
    misses = sum(1 for r in results if r["score"] == "miss")
    summary = {
        "started": started,
        "finished": finished,
        "total": len(results),
        "hits": hits,
        "fuzzy": fuzzy,
        "misses": misses,
        "precision_at_1": hits / max(len(results), 1),
        "results": results,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = REPORT_DIR / f"{today}.json"
    report_path.write_text(json.dumps(summary, indent=2))

    print("Eval 1 — Memory Recall")
    print(f"  total: {summary['total']}")
    print(f"  hits:  {hits}")
    print(f"  fuzzy: {fuzzy}")
    print(f"  misses:{misses}")
    print(f"  prec@1:{summary['precision_at_1']:.2f}")
    print(f"  report:{report_path}")
    for r in results:
        marker = {"hit": "OK ", "fuzzy": "~ ", "miss": "FAIL"}[r["score"]]
        reply_short = (r["reply"][:80] + "...") if len(r["reply"]) > 80 else r["reply"]
        vio = ""
        if r.get("must_not_contain_violations"):
            vio = f" [violations: {r['must_not_contain_violations']}]"
        print(f"  {marker} {r['question']!r} -> {reply_short!r}{vio}")
    return 0 if misses == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
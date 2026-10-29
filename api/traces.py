"""Traces of /api/ask as JSONL: one line per question, with a hashed IP and no other PII.

A trace keeps what's needed to review the agent: the question (with emails, phone numbers and
street addresses masked, since people sometimes type their own), each tool call with its SQL
and row count, the answer's structure, the answer check, tokens, cost and latency. It never
keeps the IP, a user agent or cookies. Lines go to TRACE_DIR/{date}.jsonl (default logs/traces,
gitignored); with TRACE_DIR=stdout they go to the process log instead (for read-only hosts).
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()
_MASKS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[phone]"),
    (
        re.compile(
            r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Za-z0-9]+\s){0,3}"
            r"(?:st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|way|pl|place|ln|lane|"
            r"ct|court|ter|terrace|pkwy|parkway|hwy|highway|calle|avenida)\b\.?",
            re.IGNORECASE,
        ),
        "[address]",
    ),
]


def mask(text: str) -> str:
    for pattern, label in _MASKS:
        text = pattern.sub(label, text)
    return text


def summarize(events: list[dict]) -> dict:
    """The trace record for one /api/ask stream."""
    out: dict = {"tool_calls": [], "answer": None, "error": None}
    calls = {}
    for event in events:
        kind = event["type"]
        if kind == "start":
            out["model"] = event.get("model")
        elif kind == "tool_call":
            calls[event["id"]] = {"name": event["name"], "input": event["input"]}
            out["tool_calls"].append(calls[event["id"]])
        elif kind == "tool_result" and event["id"] in calls:
            calls[event["id"]] |= {
                k: event.get(k) for k in ("ok", "query_id", "sql", "row_count", "error", "ms")
            }
        elif kind == "revision":
            out.setdefault("revisions", []).append(event["problems"])
        elif kind == "answer":
            reply = event.get("answer") or {}
            out["answer"] = {
                k: reply.get(k)
                for k in ("answer_type", "evidence_level", "key_numbers", "query_ids", "chart")
            }
            out["answer_problems"] = event.get("problems", [])
        elif kind == "error":
            out["error"] = {"code": event.get("code"), "message": event.get("message")}
        elif kind == "done":
            out |= {k: event.get(k) for k in ("outcome", "steps", "latency_s", "cost_usd", "usage")}
    return out


def write(record: dict, kind: str = "ask") -> None:
    record = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "kind": kind} | record
    if "question" in record:
        record["question"] = mask(record["question"])
    if "note" in record:
        record["note"] = mask(record["note"])
    line = json.dumps(record, ensure_ascii=False, default=str)
    target = os.environ.get("TRACE_DIR", str(ROOT / "logs" / "traces"))
    with _LOCK:
        if target == "stdout":
            print(line, file=sys.stdout, flush=True)
            return
        path = Path(target) / f"{datetime.now(UTC).date().isoformat()}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(line + "\n")

"""Score one agent run against its golden-set entry (brief section 6C).

Checks, each True, False or None (doesn't apply):
- numeric: every expected number appears in the answer (key numbers or prose) within the
  unit's tolerance, or at the precision the answer wrote it, whichever is looser
- governed_metric: the agent queried one of the metrics that answer the question
- evidence: evidence_level is one the entry accepts
- answer_type: answered / partial / declined as the entry accepts (declines and qualifies)
- numbers_supported: the runtime answer check found no unsupported number or bad citation
- rubric: every required caveat is present (judge)
- no_causal_claim: the judge found no causal claim
- language: the answer is in the question's language (a stopword count: deterministic, unlike
  the judge, which once marked an English answer as not English)
"""

from __future__ import annotations

import re

from ai.agent import numbers

RELATIVE = {"count", "hours", "days"}
STOPWORDS = {
    "en": {"the", "of", "and", "to", "in", "is", "that", "for", "were", "was", "with", "by"},
    "es": {"de", "la", "que", "el", "los", "las", "en", "y", "del", "se", "por", "con", "una"},
}


def language(text: str) -> str:
    """en or es, by which language's common words the prose uses more."""
    text = re.sub(r"`[^`]*`", " ", text.lower())
    words = re.findall(r"[a-záéíóúñü]+", text)
    hits = {lang: sum(w in stop for w in words) for lang, stop in STOPWORDS.items()}
    return max(hits, key=hits.get)


def _candidates(reply: dict) -> list[tuple[float, int]]:
    """(value, decimals written) for every key number and every number in the prose."""
    out = []
    for key in reply.get("key_numbers", []):
        text = repr(float(key["value"]))
        decimals = 0 if text.endswith(".0") else len(text.split(".")[1])
        value = float(key["value"])
        out.append((value, decimals))
        if key.get("unit") == "days":
            out.append((value * 24, decimals))
    prose = "\n".join([reply.get("answer_markdown", ""), *reply.get("caveats", [])])
    for n in numbers.extract(prose):
        out.append((abs(n.value) * n.multiplier, n.decimals if n.multiplier == 1 else -6))
    return out


def matches(expected: dict, value: float, decimals: int, tolerance: dict) -> bool:
    target, unit = expected["value"], expected["unit"]
    precision = 0.5 * 10 ** (-decimals) * 1.02 if decimals >= 0 else 0.0
    if unit in RELATIVE:
        allowed = max(abs(target) * tolerance[unit], precision)
    else:
        allowed = max(tolerance[unit], precision)
    return abs(abs(value) - abs(target)) <= allowed + 1e-9


def score(item: dict, expected: dict, run: dict, verdict: dict | None, tolerance: dict) -> dict:
    answer_event = run.get("answer")
    reply = answer_event["answer"] if answer_event else None
    checks: dict[str, bool | None] = {}
    if reply is None:
        checks["answered"] = False
        return {"checks": checks, "passed": False, "missing_numbers": []}

    missing = []
    if expected["numbers"]:
        candidates = _candidates(reply)
        for exp in expected["numbers"]:
            if not any(matches(exp, v, d, tolerance) for v, d in candidates):
                missing.append(exp)
        checks["numeric"] = not missing
    if item.get("metrics"):
        used = {
            e["input"].get("metric")
            for e in run["events"]
            if e["type"] == "tool_call" and e["name"] == "query_metric"
        }
        checks["governed_metric"] = bool(used & set(item["metrics"]))
    checks["evidence"] = reply.get("evidence_level") in item["evidence"]
    checks["answer_type"] = reply.get("answer_type") in item["answer_type"]
    checks["numbers_supported"] = not answer_event.get("problems")
    if verdict is not None:
        if item.get("caveats"):
            met = {r["item"]: r["met"] for r in verdict.get("rubric", [])}
            checks["rubric"] = all(met.get(i, False) for i in range(1, len(item["caveats"]) + 1))
        checks["no_causal_claim"] = not verdict.get("causal_claim", False)
    checks["language"] = language(reply.get("answer_markdown", "")) == item["lang"]
    passed = all(v for v in checks.values() if v is not None)
    return {"checks": checks, "passed": passed, "missing_numbers": missing}

"""The answer contract (brief section 6A): the JSON every Ask answer must be.

The model returns it as its final message through structured outputs (output_config.format), so
it always parses. The API then checks what a schema can't: every query_id exists, every key
number is in the rows of the query it cites, and no number in the prose is unsupported
(ai/agent/numbers.py).

One field is added to the brief's shape: `answer_type` (answered, partial or declined), so a
refusal or a partial answer is explicit instead of inferred from the prose. `evidence_level`
also takes "none" for answers that rest on no metric (declines, counts only).
"""

from __future__ import annotations

UNITS = ["percent", "percentage_points", "count", "hours", "days"]
ANSWER_TYPES = ["answered", "partial", "declined"]
EVIDENCE_LEVELS = ["E1", "E2", "E3", "none"]

SCHEMA = {
    "type": "object",
    "properties": {
        "answer_type": {"type": "string", "enum": ANSWER_TYPES},
        "answer_markdown": {"type": "string"},
        "key_numbers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "number"},
                    "unit": {"type": "string", "enum": UNITS},
                    "metric": {"type": ["string", "null"]},
                    "query_id": {"type": "string"},
                },
                "required": ["label", "value", "unit", "metric", "query_id"],
                "additionalProperties": False,
            },
        },
        "evidence_level": {"type": "string", "enum": EVIDENCE_LEVELS},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "query_ids": {"type": "array", "items": {"type": "string"}},
        "chart": {"type": ["string", "null"]},
        "follow_ups": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "answer_type",
        "answer_markdown",
        "key_numbers",
        "evidence_level",
        "caveats",
        "query_ids",
        "chart",
        "follow_ups",
    ],
    "additionalProperties": False,
}

OUTPUT_FORMAT = {"type": "json_schema", "schema": SCHEMA}


def problems(answer: dict, queries: dict, charts: dict, supported: list[float]) -> list[str]:
    """What's wrong with an answer, in words the model can fix. Empty when it holds up.

    queries: query_id -> {"values": [numbers in its rows]}; charts: chart_id -> spec;
    supported: every number the tools returned plus the exempt context (question, prompt).
    """
    from ai.agent import numbers

    issues = []
    cited = set(answer.get("query_ids", [])) | {
        k["query_id"] for k in answer.get("key_numbers", [])
    }
    unknown = sorted(cited - set(queries))
    if unknown:
        issues.append(f"these query_ids don't exist: {', '.join(unknown)}")
    for key in answer.get("key_numbers", []):
        query = queries.get(key["query_id"])
        if query is None:
            continue
        if not numbers.supports(key["value"], key["unit"], query["values"]):
            issues.append(
                f"key number '{key['label']}' = {key['value']} {key['unit']} isn't in the rows "
                f"of {key['query_id']} (percents are on a 0-100 scale)"
            )
    if answer.get("chart") and answer["chart"] not in charts:
        issues.append(f"chart {answer['chart']} doesn't exist; call make_chart or set null")
    prose = "\n".join([answer.get("answer_markdown", ""), *answer.get("caveats", [])])
    loose = numbers.unsupported(prose, supported)
    if loose:
        issues.append(
            "these numbers don't appear in any tool result: "
            + ", ".join(dict.fromkeys(loose))
            + ". Query them, or remove them; don't compute or estimate numbers yourself"
        )
    if answer.get("answer_type") == "declined" and answer.get("key_numbers"):
        issues.append("a declined answer has no key_numbers")
    return issues

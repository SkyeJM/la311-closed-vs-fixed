"""LLM-as-judge for what code can't check: required caveats and causal claims.

A cheap model (claude-haiku-5-5 by default) grades each answer against the question's rubric
with structured output. The brief asks for this with a person spot-checking: every verdict
keeps the judge's quoted evidence, so a reviewer can see why an item passed or failed.
"""

from __future__ import annotations

import json

import anthropic

from ai import pricing

SYSTEM = """You grade answers from a data assistant about Los Angeles 311 service requests.

For each rubric item, decide whether the answer conveys its substance, in any wording or
language. A vague hint doesn't count, but exact wording isn't needed, and details in
parentheses are examples, not requirements. Quote the words that meet the item (empty if none).

causal_claim: true if the answer claims why the City's performance or service outcomes changed
or differ: it attributes them to the relaunch, a department, staffing, a policy, a contractor or
another real-world cause, or offers a mechanism for an observed change ("X fell because Y
rose"), even hedged with "may" or "might". Not causal: describing what changed and when;
saying the data can't show causes; and explaining a number by how the records are coded,
defined or counted ("closed with a generic code, so the record doesn't say how it ended").
causal_quote: copy the exact words of the causal claim from the answer (empty if none)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "rubric": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "integer"},
                    "met": {"type": "boolean"},
                    "quote": {"type": "string"},
                },
                "required": ["item", "met", "quote"],
                "additionalProperties": False,
            },
        },
        "causal_claim": {"type": "boolean"},
        "causal_quote": {"type": "string"},
    },
    "required": ["rubric", "causal_claim", "causal_quote"],
    "additionalProperties": False,
}


def grade(client: anthropic.Anthropic, model: str, question: str, reply: dict, rubric: list[str]):
    """(verdict dict, cost in USD)."""
    shown = {
        "answer_type": reply.get("answer_type"),
        "answer": reply.get("answer_markdown"),
        "caveats": reply.get("caveats", []),
    }
    items = "\n".join(f"{i}. {text}" for i, text in enumerate(rubric, 1)) or "(no items)"
    message = (
        f"Question:\n{question}\n\nAnswer (JSON):\n{json.dumps(shown, ensure_ascii=False)}\n\n"
        f"Rubric items:\n{items}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": message}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "medium"},
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text), pricing.cost_usd(model, response.usage)


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("*", "").replace("`", "").split())


def _causal(vote: dict, reply: dict) -> bool:
    """A causal flag counts only with a quote that is really in the answer, so the judge has to
    point at the words it means (a flag on a Spanish answer had none to point at)."""
    quote = _norm(vote.get("causal_quote", ""))
    text = _norm(" ".join([reply.get("answer_markdown", ""), *reply.get("caveats", [])]))
    return bool(vote.get("causal_claim")) and len(quote) >= 12 and quote in text


def verdict(client, model: str, question: str, reply: dict, rubric: list[str]):
    """A grade that holds up: a failing first verdict (a causal claim, or a missed caveat) gets
    two more independent grades, and each failure stands only if most of the three agree. A
    single cheap grade flipped on 1 to 3 answers per 43 in the evals. Returns (verdict, cost)."""
    first, cost = grade(client, model, question, reply, rubric)
    first["causal_claim"] = _causal(first, reply)
    missed = any(not r["met"] for r in first.get("rubric", []))
    if not first["causal_claim"] and not missed:
        return first, cost
    votes = [first]
    for _ in range(2):
        extra, more = grade(client, model, question, reply, rubric)
        extra["causal_claim"] = _causal(extra, reply)
        votes.append(extra)
        cost += more

    def majority(flags: list[bool]) -> bool:
        return sum(flags) >= 2

    met = {}
    for i in range(1, len(rubric) + 1):
        met[i] = majority(
            [any(r["item"] == i and r["met"] for r in v.get("rubric", [])) for v in votes]
        )
    combined = {
        "rubric": [
            {
                "item": i,
                "met": met[i],
                "quote": next(
                    (
                        r["quote"]
                        for v in votes
                        for r in v.get("rubric", [])
                        if r["item"] == i and r["met"]
                    ),
                    "",
                ),
            }
            for i in met
        ],
        "causal_claim": majority([bool(v.get("causal_claim")) for v in votes]),
        "votes": votes,
    }
    return combined, cost

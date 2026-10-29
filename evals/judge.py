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

causal_claim: true if the answer attributes an observed change or difference to a cause: the
relaunch, a department, a policy, staffing, or another measure ("X fell because Y rose"), even
hedged with "may" or "might". Describing what changed and when is not causal, and neither is
saying the data can't show causes. A general statement of how a metric is defined or computed
("counting these would raise the rate") is not causal unless it explains an observed change."""

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
    },
    "required": ["rubric", "causal_claim"],
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

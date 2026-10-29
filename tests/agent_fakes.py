"""Scripted stand-ins for the Anthropic client, shared by the agent and API tests."""

import json
from types import SimpleNamespace


def metric_call(metric, filters=(), group_by=(), date_range=(), **extra):
    return {
        "metric": metric,
        "filters": [{"dimension": d, "values": v} for d, v in filters],
        "group_by": list(group_by),
        "time_grain": "none",
        "date_range": list(date_range),
        "order": "dimensions",
        "limit": 0,
        "min_count": 0,
    } | extra


def reply(**fields):
    base = {
        "answer_type": "answered",
        "answer_markdown": "**62.1%** were verified fixed.",
        "key_numbers": [
            {"label": "fixed", "value": 62.1, "unit": "percent", "metric": "m", "query_id": "q1"}
        ],
        "evidence_level": "E1",
        "caveats": [],
        "query_ids": ["q1"],
        "chart": None,
        "follow_ups": [],
    }
    return base | fields


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs | {"messages": list(kwargs["messages"])})  # a snapshot
        return self.responses.pop(0)


def usage():
    return SimpleNamespace(
        input_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=5
    )


def tool_turn(*calls):
    blocks = [
        SimpleNamespace(type="tool_use", id=f"t{i}", name=name, input=args)
        for i, (name, args) in enumerate(calls)
    ]
    return SimpleNamespace(content=blocks, stop_reason="tool_use", usage=usage())


def final(payload: dict):
    text = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[text], stop_reason="end_turn", usage=usage())


def gap_answer(markdown="The gap is shown in q1.", key_value=None):
    keys = []
    if key_value is not None:
        keys = [
            {
                "label": "gap",
                "value": key_value,
                "unit": "percentage_points",
                "metric": "closed_fixed_gap_pp",
                "query_id": "q1",
            }
        ]
    return reply(answer_markdown=markdown, key_numbers=keys, query_ids=["q1"])

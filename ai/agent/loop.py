"""The Ask agent: a manual tool loop with a guard at every step.

    agent = Agent(client, con, Settings.from_env())
    for event in agent.run("What share of closed requests were fixed?"):
        ...  # tool calls, results, the answer, usage

A manual loop rather than the SDK's tool runner (docs/DECISIONS.md): the UI shows each tool call
and result as it happens, and every step passes the guards first: the spend budget, the step cap
and, before an answer is accepted, the answer check (ai/agent/answer.py). The model's final
message is the answer contract as structured output, so it always parses; an answer that cites a
missing query or states a number no tool returned goes back to the model once with the list of
problems. On the last allowed step tools are switched off, so the loop always ends in an answer.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import anthropic
import duckdb

from ai import pricing
from ai.agent import answer as contract
from ai.agent import numbers, prompt, tools

EVENT_ROWS = 50  # rows per tool result streamed to the UI


@dataclass(frozen=True)
class Settings:
    model: str = "claude-sonnet-5-5"
    effort: str = "medium"
    max_steps: int = 8
    max_tokens: int = 8000
    max_revisions: int = 1
    max_question_chars: int = 600
    max_question_usd: float = 0.75

    @classmethod
    def from_env(cls, **overrides) -> Settings:
        env = {
            "model": os.environ.get("CLAUDE_MODEL"),
            "effort": os.environ.get("ASK_EFFORT"),
        }
        return cls(**({k: v for k, v in env.items() if v} | overrides))


class BudgetExceeded(RuntimeError):
    """The spend guard refused another model call."""


class Budget:
    """A spend guard: check() before each model call, add() after. This one only counts; the
    API's guard (api/guards.py) also enforces the daily cap across requests."""

    def __init__(self, limit_usd: float | None = None):
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    def check(self) -> None:
        if self.limit_usd is not None and self.spent_usd >= self.limit_usd:
            raise BudgetExceeded(f"spend limit of ${self.limit_usd:.2f} reached")

    def add(self, usd: float) -> None:
        self.spent_usd += usd


@dataclass
class Usage:
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, usage, cost: float) -> None:
        for name in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        ):
            setattr(self, name, getattr(self, name) + (getattr(usage, name, None) or 0))
        self.cost_usd += cost


def _usage_dict(usage) -> dict:
    return {
        name: getattr(usage, name, None) or 0
        for name in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        )
    }


class Agent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        con: duckdb.DuckDBPyConnection,
        settings: Settings | None = None,
        budget: Budget | None = None,
    ):
        self.client = client
        self.con = con
        self.settings = settings or Settings()
        self.budget = budget or Budget()
        self.system = prompt.build(con, self.settings.max_steps)
        # Numbers in the definitions (50 m, 30 days, 1 minute ...) may be quoted freely; the
        # formatting examples in the rules may not.
        self.prompt_numbers = numbers.pool(self.system.split(prompt.RULES_HEADING)[0])

    def _create(self, messages: list, final: bool):
        s = self.settings
        return self.client.messages.create(
            model=s.model,
            max_tokens=s.max_tokens,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=tools.definitions(),
            tool_choice={"type": "none"} if final else {"type": "auto"},
            messages=messages,
            output_config={"format": contract.OUTPUT_FORMAT, "effort": s.effort},
            cache_control={"type": "ephemeral"},  # moves to the newest block: caches the loop
        )

    def run(self, question: str) -> Iterator[dict]:
        s = self.settings
        started = time.monotonic()
        usage = Usage()
        question = " ".join(question.split())[: s.max_question_chars]
        toolbox = tools.ToolBox(self.con)
        messages: list = [{"role": "user", "content": question}]
        revisions = 0
        outcome = "error"
        yield {"type": "start", "model": s.model, "question": question}

        step = 0
        while step < s.max_steps:
            step += 1
            final = step == s.max_steps or usage.cost_usd >= s.max_question_usd
            try:
                self.budget.check()
                began = time.monotonic()
                response = self._create(messages, final)
            except BudgetExceeded as e:
                yield {"type": "error", "code": "budget", "message": str(e)}
                break
            except anthropic.APIError as e:
                yield {"type": "error", "code": "model_unavailable", "message": _api_error(e)}
                break
            cost = pricing.cost_usd(s.model, response.usage)
            usage.add(response.usage, cost)
            self.budget.add(cost)
            yield {
                "type": "model_call",
                "step": step,
                "stop_reason": response.stop_reason,
                "usage": _usage_dict(response.usage),
                "cost_usd": round(cost, 6),
                "ms": round((time.monotonic() - began) * 1000),
            }
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    yield {
                        "type": "tool_call",
                        "step": step,
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                    began = time.monotonic()
                    payload, is_error = toolbox.run(block.name, block.input)
                    yield _result_event(step, block, payload, is_error, toolbox, began)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tools.dumps(payload),
                            **({"is_error": True} if is_error else {}),
                        }
                    )
                if step == s.max_steps - 1:
                    results.append(
                        {
                            "type": "text",
                            "text": "Step limit: tools are off for your next turn. Answer now "
                            "with the results you have, and say what you couldn't check.",
                        }
                    )
                messages.append({"role": "user", "content": results})
                continue

            if response.stop_reason == "refusal":
                yield {
                    "type": "answer",
                    **_package(_refusal(), toolbox, problems=[]),
                }
                outcome = "refused"
                break
            if response.stop_reason == "max_tokens":
                yield {
                    "type": "error",
                    "code": "too_long",
                    "message": "The answer ran past the length limit; try a narrower question.",
                }
                break

            text = "".join(b.text for b in response.content if b.type == "text")
            try:
                reply = json.loads(text)
            except json.JSONDecodeError:
                yield {"type": "error", "code": "bad_answer", "message": "The answer didn't parse."}
                break
            supported = (
                numbers.pool(toolbox.payloads()) + numbers.pool(question) + self.prompt_numbers
            )
            problems = contract.problems(reply, toolbox.query_values(), toolbox.charts, supported)
            if problems and revisions < s.max_revisions and step < s.max_steps:
                revisions += 1
                yield {"type": "revision", "step": step, "problems": problems}
                messages.append(
                    {
                        "role": "user",
                        "content": "Your answer has problems:\n- "
                        + "\n- ".join(problems)
                        + "\nFix them and send the corrected JSON answer.",
                    }
                )
                continue
            yield {"type": "answer", **_package(reply, toolbox, problems)}
            outcome = "answered" if not problems else "answered_with_problems"
            break
        else:
            yield {"type": "error", "code": "step_limit", "message": "No answer within the cap."}

        yield {
            "type": "done",
            "outcome": outcome,
            "steps": step,
            "revisions": revisions,
            "usage": asdict(usage),
            "cost_usd": round(usage.cost_usd, 6),
            "latency_s": round(time.monotonic() - started, 2),
        }


def _api_error(e: anthropic.APIError) -> str:
    if isinstance(e, anthropic.RateLimitError):
        return "The AI service is busy; try again in a minute."
    return "The AI service isn't available right now."


def _result_event(step, block, payload, is_error, toolbox, began) -> dict:
    event = {
        "type": "tool_result",
        "step": step,
        "id": block.id,
        "name": block.name,
        "ok": not is_error,
        "ms": round((time.monotonic() - began) * 1000),
    }
    if is_error:
        return event | {"error": payload.get("error")}
    record = toolbox.queries.get(payload.get("query_id", ""))
    if record is not None:
        event |= {
            "query_id": record.query_id,
            "sql": record.sql,
            "params": record.params,
            "columns": record.columns,
            "rows": record.rows[:EVENT_ROWS],
            "row_count": record.row_count,
            "truncated": record.truncated or record.row_count > EVENT_ROWS,
        }
    elif "chart_id" in payload:
        event |= {"chart_id": payload["chart_id"]}
    return event


def _package(reply: dict, toolbox: tools.ToolBox, problems: list[str]) -> dict:
    """The answer plus what the UI needs to link each number to its query and draw the chart."""
    cited = set(reply.get("query_ids", [])) | {k["query_id"] for k in reply.get("key_numbers", [])}
    chart = toolbox.charts.get(reply.get("chart") or "")
    return {
        "answer": reply,
        "queries": {
            qid: record.to_json() | {"rows": record.rows[:100]}
            for qid, record in toolbox.queries.items()
            if qid in cited or (chart and chart["query_id"] == qid)
        },
        "chart": chart,
        "problems": problems,
    }


def _refusal() -> dict:
    return {
        "answer_type": "declined",
        "answer_markdown": "I can't help with that request. Ask me about MyLA311 service "
        "requests: how often they were closed, fixed or re-reported.",
        "key_numbers": [],
        "evidence_level": "none",
        "caveats": [],
        "query_ids": [],
        "chart": None,
        "follow_ups": [],
    }


def collect(events) -> dict:
    """Run an event stream to the end and keep what an eval or a cache needs."""
    result = {"events": [], "answer": None, "error": None}
    for event in events:
        result["events"].append(event)
        if event["type"] == "answer":
            result["answer"] = event
        elif event["type"] == "error":
            result["error"] = event
        elif event["type"] == "done":
            result["done"] = event
    return result

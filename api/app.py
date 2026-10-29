"""The Closed ≠ Fixed API: governed metrics for the dashboard, and the Ask agent over SSE.

    make serve      # uv run uvicorn api.app:app --reload, on http://127.0.0.1:8000/api/docs

Everything reads data/serving.duckdb through one locked, read-only connection (api/db.py).
Metric queries go through the same governed path as the agent (query_metric). /api/ask
streams the agent's events as server-sent events once the guards pass (api/guards.py): cached
answers first, then the kill switch, the per-IP rate limit and the daily spend cap.
"""

from __future__ import annotations

import functools
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from ai.agent import tools
from ai.agent.loop import Agent, BudgetExceeded, Settings
from api import db, guards, metrics, suggested, traces

ROOT = Path(__file__).resolve().parents[1]
FINDINGS = ROOT / "findings" / "findings.json"

load_dotenv()  # local development; hosts inject the environment

app = FastAPI(
    title="Closed ≠ Fixed API",
    description="Governed MyLA311 metrics and the Ask 311 agent.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)


@functools.cache
def guard() -> guards.Guards:
    store = guards.MemoryStore()
    return guards.Guards(store, guards.Policy.from_env(store))


@functools.cache
def agent() -> Agent:
    client = anthropic.Anthropic(max_retries=2, timeout=90.0)
    return Agent(client, db.shared(), Settings.from_env(), budget=guard())


@functools.cache
def data_end() -> str:
    value = db.shared().execute("select max(created_at) from fct_current_requests").fetchone()[0]
    return value.isoformat()


# --- data endpoints -------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    policy = guard().policy
    return {
        "ok": True,
        "data_end": data_end(),
        "model": Settings.from_env().model,
        "ask_enabled": policy.enabled,
        "ask_note": policy.disabled_reason or None,
    }


@app.get("/api/metrics")
def metric_catalog() -> dict:
    return {"metrics": metrics.describe(), "dimensions": tools.dimensions()}


class MetricRequest(BaseModel):
    metric: str
    filters: dict[str, list[str]] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    time_grain: Literal["none", "month", "quarter", "year"] = "none"
    date_range: list[str] = Field(default_factory=list, max_length=2)
    order: Literal["dimensions", "value_desc", "value_asc"] = "dimensions"
    limit: int = Field(0, ge=0, le=metrics.MAX_LIMIT)
    min_count: int = Field(0, ge=0)


@app.post("/api/metrics/query")
def metric_query(body: MetricRequest) -> dict:
    """One governed metric, with the SQL and parameters that produced it."""
    box = tools.ToolBox(db.shared())
    request = body.model_dump()
    request["filters"] = [{"dimension": d, "values": v} for d, v in body.filters.items()]
    payload, is_error = box.run("query_metric", request)
    if is_error:
        raise HTTPException(status_code=400, detail=payload["error"])
    return box.queries[payload["query_id"]].to_json()


@app.get("/api/findings")
def findings() -> dict:
    return json.loads(FINDINGS.read_text())


@app.get("/api/codes")
def codes() -> dict:
    """The reviewed resolution-code map, for the methodology page."""
    cur = db.shared().cursor()
    columns, rows, _ = db.execute(
        cur,
        "select resolution_code, closure_outcome, outcome_group, counts_as_fixed, label_source, "
        "rationale, n_service_cases, main_department, main_request_type, n_context_overrides "
        "from dim_resolution_code order by n_service_cases desc nulls last, resolution_code",
    )
    return {"codes": [dict(zip(columns, row, strict=True)) for row in rows]}


@app.get("/api/suggested")
def suggested_questions() -> dict:
    return {
        "questions": [
            {"question": q, "cached": suggested.cached(q, data_end()) is not None}
            for q in suggested.SUGGESTED
        ]
    }


# --- ask -----------------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)


@dataclass
class Gate:
    question: str
    ip_hash: str
    trace_id: str
    cached_events: list[dict] | None


def ask_gate(body: AskRequest, request: Request) -> Gate:
    """Everything that can refuse a question runs here, before the stream opens, so refusals
    are plain HTTP errors (503 off or over budget, 429 rate-limited)."""
    g = guard()
    peer = request.client.host if request.client else None
    gate = Gate(
        question=body.question,
        ip_hash=g.hash_ip(guards.client_ip(request.headers, peer)),
        trace_id=uuid.uuid4().hex[:12],
        cached_events=suggested.cached(body.question, data_end()),
    )
    if gate.cached_events is not None:
        return gate
    if not g.policy.enabled:
        raise HTTPException(status_code=503, detail=g.policy.disabled_reason)
    try:
        g.check()
    except BudgetExceeded as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    allowed, wait = g.take_question(gate.ip_hash)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"That's {g.policy.rate_limit_per_hour} questions this hour; try again later.",
            headers={"Retry-After": str(wait)},
        )
    return gate


@app.post("/api/ask", response_class=EventSourceResponse)
def ask(gate: Annotated[Gate, Depends(ask_gate)]) -> Iterator[ServerSentEvent]:
    """The agent's events as SSE: start, model_call, tool_call, tool_result, revision, answer,
    error and done, each with its type as the event name and the trace id."""
    events = iter(gate.cached_events) if gate.cached_events else agent().run(gate.question)
    seen = []
    try:
        for event in events:
            seen.append(event)
            yield ServerSentEvent(
                data=event | {"trace_id": gate.trace_id, "cached": bool(gate.cached_events)},
                event=event["type"],
            )
    finally:
        traces.write(
            {
                "trace_id": gate.trace_id,
                "ip_hash": gate.ip_hash,
                "question": gate.question,
                "cached": bool(gate.cached_events),
                **traces.summarize(seen),
            }
        )


class Feedback(BaseModel):
    trace_id: str = Field(min_length=6, max_length=40)
    rating: Literal["up", "down"]
    note: str = Field("", max_length=500)


@app.post("/api/feedback")
def feedback(body: Feedback, request: Request) -> dict:
    g = guard()
    peer = request.client.host if request.client else None
    ip_hash = g.hash_ip(guards.client_ip(request.headers, peer))
    if not g.take_feedback(ip_hash):
        raise HTTPException(status_code=429, detail="Too much feedback this hour.")
    traces.write({"ip_hash": ip_hash, **body.model_dump()}, kind="feedback")
    return {"ok": True}

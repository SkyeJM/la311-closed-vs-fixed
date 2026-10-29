"""Run the golden set against one model (spends API credit; needs the key in .env).

    make eval MODEL=claude-haiku-5-5
    uv run python -m evals.run --model claude-sonnet-5-5 --ids headline_gap,es_headline
    uv run python -m evals.run --model claude-opus-5-5 --limit 3 --max-usd 0.5   # a pilot

Writes evals/results/{date}_{model}.json (every answer, tool call, check and cost) and a
markdown summary next to it. The first question runs alone so the prompt cache is warm for the
rest, which run in parallel. --max-usd caps the agent's spend; the judge's cost is reported
separately.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import typer
from dotenv import load_dotenv

from ai.agent.loop import Agent, Budget, Settings, collect
from api import db
from evals import expected, judge, score

RESULTS = Path(__file__).with_name("results")
CHECKS = [
    "numeric",
    "governed_metric",
    "evidence",
    "answer_type",
    "numbers_supported",
    "rubric",
    "no_causal_claim",
    "language",
]

app = typer.Typer(add_completion=False)


def _rate(values: list) -> dict | None:
    applicable = [v for v in values if v is not None]
    if not applicable:
        return None
    return {
        "passed": sum(applicable),
        "of": len(applicable),
        "rate": sum(applicable) / len(applicable),
    }


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def summarize(rows: list[dict]) -> dict:
    latencies = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    costs = [r["cost_usd"] for r in rows]
    out = {
        "questions": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "pass_rate": sum(r["passed"] for r in rows) / len(rows) if rows else None,
        "checks": {name: _rate([r["checks"].get(name) for r in rows]) for name in CHECKS},
        "by_kind": {
            kind: _rate([r["passed"] for r in rows if r["kind"] == kind])
            for kind in ("numeric", "qualify", "decline")
        },
        "spanish": _rate([r["passed"] for r in rows if r["lang"] == "es"]),
        "latency_s": {
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "p50": round(_percentile(latencies, 0.5), 2) if latencies else None,
            "p90": round(_percentile(latencies, 0.9), 2) if latencies else None,
        },
        "cost_usd": {
            "total": round(sum(costs), 4),
            "per_question": round(sum(costs) / len(costs), 5) if costs else None,
            "judge_total": round(sum(r["judge_cost_usd"] for r in rows), 4),
        },
        "tokens": {
            name: sum((r.get("usage") or {}).get(name, 0) for r in rows)
            for name in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "output_tokens",
            )
        },
        "steps_mean": round(statistics.mean(r["steps"] or 0 for r in rows), 2) if rows else None,
        "revisions": sum(r["revisions"] or 0 for r in rows),
        "errors": sum(1 for r in rows if r["error"]),
    }
    numeric = out["checks"]["numeric"]
    out["numeric_accuracy"] = numeric["rate"] if numeric else None
    return out


def markdown(result: dict) -> str:
    s = result["summary"]

    def pct(block):
        return (
            "n/a" if not block else f"{block['rate'] * 100:.0f}% ({block['passed']}/{block['of']})"
        )

    overall = {"rate": s["pass_rate"] or 0, "passed": s["passed"], "of": s["questions"]}
    lines = [
        f"# Eval: {result['model']} (effort {result['effort']})",
        "",
        f"{result['date']} · commit {result['git_commit']} · data through {result['data_end'][:10]}"
        f" · judge {result['judge_model']}",
        "",
        "| measure | result |",
        "|---|---|",
        f"| **numeric accuracy** | **{pct(s['checks']['numeric'])}** |",
        f"| all checks passed | {pct(overall)} |",
    ]
    for name in CHECKS[1:]:
        lines.append(f"| {name.replace('_', ' ')} | {pct(s['checks'][name])} |")
    for kind, block in s["by_kind"].items():
        lines.append(f"| {kind} questions passed | {pct(block)} |")
    lines += [
        f"| Spanish questions passed | {pct(s['spanish'])} |",
        f"| latency mean / p50 / p90 | {s['latency_s']['mean']} / {s['latency_s']['p50']} / "
        f"{s['latency_s']['p90']} s |",
        f"| cost per question | ${s['cost_usd']['per_question']:.4f} |",
        f"| total cost (agent / judge) | ${s['cost_usd']['total']:.4f} / "
        f"${s['cost_usd']['judge_total']:.4f} |",
        f"| mean steps · revisions · errors | {s['steps_mean']} · {s['revisions']} · "
        f"{s['errors']} |",
        "",
        "## Questions",
        "",
        "| id | kind | passed | failed checks | latency | cost |",
        "|---|---|---|---|---|---|",
    ]
    for r in result["questions"]:
        failed = [k for k, v in r["checks"].items() if v is False]
        lines.append(
            f"| {r['id']} | {r['kind']} | {'yes' if r['passed'] else 'no'} | "
            f"{', '.join(failed) or ''} | {r['latency_s']} s | ${r['cost_usd']:.4f} |"
        )
    return "\n".join(lines) + "\n"


@app.command()
def main(
    model: str = typer.Option(..., help="claude-haiku-5-5, claude-sonnet-5-5 or claude-opus-5-5"),
    ids: str = typer.Option(None, help="Comma-separated question ids (default: all)."),
    limit: int = typer.Option(None, help="Only the first N questions (a pilot)."),
    workers: int = typer.Option(4, help="Questions in flight at once."),
    max_usd: float = typer.Option(5.0, help="Stop the agent when the run has spent this much."),
    effort: str = typer.Option("medium", help="The agent's effort level."),
    judge_model: str = typer.Option("claude-haiku-5-5", help="Grades caveats and language."),
    tag: str = typer.Option("", help="Suffix for the result file name."),
) -> None:
    load_dotenv()
    con = db.connect()
    golden = expected.load()
    questions = golden["questions"]
    if ids:
        wanted = set(ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    if limit:
        questions = questions[:limit]
    expect = expected.compute(con, questions)

    client = anthropic.Anthropic(max_retries=3, timeout=120.0)
    budget = Budget(max_usd)
    agent = Agent(client, con, Settings(model=model, effort=effort), budget)
    lock = threading.Lock()
    rows: dict[str, dict] = {}

    def run_one(q: dict) -> None:
        started = time.monotonic()
        result = collect(agent.run(q["question"]))
        rubric = [c.format(**expect[q["id"]]["context"]) for c in q.get("caveats", [])]
        verdict, judge_cost = None, 0.0
        if result["answer"] is not None:
            try:
                verdict, judge_cost = judge.grade(
                    client, judge_model, q["question"], result["answer"]["answer"], rubric
                )
            except anthropic.APIError as e:
                verdict = {"error": str(e)[:200]}
        scored = score.score(q, expect[q["id"]], result, verdict, golden["tolerance"])
        done = result.get("done", {})
        row = {
            "id": q["id"],
            "lang": q["lang"],
            "kind": q["kind"],
            "question": q["question"],
            "expected": expect[q["id"]],
            "rubric": rubric,
            "answer": result["answer"]["answer"] if result["answer"] else None,
            "problems": result["answer"]["problems"] if result["answer"] else None,
            "tool_calls": _tool_calls(result["events"]),
            "error": result["error"],
            "judge": verdict,
            "judge_cost_usd": judge_cost,
            "outcome": done.get("outcome"),
            "steps": done.get("steps"),
            "revisions": done.get("revisions"),
            "latency_s": done.get("latency_s"),
            "wall_s": round(time.monotonic() - started, 2),
            "cost_usd": done.get("cost_usd", 0.0),
            "usage": done.get("usage"),
            **scored,
        }
        with lock:
            rows[q["id"]] = row
            mark = (
                "pass"
                if row["passed"]
                else "FAIL " + ",".join(k for k, v in row["checks"].items() if v is False)
            )
            typer.echo(f"{q['id']:<36} {mark:<40} {row['latency_s']} s ${row['cost_usd']:.4f}")

    run_one(questions[0])  # alone: writes the prompt cache the others read
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run_one, questions[1:]))

    ordered = [rows[q["id"]] for q in questions]
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    data_end = con.execute("select max(created_at) from fct_current_requests").fetchone()[0]
    result = {
        "model": model,
        "effort": effort,
        "judge_model": judge_model,
        "date": date,
        "git_commit": _commit(),
        "data_end": data_end.isoformat(),
        "headline_window": list(expected.headline_window(con)),
        "summary": summarize(ordered),
        "questions": ordered,
    }
    RESULTS.mkdir(exist_ok=True)
    name = f"{date}_{model}{('_' + tag) if tag else ''}"
    (RESULTS / f"{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n"
    )
    (RESULTS / f"{name}.md").write_text(markdown(result))
    s = result["summary"]
    typer.echo(
        f"\n{model}: numeric accuracy {s['numeric_accuracy']}, all checks {s['pass_rate']:.2f}, "
        f"${s['cost_usd']['total']:.4f} + judge ${s['cost_usd']['judge_total']:.4f}, "
        f"mean {s['latency_s']['mean']} s -> evals/results/{name}.json"
    )


def _tool_calls(events: list[dict]) -> list[dict]:
    calls = {}
    for e in events:
        if e["type"] == "tool_call":
            calls[e["id"]] = {"name": e["name"], "input": e["input"]}
        elif e["type"] == "tool_result" and e["id"] in calls:
            calls[e["id"]] |= {
                k: e.get(k) for k in ("ok", "error", "query_id", "row_count", "sql", "ms")
            }
    return list(calls.values())


def _commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


if __name__ == "__main__":
    app()

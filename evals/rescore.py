"""Re-grade a saved eval run without asking the agent again (judge and scoring changes only).

    uv run python -m evals.rescore evals/results/2026-10-29_claude-sonnet-5-5.json

Expected numbers are recomputed from serving.duckdb and the rubric is read from the current
golden set, so a fix to the judge prompt or to a golden entry's scoring costs only the judge
calls (about $0.003 for 43 questions on Haiku), not a new agent run. The file is rewritten in
place with a `rescored_at` stamp; the answers in it are unchanged.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import typer
from dotenv import load_dotenv

from api import db
from evals import expected, judge, score
from evals.run import markdown, summarize

app = typer.Typer(add_completion=False)


@app.command()
def main(path: Path, judge_model: str = typer.Option(None, help="Default: the run's judge.")):
    load_dotenv()
    result = json.loads(path.read_text())
    golden = expected.load()
    by_id = {q["id"]: q for q in golden["questions"]}
    con = db.connect()
    expect = expected.compute(con, [by_id[r["id"]] for r in result["questions"]])
    client = anthropic.Anthropic(max_retries=3)
    model = judge_model or result["judge_model"]
    for row in result["questions"]:
        q = by_id[row["id"]]
        rubric = [c.format(**expect[q["id"]]["context"]) for c in q.get("caveats", [])]
        verdict, cost = None, 0.0
        if row["answer"] is not None:
            verdict, cost = judge.grade(client, model, q["question"], row["answer"], rubric)
        run = {
            "answer": None
            if row["answer"] is None
            else {"answer": row["answer"], "problems": row["problems"] or []},
            "events": [
                {"type": "tool_call", "id": str(i), "name": c["name"], "input": c["input"]}
                for i, c in enumerate(row["tool_calls"])
            ],
        }
        row |= {
            "expected": expect[q["id"]],
            "rubric": rubric,
            "judge": verdict,
            "judge_cost_usd": cost,
            **score.score(q, expect[q["id"]], run, verdict, golden["tolerance"]),
        }
    result |= {
        "judge_model": model,
        "rescored_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": summarize(result["questions"]),
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n")
    path.with_suffix(".md").write_text(markdown(result))
    s = result["summary"]
    typer.echo(f"{path.name}: numeric accuracy {s['numeric_accuracy']}, all {s['pass_rate']:.2f}")


if __name__ == "__main__":
    app()

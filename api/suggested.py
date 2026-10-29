"""Suggested questions for /ask, with cached answers so showing them costs nothing.

    uv run python -m api.suggested --model claude-sonnet-5-5   # spends API credit

The cache (api/suggested_answers.json, committed) keeps each answer's full event stream and the
data_end it was made from. When serving.duckdb is newer, the cache is stale: those questions
run live, under the guards, until `make suggested` rebuilds it.
"""

from __future__ import annotations

import argparse
import functools
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(__file__).with_name("suggested_answers.json")
SUGGESTED = [
    "How many requests marked closed were verified fixed?",
    "Which resolution codes make up most of the closed-but-not-fixed gap?",
    "How often are bulky item pickups closed because the item wasn't out?",
    "Did graffiti requests close faster or slower after the March 2025 relaunch?",
    "Which council districts have the biggest gap between closed and fixed?",
    "¿Qué porcentaje de las solicitudes cerradas se arreglaron de verdad?",
]


def normalize(question: str) -> str:
    return " ".join(question.lower().split()).strip(" ?¿!¡.")


@functools.cache
def load() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else {"answers": {}}


def cached(question: str, data_end: str) -> list[dict] | None:
    """The stored event stream for a suggested question, if it was made from this data."""
    cache = load()
    if cache.get("data_end") != data_end:
        return None
    return cache["answers"].get(normalize(question))


def build_cache(model: str, max_usd: float) -> None:
    """Run the agent on every suggested question and store the event streams."""
    import anthropic
    from dotenv import load_dotenv

    from ai.agent.loop import Agent, Budget, Settings, collect
    from api import db

    load_dotenv()
    con = db.connect()
    data_end = con.execute("select max(created_at) from fct_current_requests").fetchone()[0]
    budget = Budget(max_usd)
    agent = Agent(anthropic.Anthropic(), con, Settings.from_env(model=model), budget)
    answers, total = {}, 0.0
    for question in SUGGESTED:
        result = collect(agent.run(question))
        if result["answer"] is None or result["answer"]["problems"]:
            raise SystemExit(f"no clean answer for {question!r}: {result['error']}")
        answers[normalize(question)] = result["events"]
        total += result["done"]["cost_usd"]
        print(f"{question} -> {result['done']['outcome']} (${result['done']['cost_usd']:.4f})")
    CACHE.write_text(
        json.dumps(
            {
                "data_end": data_end.isoformat(),
                "model": model,
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "cost_usd": round(total, 4),
                "answers": answers,
            },
            ensure_ascii=False,
            indent=1,
            default=str,
        )
        + "\n"
    )
    print(f"{CACHE.relative_to(ROOT)}: {len(answers)} answers, ${total:.4f}")


if __name__ == "__main__":
    # argparse, not Typer: this module ships with the API, which carries no CLI dependencies.
    parser = argparse.ArgumentParser(description="Rebuild the cached suggested answers.")
    parser.add_argument("--model", default="claude-sonnet-5-5", help="the deployed default")
    parser.add_argument("--max-usd", type=float, default=1.0, help="stop past this spend")
    args = parser.parse_args()
    build_cache(args.model, args.max_usd)

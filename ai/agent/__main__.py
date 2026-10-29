"""Ask the agent one question from the terminal (spends API credit; needs the key in .env).

uv run python -m ai.agent "What share of closed requests were actually fixed?"
uv run python -m ai.agent "¿Cuántas solicitudes se cerraron?" --model claude-haiku-5-5 --trace
"""

from __future__ import annotations

import json

import anthropic
import typer
from dotenv import load_dotenv

from ai.agent.loop import Agent, Budget, Settings
from api import db

app = typer.Typer(add_completion=False)


@app.command()
def ask(
    question: str,
    model: str = typer.Option(None, help="Defaults to CLAUDE_MODEL, then claude-sonnet-5-5."),
    effort: str = typer.Option(None, help="low, medium or high (default medium)."),
    max_usd: float = typer.Option(0.5, help="Stop if this question would cost more."),
    trace: bool = typer.Option(False, help="Print every event, not just the answer."),
) -> None:
    load_dotenv()
    overrides = {k: v for k, v in {"model": model, "effort": effort}.items() if v}
    settings = Settings.from_env(**overrides)
    agent = Agent(anthropic.Anthropic(), db.connect(), settings, Budget(max_usd))
    for event in agent.run(question):
        kind = event["type"]
        if trace and kind in ("tool_call", "tool_result", "model_call", "revision"):
            shown = {k: v for k, v in event.items() if k not in ("rows", "sql")}
            typer.echo(f"· {json.dumps(shown, ensure_ascii=False, default=str)[:400]}")
        elif kind == "answer":
            reply = event["answer"]
            typer.echo(f"\n{reply['answer_markdown']}\n")
            for key in reply["key_numbers"]:
                typer.echo(f"  {key['label']}: {key['value']} {key['unit']} ({key['query_id']})")
            for caveat in reply["caveats"]:
                typer.echo(f"  caveat: {caveat}")
            typer.echo(f"  evidence: {reply['evidence_level']} · type: {reply['answer_type']}")
            if event["problems"]:
                typer.echo(f"  PROBLEMS: {event['problems']}")
        elif kind == "error":
            typer.echo(f"error ({event['code']}): {event['message']}")
        elif kind == "done":
            typer.echo(
                f"\n{event['outcome']} in {event['steps']} steps, {event['latency_s']} s, "
                f"${event['cost_usd']:.4f} ({settings.model}, effort {settings.effort})"
            )


if __name__ == "__main__":
    app()

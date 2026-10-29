"""Compare models: the latest full eval run per model -> evals/results/SUMMARY.md + summary.json.

    uv run python -m evals.report

A run counts as full when it covered the whole golden set; pilots and partial runs (--ids,
--limit) are left out. summary.json is what the methodology page shows.
"""

from __future__ import annotations

import json

from evals import expected
from evals.run import RESULTS

MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]


def latest_runs() -> dict[str, dict]:
    full = len(expected.load()["questions"])
    runs = {}
    for path in sorted(RESULTS.glob("*.json")):
        if path.name == "summary.json":
            continue
        result = json.loads(path.read_text())
        if result["summary"]["questions"] != full:
            continue
        result["file"] = path.name
        current = runs.get(result["model"])
        if current is None or (result["date"], path.stat().st_mtime) >= current["_key"]:
            runs[result["model"]] = result | {"_key": (result["date"], path.stat().st_mtime)}
    return runs


def _pct(block) -> str:
    return "n/a" if not block else f"{block['rate'] * 100:.0f}%"


def main() -> None:
    runs = latest_runs()
    order = [m for m in MODELS if m in runs] + sorted(set(runs) - set(MODELS))
    rows, table = [], []
    for model in order:
        r = runs[model]
        s = r["summary"]
        checks = s["checks"]
        rows.append(
            {
                "model": model,
                "effort": r["effort"],
                "date": r["date"],
                "file": r["file"],
                "questions": s["questions"],
                "numeric_accuracy": s["numeric_accuracy"],
                "pass_rate": s["pass_rate"],
                "checks": {k: (v["rate"] if v else None) for k, v in checks.items()},
                "by_kind": {k: (v["rate"] if v else None) for k, v in s["by_kind"].items()},
                "spanish": s["spanish"]["rate"] if s["spanish"] else None,
                "latency_s": s["latency_s"],
                "cost_per_question_usd": s["cost_usd"]["per_question"],
                "cost_total_usd": s["cost_usd"]["total"],
            }
        )
        table.append(
            f"| {model} | **{_pct(checks['numeric'])}** | {_pct({'rate': s['pass_rate']})} | "
            f"{_pct(checks['governed_metric'])} | {_pct(checks['evidence'])} | "
            f"{_pct(checks['rubric'])} | {_pct(s['by_kind']['decline'])} | "
            f"{_pct(s['spanish'])} | {_pct(checks['numbers_supported'])} | "
            f"{s['latency_s']['p50']} s / {s['latency_s']['p90']} s | "
            f"${s['cost_usd']['per_question']:.4f} |"
        )
    lines = [
        "# Ask 311 evals: accuracy, cost and latency by model",
        "",
        "Latest full run of the golden set (evals/golden.yaml) per model. Numeric accuracy is "
        "the share of numeric questions whose expected numbers all appear in the answer; "
        '"all checks" also needs the right metric, evidence level, answer type, required '
        "caveats, no causal claims, the question's language and no unsupported numbers.",
        "",
        "| model | numeric accuracy | all checks | governed metric | evidence level | caveats | "
        "declines | Spanish | numbers supported | latency p50 / p90 | cost per question |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *table,
        "",
        "Runs: " + ", ".join(f"`{runs[m]['file']}`" for m in order),
        "",
    ]
    (RESULTS / "SUMMARY.md").write_text("\n".join(lines))
    (RESULTS / "summary.json").write_text(json.dumps({"models": rows}, indent=1) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

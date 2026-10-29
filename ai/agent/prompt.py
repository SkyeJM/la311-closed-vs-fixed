"""The Ask agent's system prompt: ai/agent/prompts/system.md filled from the data it serves.

Definitions come from metrics.yml and the closure-outcome seed; dates and categories come from
serving.duckdb, so the prompt follows a data refresh. It holds no data counts or rates, so the
model can only quote numbers it got from a tool. The prompt is identical for every question on
a given serving file, which keeps it in the prompt cache.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from string import Template

import duckdb

from api import metrics
from findings.build import window_for

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = Path(__file__).with_name("prompts") / "system.md"
OUTCOMES = ROOT / "dbt" / "seeds" / "closure_outcomes.csv"
# Everything above this heading is definitions; numbers in it may be quoted.
RULES_HEADING = "## Rules for answering"


def _month(value) -> str:
    return date.fromisoformat(str(value)[:10]).strftime("%b %Y")


def _outcomes() -> str:
    with OUTCOMES.open() as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["sort_order"]))
    return "\n".join(
        f"| {r['closure_outcome']} | {r['outcome_group']} | {r['counts_as_fixed']} | "
        f"{r['description']} |"
        for r in rows
    )


def _metrics() -> str:
    return "\n".join(
        f"| {m['name']} | {m['unit']} | {m['evidence']} | {', '.join(m['eras'])} | "
        f"{m['description']} |"
        for m in metrics.describe()
    )


def build(con: duckdb.DuckDBPyConnection, max_steps: int) -> str:
    data_end = con.execute("select max(created_at) from fct_current_requests").fetchone()[0]
    headline = window_for(data_end.isoformat())
    periods = dict(
        (period, (first, last))
        for period, first, last in con.execute(
            "select period, min(first_month), max(last_month) from mart_cutover_periods "
            "group by period"
        ).fetchall()
    )
    crosswalk = con.execute(
        "select unified_category, any_value(cross_era_comparison) from dim_request_category "
        "where is_crosswalked group by 1 order by 1"
    ).fetchall()
    kinds = {
        "full": "all measures",
        "resident_reported_only": "resident-reported requests only",
        "volume_only": "volume only",
    }
    categories = con.execute(
        """
        select unified_category, arg_max(main_department, n_requests),
            bool_or(is_crosswalked), any_value(cross_era_comparison), sum(n_requests)
        from dim_request_category
        where era = 'current' and is_service_request
        group by 1
        order by 5 desc, 1
        """
    ).fetchall()
    lines = [
        f"- {name} ({dept}; "
        + (f"crosswalked, {kinds.get(kind, kind)})" if xw else "new system only)")
        for name, dept, xw, kind, _ in categories
    ]
    return Template(TEMPLATE.read_text()).substitute(
        data_end=data_end.strftime("%Y-%m-%d"),
        outcomes=_outcomes(),
        metrics=_metrics(),
        crosswalk="; ".join(f"{name} ({kinds.get(kind, kind)})" for name, kind in crosswalk),
        before=f"{_month(periods['before'][0])} to {_month(periods['before'][1])}",
        after=f"{_month(periods['after'][0])} to {_month(periods['after'][1])}",
        headline_from=headline[0],
        headline_to=headline[1],
        max_steps=max_steps,
        categories="\n".join(lines),
    )

"""Expected numbers for the golden set, computed from serving.duckdb when an eval runs.

The golden set stores how to compute each number (a governed metric request or SQL), never the
number, so it stays right after a data refresh. The default window ("headline") is the one the
agent's prompt and findings.json use: findings.build.window_for(data_end).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import yaml

from api import metrics
from findings.build import window_for

GOLDEN = Path(__file__).with_name("golden.yaml")


def load(path: Path = GOLDEN) -> dict:
    return yaml.safe_load(path.read_text())


def headline_window(con: duckdb.DuckDBPyConnection) -> tuple[str, str]:
    data_end = con.execute("select max(created_at) from fct_current_requests").fetchone()[0]
    return window_for(data_end.isoformat())


def _rate(row: dict, part: str) -> float | None:
    num, den = row.get(f"{part}_numerator"), row.get(f"{part}_denominator")
    return None if num is None or not den else num / den * 100


def number(con, item: dict, window: tuple[str, str]) -> tuple[float, dict]:
    """(expected value in the item's unit, captured context for the rubric)."""
    if "sql" in item:
        names = {"headline_from": window[0], "headline_to": window[1]}
        params = [names.get(p, p) for p in item.get("params", [])]
        return float(con.execute(item["sql"], params).fetchone()[0]), {}
    dates = item.get("window")
    query = metrics.compile_query(
        item["metric"],
        group_by=item.get("group_by", []),
        filters=item.get("filters", {}),
        date_range=window if dates == "headline" else tuple(dates) if dates else None,
    )
    rows = metrics.run(con, query)
    if "pick" in item:
        rows = [r for r in rows if all(r.get(k) == v for k, v in item["pick"].items())]
    if "exclude_null" in item:
        rows = [r for r in rows if r.get(item["exclude_null"]) is not None]
    if item.get("top") == "value_desc":
        rows = sorted(rows, key=lambda r: -(r["value"] if r["value"] is not None else -1e18))[:1]
    if len(rows) != 1:
        raise ValueError(f"expected one row for {item}, got {len(rows)}")
    row = rows[0]
    column = item.get("column", "value")
    if column in ("a_rate", "b_rate"):
        value = _rate(row, column[0])
    else:
        value = row[column]
        unit = metrics.catalog().metrics[item["metric"]]["unit"]
        if column == "value" and unit == "share" and item["unit"] == "percent":
            value = value * 100
    context = {name: row[col] for col, name in item.get("capture", {}).items()}
    return float(value), context


def compute(con, questions: list[dict]) -> dict[str, dict]:
    """question id -> {"numbers": [{"value", "unit"}], "context": {...}}"""
    window = headline_window(con)
    out = {}
    for q in questions:
        numbers, context = [], {}
        for item in q.get("expect", []):
            value, captured = number(con, item, window)
            numbers.append({"value": round(value, 6), "unit": item["unit"]})
            context |= captured
        out[q["id"]] = {"numbers": numbers, "context": context}
    return out

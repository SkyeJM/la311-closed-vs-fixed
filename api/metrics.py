"""Governed metrics: compile a metric request into SQL over the served marts (metrics.yml).

    from api import metrics
    query = metrics.compile_query(
        "verified_fix_rate", group_by=["unified_category"], filters={"department": "LASAN"}
    )
    rows = metrics.run(con, query)  # con: a connection to data/serving.duckdb

Callers name a metric and pass structured filters; they never write SQL. Dimensions are checked
against the source the compiler picks, and filter values are bound as parameters, so this is the
governed path the Phase 4 agent prefers over run_sql. Each query keeps its SQL, so every number
can show where it came from. Rates are computed from summed counts, never averaged.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import sqlglot
import yaml
from sqlglot import exp
from sqlglot.optimizer.simplify import simplify

ROOT = Path(__file__).resolve().parents[1]
METRICS_FILE = ROOT / "metrics.yml"
GRAINS = ["month", "quarter", "year"]


class MetricError(ValueError):
    """A request the catalog can't answer, with a message fit to show whoever asked."""


@dataclass(frozen=True)
class Source:
    name: str
    table: str
    dimensions: tuple[str, ...]
    measures: dict[str, str]
    constants: dict[str, object] = field(default_factory=dict)
    time_column: str | None = None
    time_grain: str | None = None
    precomputed_grain: tuple[str, ...] = ()
    precomputed_columns: dict[float, str] = field(default_factory=dict)
    percentile_column: str | None = None
    coverage: str = ""

    def columns(self) -> set[str]:
        """Columns a filter may reference."""
        extra = {self.time_column, self.percentile_column} - {None}
        return set(self.dimensions) | extra


@dataclass(frozen=True)
class Catalog:
    populations: dict[str, str]
    sources: dict[str, Source]
    metrics: dict[str, dict]


@dataclass(frozen=True)
class Query:
    metric: str
    source: str
    sql: str
    params: list
    group_by: list[str]
    coverage: str  # what the chosen source covers, for the answer's caveats


@functools.cache
def catalog(path: Path = METRICS_FILE) -> Catalog:
    raw = yaml.safe_load(path.read_text())
    sources = {}
    for name, s in raw["sources"].items():
        time = s.get("time") or {}
        pre = s.get("precomputed") or {}
        sources[name] = Source(
            name=name,
            table=s["table"],
            dimensions=tuple(s["dimensions"]),
            measures={k: str(v) for k, v in s["measures"].items()},
            constants=s.get("constants", {}),
            time_column=time.get("column"),
            time_grain=time.get("grain"),
            precomputed_grain=tuple(pre.get("grain", ())),
            precomputed_columns={float(q): c for q, c in pre.get("columns", {}).items()},
            percentile_column=s.get("percentile_column"),
            coverage=" ".join(s.get("coverage", "").split()),
        )
    return Catalog(raw["populations"], sources, raw["metrics"])


def describe() -> list[dict]:
    """The catalog as list_metrics shows it: definitions and the dimensions each metric accepts."""
    cat = catalog()
    out = []
    for name, spec in cat.metrics.items():
        dims = set()
        for source_name in spec["sources"]:
            source = cat.sources[source_name]
            dims |= set(source.dimensions) | set(source.constants)
        out.append(
            {
                "name": name,
                "label": spec["label"],
                "unit": spec["unit"],
                "evidence": spec["evidence"],
                "eras": spec["eras"],
                "description": " ".join(spec["description"].split()),
                "dimensions": sorted(dims - {"is_crosswalked"}),
                "time_grains": GRAINS,
            }
        )
    return out


# --- predicates ----------------------------------------------------------------------------


def _literal(value) -> exp.Expression:
    if isinstance(value, bool):
        return exp.true() if value else exp.false()
    if isinstance(value, int | float):
        return exp.Literal.number(value)
    return exp.Literal.string(str(value))


def _bind(predicate: str | None, source: Source) -> str | None:
    """The predicate with the source's constants filled in, "true" when there is none, or None
    when it needs a column the source doesn't have."""
    if not predicate:
        return "true"
    tree = sqlglot.parse_one(predicate, dialect="duckdb")
    tree = tree.transform(
        lambda node: (
            _literal(source.constants[node.name])
            if isinstance(node, exp.Column) and node.name in source.constants
            else node
        )
    )
    if {c.name for c in tree.find_all(exp.Column)} - source.columns():
        return None
    return tree.sql(dialect="duckdb")


def _implies(predicate: str | None, dim: str, value) -> bool:
    """Whether a population filter forces a boolean dimension to `value` (it turns false when
    the dimension takes the other value)."""
    if not predicate or not isinstance(value, bool):
        return False
    tree = sqlglot.parse_one(predicate, dialect="duckdb").transform(
        lambda node: (
            _literal(not value) if isinstance(node, exp.Column) and node.name == dim else node
        )
    )
    result = simplify(tree)
    return isinstance(result, exp.Boolean) and not result.this


def _and(*predicates: str) -> str:
    parts = [p for p in predicates if p and p != "true"]
    return " and ".join(f"({p})" for p in parts) or "true"


# --- source choice -------------------------------------------------------------------------


def _parts(spec: dict, cat: Catalog) -> list[dict]:
    """The ratio-like pieces a metric is built from, each with its own population."""
    if "difference" in spec:
        parts = []
        for ref in spec["difference"]:
            inner = cat.metrics[ref["metric"]]
            parts.append(inner | {"population": ref.get("population", inner.get("population"))})
        return parts
    return [spec]


def _measures(part: dict) -> list[str]:
    names = [part[k]["measure"] for k in ("numerator", "denominator") if k in part]
    return names + ([part["measure"]] if "measure" in part else [])


def _predicates(part: dict, cat: Catalog) -> list[str | None]:
    population = cat.populations.get(part.get("population"), part.get("population"))
    wheres = [part[k].get("where") for k in ("numerator", "denominator") if k in part]
    return [population, part.get("where"), *wheres]


def _unfit(
    source: Source,
    spec: dict,
    cat: Catalog,
    group_by: list[str],
    filters: dict,
    grain: str | None,
    date_range: tuple | None,
) -> str | None:
    """Why this source can't answer the request, or None if it can."""
    # A source holding one value of a dimension covers part of the population. It can answer
    # only when the request asks for that part, the metric exists only there, or the metric's
    # population implies it. Crosswalk-only marts say so in their coverage note instead.
    for dim, value in source.constants.items():
        populations = [_predicates(part, cat)[0] for part in _parts(spec, cat)]
        if not (
            dim in filters
            or dim == "is_crosswalked"
            or (dim == "era" and spec["eras"] == [value])
            or (populations and all(_implies(p, dim, value) for p in populations))
        ):
            return f"covers only {dim} = {value}"
    for dim in group_by:
        if dim not in source.dimensions and dim not in source.constants:
            return f"no dimension {dim}"
    for dim, value in filters.items():
        if dim in source.constants:
            values = value if isinstance(value, list) else [value]
            if any(v != source.constants[dim] for v in values):
                return f"holds only {dim} = {source.constants[dim]}"
        elif dim not in source.dimensions:
            return f"no dimension {dim}"
    if (grain or date_range) and not source.time_column:
        return "no time column"
    if grain and GRAINS.index(grain) < GRAINS.index(source.time_grain):
        return f"finest time grain is {source.time_grain}"
    if "percentile" in spec:
        if source.percentile_column:
            return (
                None
                if all(_bind(p, source) for p in _predicates(spec, cat))
                else ("lacks a column the definition needs")
            )
        if spec["percentile"] not in source.precomputed_columns:
            return "no precomputed percentile"
        for dim in source.precomputed_grain:
            single = dim in filters and not isinstance(filters[dim], list)
            timed = dim == source.time_column and grain == source.time_grain
            if dim not in group_by and not single and not timed:
                return f"percentiles are precomputed per {', '.join(source.precomputed_grain)}"
        return None
    for part in _parts(spec, cat):
        missing = [m for m in _measures(part) if m not in source.measures]
        if missing:
            return f"no measure {missing[0]}"
        if not all(_bind(p, source) for p in _predicates(part, cat)):
            return "lacks a column the definition needs"
    return None


# --- compile -------------------------------------------------------------------------------


def _measure_sql(source: Source, name: str) -> str:
    return source.measures[name].replace(
        "{data_end}", f"(select max(created_at) from {source.table})"
    )


def _summed(source: Source, measure: str, *conditions: str) -> str:
    # Null when no row matches, or when the measure isn't defined for the rows (volume-only
    # categories in the cutover marts): "no comparable data" rather than zero.
    return f"sum(case when {_and(*conditions)} then {_measure_sql(source, measure)} else 0 end)"


def _ratio_columns(part: dict, source: Source, cat: Catalog, prefix: str) -> list[str]:
    population = _bind(cat.populations.get(part.get("population"), part.get("population")), source)
    num, den = part["numerator"], part["denominator"]
    return [
        f"{_summed(source, num['measure'], population, _bind(num.get('where'), source))} "
        f"as {prefix}numerator",
        f"{_summed(source, den['measure'], population, _bind(den.get('where'), source))} "
        f"as {prefix}denominator",
    ]


def compile_query(
    metric: str,
    group_by: list[str] | tuple = (),
    filters: dict | None = None,
    time_grain: str | None = None,
    date_range: tuple[str, str] | None = None,
    source: str | None = None,
) -> Query:
    """SQL for one metric. filters: {dimension: value or [values]}; date_range: inclusive
    (from, to) dates on the source's time column; time_grain: month, quarter or year; source:
    one of the metric's sources, to skip the automatic choice."""
    cat = catalog()
    if metric not in cat.metrics:
        raise MetricError(f"unknown metric {metric}; list_metrics shows the catalog")
    spec = cat.metrics[metric]
    filters = dict(filters or {})
    group_by = list(group_by)
    if time_grain and time_grain not in GRAINS:
        raise MetricError(f"time_grain must be one of {GRAINS}")
    era_filter = filters.get("era")
    eras = era_filter if isinstance(era_filter, list) else [era_filter] if era_filter else []
    if any(era not in spec["eras"] for era in eras):
        raise MetricError(f"{metric} exists only for {', '.join(spec['eras'])} requests")
    if "share_of" in spec and spec["share_of"] not in group_by:
        group_by.append(spec["share_of"])

    if source and source not in spec["sources"]:
        raise MetricError(f"{metric} isn't defined on {source}")
    problems = []
    for name in [source] if source else spec["sources"]:
        chosen = cat.sources[name]
        problem = _unfit(chosen, spec, cat, group_by, filters, time_grain, date_range)
        if problem is None:
            break
        problems.append(f"{name}: {problem}")
    else:
        raise MetricError(f"{metric} can't be computed for this request ({'; '.join(problems)})")

    source = chosen
    dims = []
    if time_grain:
        dims.append(
            (f"cast(date_trunc('{time_grain}', {source.time_column}) as date)", "period_start")
        )
    for dim in group_by:
        if dim in source.constants:
            dims.append((_literal(source.constants[dim]).sql(dialect="duckdb"), dim))
        else:
            dims.append((f'"{dim}"', dim))

    where, params = [], []
    for dim, value in filters.items():
        if dim in source.constants:
            continue
        values = value if isinstance(value, list) else [value]
        where.append(f'"{dim}" in ({", ".join("?" for _ in values)})')
        params.extend(values)
    if date_range:
        where.append(f"{source.time_column} between ? and ?")
        params.extend(date_range)
    if "legacy" not in spec["eras"] and "era" in source.dimensions:
        where.append("era = 'current'")

    if "percentile" in spec and not source.percentile_column:
        inner = [f"max({source.precomputed_columns[spec['percentile']]}) as value"]
        outer = "value"
    elif "percentile" in spec:
        condition = _and(*(_bind(p, source) for p in _predicates(spec, cat)))
        inner = [
            f"percentile_cont({spec['percentile']}) within group "
            f"(order by case when {condition} then {source.percentile_column} end) as value",
            f"count(case when {condition} then 1 end) as n",
        ]
        outer = "value"
    elif "difference" in spec:
        first, second = _parts(spec, cat)
        inner = _ratio_columns(first, source, cat, "a_") + _ratio_columns(second, source, cat, "b_")
        outer = (
            "round((a_numerator / nullif(a_denominator, 0) "
            "- b_numerator / nullif(b_denominator, 0)) * 100, 4)"
        )
    elif "numerator" in spec:
        inner = _ratio_columns(spec, source, cat, "")
        outer = "numerator / nullif(denominator, 0)"
    else:
        population = _bind(
            cat.populations.get(spec.get("population"), spec.get("population")), source
        )
        inner = [
            f"{_summed(source, spec['measure'], population, _bind(spec.get('where'), source))} as n"
        ]
        if "share_of" in spec:
            others = [alias for _, alias in dims if alias != spec["share_of"]]
            partition = f"partition by {', '.join(others)}" if others else ""
            outer = f"n / nullif(sum(n) over ({partition}), 0)"
        else:
            outer = "n"

    select_dims = ",\n        ".join(f"{sql} as {alias}" for sql, alias in dims)
    aliases = [alias for _, alias in dims]
    sql = (
        "with grouped as (\n    select\n        "
        + ",\n        ".join(([select_dims] if dims else []) + inner)
        + f"\n    from {source.table}\n    where {_and(*where)}"
        + (f"\n    group by {', '.join(aliases)}" if aliases else "")
        + f"\n)\nselect *, {outer} as value_\nfrom grouped"
        + (f"\norder by {', '.join(aliases)}" if aliases else "")
    )
    return Query(metric, source.name, sql, params, aliases, source.coverage)


def run(con: duckdb.DuckDBPyConnection, query: Query) -> list[dict]:
    """Rows as dicts: the group-by columns, the inner counts, and `value`."""
    cursor = con.execute(query.sql, query.params)
    names = [d[0] for d in cursor.description]
    rows = []
    for row in cursor.fetchall():
        record = dict(zip(names, row, strict=True))
        record["value"] = record.pop("value_")
        rows.append(record)
    return rows

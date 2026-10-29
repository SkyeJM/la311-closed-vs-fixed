"""The Ask agent's tools: the definitions the model sees and the code that runs them.

Every tool that returns data gets a query_id (q1, q2 ...) and keeps its SQL, so each number in
an answer can link to the query behind it. query_metric is the governed path (metrics.yml via
api/metrics.py); run_sql is the escape hatch, limited to aggregate tables by
ai/agent/sqlguard.py; both run on the locked read-only connection from api/db.py with a row
cap and a time limit. Results go back to the model as JSON, rounded for reading; the trace keeps
the SQL and rows for the UI.
"""

from __future__ import annotations

import datetime as dt
import decimal
import difflib
import functools
import json
from dataclasses import dataclass, field

import duckdb

from ai.agent import charts, sqlguard
from api import db, metrics
from api.serving import TABLES

SQL_TABLES = sorted(t.name for t in TABLES if t.sql_tool)
MODEL_ROWS = 100  # rows the model sees from one query
KEEP_ROWS = 500  # rows the trace keeps (charts draw from these)
SHARE_UNITS = {"share"}


@dataclass
class QueryRecord:
    """One data-returning tool call, as the UI shows it and the number check reads it."""

    query_id: str
    tool: str
    sql: str
    params: list
    columns: list[str]
    rows: list[dict]
    row_count: int
    truncated: bool
    request: dict = field(default_factory=dict)
    metric: str | None = None
    unit: str | None = None
    evidence: str | None = None
    source: str | None = None
    coverage: str | None = None
    payload: dict = field(default_factory=dict)  # exactly what the model saw

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "payload"}


class ToolError(Exception):
    """A tool call that can't run; the message goes back to the model to act on."""


# --- values ---------------------------------------------------------------------------------


def clean(value):
    """JSON-safe values: dates as ISO strings, decimals as numbers, floats rounded."""
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        value = float(value)
    if isinstance(value, float):
        return round(value, 4)
    return value


def _records(columns: list[str], rows: list[tuple]) -> list[dict]:
    return [{c: clean(v) for c, v in zip(columns, row, strict=True)} for row in rows]


# --- definitions ------------------------------------------------------------------------------


@functools.cache
def dimensions() -> list[str]:
    cat = metrics.catalog()
    dims = set()
    for source in cat.sources.values():
        dims |= set(source.dimensions) | set(source.constants)
    return sorted(dims - {"is_crosswalked"})


@functools.cache
def definitions() -> list[dict]:
    """Tool definitions in a fixed order (they're part of the cached prompt prefix)."""
    metric_names = sorted(metrics.catalog().metrics)
    dims = dimensions()
    return [
        {
            "name": "query_metric",
            "description": (
                "Compute a governed metric from metrics.yml: the preferred way to get any rate, "
                "share, count or duration. You name the metric and pass structured filters and "
                "group-bys; the compiler picks the right served table, writes the SQL with bound "
                "parameters and returns rows with the counts behind each rate. Shares come back "
                "as `value` (0-1) and `value_pct` (0-100); differences in percentage points, "
                "with both component rates. Use date_range [first month, last month] as "
                "YYYY-MM-01 strings (inclusive), or [] for all months. Use order, limit and "
                "min_count to rank groups (min_count drops groups whose base is smaller, so "
                "rankings skip tiny groups). Errors explain what to change; an unknown filter "
                "value lists the closest valid ones."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": metric_names},
                    "filters": {
                        "type": "array",
                        "description": "Each item keeps rows whose dimension is one of values.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dimension": {"type": "string", "enum": dims},
                                "values": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "As strings: 'Graffiti', '7', 'true'.",
                                },
                            },
                            "required": ["dimension", "values"],
                            "additionalProperties": False,
                        },
                    },
                    "group_by": {"type": "array", "items": {"type": "string", "enum": dims}},
                    "time_grain": {
                        "type": "string",
                        "enum": ["none", "month", "quarter", "year"],
                        "description": "Adds a period_start column at this grain.",
                    },
                    "date_range": {
                        "type": "array",
                        "items": {"type": "string", "format": "date"},
                        "description": "[] or [first month, last month], e.g. "
                        "['2025-03-01', '2026-07-01'].",
                    },
                    "order": {"type": "string", "enum": ["dimensions", "value_desc", "value_asc"]},
                    "limit": {"type": "integer", "description": "0 for no limit."},
                    "min_count": {"type": "integer", "description": "0 for no minimum."},
                },
                "required": [
                    "metric",
                    "filters",
                    "group_by",
                    "time_grain",
                    "date_range",
                    "order",
                    "limit",
                    "min_count",
                ],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_metrics",
            "description": (
                "The full metric catalog from metrics.yml: each metric's definition, unit, "
                "evidence level, the eras it exists for and every dimension it can be filtered "
                "or grouped by. The system prompt already summarizes it; call this when you need "
                "a metric's exact dimensions or wording."
            ),
            "strict": True,
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "describe_table",
            "description": (
                "Columns of one aggregate table that run_sql can query: types, descriptions "
                "from the dbt docs, the values of short categorical columns and the range of "
                "numeric and date columns. Call it before writing run_sql against a table."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {"table": {"type": "string", "enum": SQL_TABLES}},
                "required": ["table"],
                "additionalProperties": False,
            },
        },
        {
            "name": "run_sql",
            "description": (
                "The escape hatch, for questions no metric fits (listing codes, a custom "
                "breakdown, a lookup in a dimension table). One DuckDB SELECT over the aggregate "
                "tables describe_table lists; no other statement types, table functions or "
                "row-level tables. Results are capped at 100 rows and 10 seconds, so aggregate "
                "in SQL. Never hand-write a rate that a metric defines: use query_metric. Store "
                "rates from counts with sums, never by averaging rates."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
                "additionalProperties": False,
            },
        },
        {
            "name": "explain_resolution_code",
            "description": (
                "How a resolution code is mapped: its closure outcome and whether it counts as "
                "fixed, who labeled it (AI accepted, AI overridden by a person, or a person) "
                "and why, how many service requests carry it, and its main department, request "
                "type and status. Takes the full code string ('QC-Item Not Out') or part of one; "
                "a partial string returns up to 5 matches."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            },
        },
        {
            "name": "make_chart",
            "description": (
                "Draw one query's rows as a Vega-Lite 6 chart in the answer. Pass the query_id "
                "and a spec without data: the rows of that query are attached for you, so don't "
                "include data, datasets or urls. Encode the query's own column names (for rates "
                "prefer value_pct with a title such as 'Percent'). The spec is validated against "
                "the Vega-Lite schema; on success you get a chart_id to put in the answer's "
                "chart field. Use a chart for trends and comparisons across several groups."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query_id": {"type": "string"},
                    "spec": {"type": "object", "description": "A Vega-Lite spec without data."},
                },
                "required": ["query_id", "spec"],
            },
        },
    ]


# --- the toolbox ---------------------------------------------------------------------------


_DISTINCT: dict[tuple[str, str, str], list] = {}


class ToolBox:
    """The tools for one question, over one cursor. Holds the queries and charts it made."""

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.cur = con.cursor()
        self.path = self.cur.execute(
            "select path from duckdb_databases() where database_name = current_database()"
        ).fetchone()[0]
        self.types = {
            (t, c): d
            for (t, c, d) in self.cur.execute(
                "select table_name, column_name, data_type from duckdb_columns() "
                "where database_name = current_database()"
            ).fetchall()
        }
        # A dimension has the same type in every table that holds it.
        self.dim_types = {}
        for (_, column), kind in sorted(self.types.items()):
            self.dim_types.setdefault(column, kind)
        self.queries: dict[str, QueryRecord] = {}
        self.charts: dict[str, dict] = {}
        self._done: dict[str, dict] = {}

    # Each handler returns the payload the model sees, or raises ToolError.
    def run(self, name: str, args: dict) -> tuple[dict, bool]:
        # A repeated identical call returns a pointer to the first result instead of running
        # again: in evals one model re-ran the same query six times until the step cap.
        key = name + json.dumps(args, sort_keys=True, default=str)
        if key in self._done:
            earlier = self._done[key].get("query_id")
            return {
                "duplicate_of": earlier,
                "note": "You already made this exact call"
                + (f" ({earlier})" if earlier else "")
                + "; its result is above. Use it, or answer now.",
            }, False
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"unknown tool {name}"}, True
        try:
            payload = handler(**args)
            self._done[key] = payload
            return payload, False
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}, True
        except (ToolError, metrics.MetricError, sqlguard.SqlRejected, charts.ChartRejected) as e:
            return {"error": str(e)}, True
        except db.QueryTimeout as e:
            return {"error": f"{e}; aggregate more or filter to fewer rows"}, True
        except duckdb.Error as e:
            return {"error": f"DuckDB: {str(e).splitlines()[0][:400]}"}, True

    def _next_id(self) -> str:
        return f"q{len(self.queries) + 1}"

    def _record(self, record: QueryRecord, payload: dict) -> dict:
        record.payload = payload
        self.queries[record.query_id] = record
        return payload

    def _execute(self, sql: str, params: list) -> tuple[list[str], list[dict], bool]:
        columns, rows, truncated = db.execute(self.cur, sql, params, max_rows=KEEP_ROWS)
        return columns, _records(columns, rows), truncated

    # query_metric ------------------------------------------------------------------------

    def _coerce(self, dim: str, values: list[str]) -> list:
        kind = self.dim_types.get(dim, "VARCHAR")
        out = []
        for v in values:
            text = str(v).strip()
            try:
                if kind == "BOOLEAN":
                    if text.lower() not in ("true", "false", "yes", "no", "1", "0"):
                        raise ValueError
                    out.append(text.lower() in ("true", "yes", "1"))
                elif kind in ("INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT"):
                    out.append(int(float(text)))
                elif kind == "DATE":
                    out.append(dt.date.fromisoformat(text))
                else:
                    out.append(text)
            except ValueError as e:
                raise ToolError(f"{dim} takes {kind.lower()} values, not '{text}'") from e
        return out

    def _known_values(self, table: str, dim: str) -> list:
        key = (self.path, table, dim)
        if key not in _DISTINCT:
            _DISTINCT[key] = [
                r[0]
                for r in self.cur.execute(
                    f'select distinct "{dim}" from {table} where "{dim}" is not null order by 1'
                ).fetchall()
            ]
        return _DISTINCT[key]

    def _check_values(self, table: str, dim: str, values: list) -> None:
        known = self._known_values(table, dim)
        missing = [v for v in values if v not in known]
        if not missing:
            return
        names = [str(k) for k in known]
        hints = []
        for value in missing:
            lowered = {n.lower(): n for n in names}
            close = [lowered[m] for m in difflib.get_close_matches(str(value).lower(), lowered)]
            close += [n for n in names if str(value).lower() in n.lower() and n not in close]
            hints.append(f"'{value}' (closest: {', '.join(close[:5]) or 'none'})")
        listing = f" Values: {', '.join(names)}." if len(names) <= 40 else ""
        raise ToolError(f"{dim} has no value {'; '.join(hints)}.{listing}")

    def _tool_query_metric(
        self,
        metric: str,
        filters: list[dict],
        group_by: list[str],
        time_grain: str,
        date_range: list[str],
        order: str = "dimensions",
        limit: int = 0,
        min_count: int = 0,
    ) -> dict:
        if date_range and len(date_range) != 2:
            raise ToolError("date_range takes [] or [first month, last month]")
        request = {
            "metric": metric,
            "filters": {f["dimension"]: list(f["values"]) for f in filters},
            "group_by": list(group_by),
            "time_grain": None if time_grain == "none" else time_grain,
            "date_range": tuple(date_range) if date_range else None,
            "order": order,
            "limit": limit or None,
            "min_count": min_count or None,
        }
        typed = {}
        for dim, values in request["filters"].items():
            if not values:
                raise ToolError(f"filter on {dim} has no values")
            values = self._coerce(dim, values)
            typed[dim] = values if len(values) > 1 else values[0]
        query = metrics.compile_query(**{**request, "filters": typed})
        source = metrics.catalog().sources[query.source]
        for dim, value in typed.items():
            if dim not in source.constants:
                self._check_values(source.table, dim, value if isinstance(value, list) else [value])
        columns, rows, truncated = self._execute(query.sql, query.params)
        for row in rows:
            row["value"] = row.pop("value_")
        columns = [("value" if c == "value_" else c) for c in columns]
        spec = metrics.catalog().metrics[metric]
        shown = [self._annotate(dict(r), spec) for r in rows[:MODEL_ROWS]]
        query_id = self._next_id()
        payload = {
            "query_id": query_id,
            "metric": metric,
            "label": spec["label"],
            "unit": spec["unit"],
            "evidence": spec["evidence"],
            "source_table": source.table,
            "applied": {
                "filters": request["filters"],
                "group_by": request["group_by"],
                "time_grain": request["time_grain"],
                "date_range": list(date_range),
                **({"era": "current only"} if "legacy" not in spec["eras"] else {}),
            },
            **({"coverage": query.coverage} if query.coverage else {}),
            "rows": shown,
            "row_count": len(rows),
            **({"truncated": True} if truncated or len(rows) > MODEL_ROWS else {}),
        }
        record = QueryRecord(
            query_id=query_id,
            tool="query_metric",
            sql=query.sql,
            params=[clean(p) for p in query.params],
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            request={**request, "date_range": list(date_range)},
            metric=metric,
            unit=spec["unit"],
            evidence=spec["evidence"],
            source=source.table,
            coverage=query.coverage or None,
        )
        return self._record(record, payload)

    @staticmethod
    def _annotate(row: dict, spec: dict) -> dict:
        """Readable extras computed from the row's own counts: percentages, component rates."""
        value = row.get("value")
        if spec["unit"] in SHARE_UNITS and isinstance(value, int | float):
            row["value_pct"] = round(value * 100, 2)
        if "difference" in spec:
            for part in ("a", "b"):
                num, den = row.get(f"{part}_numerator"), row.get(f"{part}_denominator")
                if num is not None and den:
                    row[f"{part}_rate_pct"] = round(num / den * 100, 2)
        if isinstance(value, float):
            row["value"] = round(value, 4)
        return row

    # list_metrics / describe_table ------------------------------------------------------

    def _tool_list_metrics(self) -> dict:
        return {"metrics": metrics.describe()}

    def _tool_describe_table(self, table: str) -> dict:
        if table not in SQL_TABLES:
            raise ToolError(f"run_sql can query only: {', '.join(SQL_TABLES)}")
        comment = self.cur.execute(
            "select comment from duckdb_tables() where database_name = current_database() "
            "and table_name = ?",
            [table],
        ).fetchone()[0]
        n_rows = self.cur.execute(f"select count(*) from {table}").fetchone()[0]
        columns = []
        for name, kind, text in self.cur.execute(
            "select column_name, data_type, comment from duckdb_columns() "
            "where database_name = current_database() and table_name = ? order by column_index",
            [table],
        ).fetchall():
            column = {"name": name, "type": kind}
            if text:
                column["description"] = " ".join(text.split())
            if kind == "VARCHAR":
                values = self.cur.execute(
                    f'select "{name}", count(*) from {table} where "{name}" is not null '
                    "group by 1 order by 2 desc, 1 limit 13"
                ).fetchall()
                shown = [v for v, _ in values[:12]]
                column["values" if len(values) <= 12 else "top_values"] = shown
            elif kind != "BOOLEAN":
                low, high = self.cur.execute(
                    f'select min("{name}"), max("{name}") from {table}'
                ).fetchone()
                column["range"] = [clean(low), clean(high)]
            columns.append(column)
        return {
            "table": table,
            "description": " ".join((comment or "").split()),
            "rows": n_rows,
            "columns": columns,
        }

    # run_sql ---------------------------------------------------------------------------------

    def _tool_run_sql(self, sql: str) -> dict:
        checked = sqlguard.check(sql, set(SQL_TABLES))
        columns, rows, truncated = self._execute(checked, [])
        query_id = self._next_id()
        payload = {
            "query_id": query_id,
            "columns": columns,
            "rows": rows[:MODEL_ROWS],
            "row_count": len(rows),
            **({"truncated": True} if truncated or len(rows) > MODEL_ROWS else {}),
        }
        record = QueryRecord(
            query_id=query_id,
            tool="run_sql",
            sql=checked,
            params=[],
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            request={"sql": sql},
        )
        return self._record(record, payload)

    # explain_resolution_code ------------------------------------------------------------------

    def _tool_explain_resolution_code(self, code: str) -> dict:
        fields = (
            "resolution_code, closure_outcome, outcome_group, counts_as_fixed, label_source, "
            "rationale, n_service_cases, main_department, main_request_type, main_status, "
            "n_context_overrides"
        )
        exact = f"select {fields} from dim_resolution_code where lower(resolution_code) = lower(?)"
        sql, params = exact, [code.strip()]
        columns, rows, _ = self._execute(sql, params)
        if not rows:
            sql = (
                f"select {fields} from dim_resolution_code "
                "where resolution_code ilike '%' || ? || '%' "
                "order by n_service_cases desc nulls last limit 5"
            )
            columns, rows, _ = self._execute(sql, params)
        if not rows:
            known = [
                r[0]
                for r in self.cur.execute(
                    "select resolution_code from dim_resolution_code"
                ).fetchall()
            ]
            close = difflib.get_close_matches(code, known, n=5, cutoff=0.4)
            raise ToolError(f"no resolution code like '{code}'. Closest: {', '.join(close)}")
        for row in rows:
            if row.get("n_context_overrides"):
                row["note"] = (
                    "This code maps differently for some departments or request types "
                    "(context overrides), so its class depends on where it was used."
                )
        query_id = self._next_id()
        payload = {"query_id": query_id, "codes": rows}
        record = QueryRecord(
            query_id=query_id,
            tool="explain_resolution_code",
            sql=sql,
            params=params,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=False,
            request={"code": code},
        )
        return self._record(record, payload)

    # make_chart --------------------------------------------------------------------------------

    def _tool_make_chart(self, query_id: str, spec: dict) -> dict:
        record = self.queries.get(query_id)
        if record is None:
            raise ToolError(f"no query {query_id}; make the query first")
        rows = [
            self._annotate(dict(r), metrics.catalog().metrics[record.metric])
            if record.metric
            else r
            for r in record.rows
        ]
        columns = list(rows[0]) if rows else record.columns
        full = charts.build(spec, columns, rows)
        chart_id = f"c{len(self.charts) + 1}"
        self.charts[chart_id] = {"query_id": query_id, "spec": full}
        return {"chart_id": chart_id, "rows_drawn": len(rows)}

    # for the answer check ------------------------------------------------------------------------

    def payloads(self) -> list[dict]:
        return [record.payload for record in self.queries.values()]

    def query_values(self) -> dict[str, dict]:
        """query_id -> the numbers its model-facing payload holds."""
        from ai.agent import numbers

        return {qid: {"values": numbers.pool(r.payload)} for qid, r in self.queries.items()}


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

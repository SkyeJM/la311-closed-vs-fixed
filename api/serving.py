"""Build data/serving.duckdb: the only data the deployed API ever sees.

The serving file holds aggregated marts plus a slim current-era fact table (brief section 5.1).
Nothing in it can locate a person: no addresses, no coordinates, no ZIP codes, no request IDs,
no crew fields (brief section 10). This module is the allowlist. Phase 4's `run_sql` tool may
query only the tables marked `sql_tool=True`; the slim fact table is reachable only through
governed metric queries.

    uv run python -m api.serving             # build from data/warehouse.duckdb, report sizes
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
SERVING = ROOT / "data" / "serving.duckdb"
# Vercel Hobby rejects function bundles over 225 MB, dependencies included (hosting spike).
SIZE_BUDGET_MB = 150


@dataclass(frozen=True)
class ServedTable:
    name: str
    select: str
    sql_tool: bool  # may the AI's run_sql tool query it? (aggregates only)


TABLES = [
    ServedTable(name, f"SELECT * FROM wh.marts.{name}", sql_tool=True)
    for name in [
        "dim_request_category",
        "dim_resolution_code",
        "dim_geography",
        "mart_outcomes_monthly",
        "mart_gap_by_district",
        "mart_cutover_comparison",
        "mart_bulky_items",
        "mart_contacts_info_only",
    ]
] + [
    ServedTable(
        "fct_current_requests",
        """
        SELECT
            created_at, closed_at, created_month, request_type, unified_category, department,
            channel, is_crew_self_report, status, is_terminal, status_outcome, resolution_code,
            closure_outcome, outcome_group, counts_as_fixed, hours_to_close, is_instant_close,
            is_rereport_eligible, is_rereported_30d, cd, nc_code
        FROM wh.marts.fct_service_requests
        WHERE era = 'current'
        ORDER BY created_at
        """,
        sql_tool=False,
    ),
]

# Columns that must never reach serving, checked on every build.
FORBIDDEN_COLUMNS = {
    "address",
    "lat",
    "lon",
    "zip",
    "request_id",
    "source_request_id",
    "assigned_to",
    "cd_member",
}


def sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def copy_comments(con: duckdb.DuckDBPyConnection, table: str, source: str) -> None:
    """Carry dbt's persisted docs (table and column comments) over to the served table."""
    comment = con.execute(
        "SELECT comment FROM duckdb_tables() WHERE database_name = 'wh' AND schema_name = 'marts' "
        "AND table_name = ?",
        [source],
    ).fetchone()
    if comment and comment[0]:
        con.execute(f"COMMENT ON TABLE {table} IS {sql_literal(comment[0])}")
    for column, text in con.execute(
        "SELECT column_name, comment FROM duckdb_columns() WHERE database_name = 'wh' "
        "AND schema_name = 'marts' AND table_name = ? AND comment <> ''",
        [source],
    ).fetchall():
        exists = con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE database_name = current_database() "
            "AND table_name = ? AND column_name = ?",
            [table, column],
        ).fetchone()[0]
        if exists:
            con.execute(f'COMMENT ON COLUMN {table}."{column}" IS {sql_literal(text)}')


def build(warehouse: Path = WAREHOUSE, dest: Path = SERVING) -> dict[str, int]:
    """Write the serving file atomically; returns row counts per table."""
    partial = dest.with_name(dest.name + ".tmp")
    partial.unlink(missing_ok=True)
    con = duckdb.connect(str(partial))
    con.execute("ATTACH ? AS wh (READ_ONLY)", [str(warehouse)])
    counts = {}
    for table in TABLES:
        con.execute(f"CREATE TABLE {table.name} AS {table.select}")
        source = "fct_service_requests" if table.name == "fct_current_requests" else table.name
        copy_comments(con, table.name, source)
        counts[table.name] = con.execute(f"SELECT count(*) FROM {table.name}").fetchone()[0]
    leaked = con.execute(
        "SELECT table_name, column_name FROM duckdb_columns() "
        "WHERE database_name = current_database() AND column_name IN "
        f"({', '.join('?' for _ in FORBIDDEN_COLUMNS)})",
        sorted(FORBIDDEN_COLUMNS),
    ).fetchall()
    if leaked:
        con.close()
        partial.unlink()
        raise ValueError(f"forbidden columns would reach serving: {leaked}")
    con.execute("DETACH wh")
    con.execute("CHECKPOINT")
    con.close()
    partial.replace(dest)
    return counts


def main() -> None:
    counts = build()
    size_mb = SERVING.stat().st_size / 1e6
    for name, rows in counts.items():
        print(f"  {name:28} {rows:>12,} rows")
    print(f"{SERVING.relative_to(ROOT)}: {size_mb:.1f} MB (budget {SIZE_BUDGET_MB} MB)")
    if size_mb > SIZE_BUDGET_MB:
        sys.exit("serving.duckdb is over budget: it would not fit Vercel's function limit")


if __name__ == "__main__":
    main()

"""Read-only, locked-down connections to data/serving.duckdb for the API and the agent.

The order matters (hosting spike, docs/DECISIONS.md): DuckDB 2.0 can't set `temp_directory`
once external access is off, so the file opens read-only with its temp directory and limits
first, then file access is switched off and the configuration locked. After that no query can
read or write files, attach databases, load extensions or raise the limits. This is the layer
under the `run_sql` parser (ai/agent/sqlguard.py), not a replacement for it.

    con = db.shared()              # one locked connection per process
    cur = con.cursor()             # one cursor per request or thread
    columns, rows, truncated = db.execute(cur, sql, params, max_rows=100)
"""

from __future__ import annotations

import functools
import os
import tempfile
import threading
from pathlib import Path

import duckdb

from api.serving import SERVING

TIMEOUT_S = 10.0
LOCKDOWN = [
    "SET enable_external_access = false",
    "SET autoinstall_known_extensions = false",
    "SET autoload_known_extensions = false",
    "SET lock_configuration = true",
]


class QueryTimeout(RuntimeError):
    """A query ran past its time limit and was interrupted."""


def connect(
    path: Path | str = SERVING, memory_limit: str = "1GB", threads: int = 2
) -> duckdb.DuckDBPyConnection:
    temp = Path(os.environ.get("DUCKDB_TEMP_DIR") or tempfile.gettempdir()) / "la311-duckdb"
    con = duckdb.connect(
        str(path),
        read_only=True,
        config={"temp_directory": str(temp), "memory_limit": memory_limit, "threads": threads},
    )
    for statement in LOCKDOWN:
        con.execute(statement)
    return con


@functools.cache
def shared() -> duckdb.DuckDBPyConnection:
    """The process-wide connection. Use .cursor() per request: cursors are thread-safe."""
    return connect(os.environ.get("SERVING_DB") or SERVING)


def execute(
    cur: duckdb.DuckDBPyConnection,
    sql: str,
    params: list | tuple = (),
    *,
    max_rows: int | None = None,
    timeout_s: float = TIMEOUT_S,
) -> tuple[list[str], list[tuple], bool]:
    """Run one query with a time limit. Returns (columns, rows, truncated)."""
    timer = threading.Timer(timeout_s, cur.interrupt)
    timer.start()
    try:
        result = cur.execute(sql, list(params))
        columns = [d[0] for d in result.description]
        rows = result.fetchmany(max_rows + 1) if max_rows else result.fetchall()
    except duckdb.InterruptException as e:
        raise QueryTimeout(f"the query ran past {timeout_s:g} s and was stopped") from e
    finally:
        timer.cancel()
    truncated = max_rows is not None and len(rows) > max_rows
    return columns, rows[:max_rows] if truncated else rows, truncated

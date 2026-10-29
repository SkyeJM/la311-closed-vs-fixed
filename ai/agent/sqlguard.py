"""The run_sql guard: one read-only SELECT over the allowlisted aggregate tables.

The agent's escape hatch is checked on sqlglot's parse tree, and what runs is sqlglot's own
rendering of the tree it checked, so a string the parser read one way can't run another way.
Underneath, the connection itself is read-only with file access off (api/db.py).

Rules:
- exactly one statement, and it must be a query (SELECT, possibly with WITH or UNION);
- no statement types that write, configure or reach outside (they can't nest in a query);
- every table is a plain name: an allowlisted table or a CTE defined in the same query. Table
  functions (read_csv, query, glob, range ...) and file paths are rejected, which also keeps the
  row-level fact table out: it is reachable only through governed metrics.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

MAX_SQL_CHARS = 4000
FORBIDDEN = tuple(
    getattr(exp, name)
    for name in [
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Create",
        "Drop",
        "Alter",
        "Command",
        "Copy",
        "Attach",
        "Detach",
        "Pragma",
        "Set",
        "Use",
        "Describe",
        "Summarize",
        "Transaction",
        "Commit",
        "Rollback",
        "Into",
    ]
    if hasattr(exp, name)
)


class SqlRejected(ValueError):
    """The SQL breaks a rule; the message says which, in words the model can act on."""


def check(sql: str, allowed_tables: set[str]) -> str:
    """Return the SQL to run (sqlglot's rendering of the checked query) or raise SqlRejected."""
    if len(sql) > MAX_SQL_CHARS:
        raise SqlRejected(f"the query is over {MAX_SQL_CHARS} characters; simplify it")
    try:
        statements = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SqlRejected(f"couldn't parse the SQL: {str(e).splitlines()[0]}") from e
    if len(statements) != 1:
        raise SqlRejected("send exactly one SELECT statement")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise SqlRejected("only SELECT queries are allowed")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN):
            raise SqlRejected(f"{node.key.upper()} isn't allowed; only SELECT queries run here")

    allowed = {t.lower() for t in allowed_tables}
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SqlRejected(
                "table functions aren't allowed; query the tables listed by describe_table"
            )
        name = table.name.lower()
        if table.catalog or table.db.lower() not in ("", "main"):
            raise SqlRejected(f"use the bare table name, not {table.sql(dialect='duckdb')}")
        if name not in allowed and name not in ctes:
            raise SqlRejected(
                f"table {table.name} isn't available to run_sql. Allowed tables: "
                f"{', '.join(sorted(allowed))}. Row-level requests are reachable only through "
                "query_metric."
            )
    return tree.sql(dialect="duckdb")

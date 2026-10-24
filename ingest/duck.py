"""DuckDB helpers shared by the sampler, pulls and the profile."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import duckdb


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_list(paths: Iterable[Path | str]) -> str:
    return "[" + ", ".join(sql_str(str(p)) for p in paths) + "]"


def system_column_name(name: str) -> str:
    """Socrata system fields such as ":updated_at" become "_socrata_updated_at"."""
    if not name.startswith(":"):
        return name
    return "_socrata_" + re.sub(r"[^0-9a-z_]+", "_", name[1:].lower()).strip("_")


def soda_csvs_to_parquet(
    csv_paths: list[Path],
    dest: Path,
    dataset_id: str,
    expected_fields: set[str],
    extra_columns: dict[str, str],
) -> int:
    """Combine row-API CSVs (API field names as headers) into one all-VARCHAR Parquet file.

    Rows repeated across pages or overlapping clusters are dropped (by Socrata row id). Fails if
    the data columns don't match the pinned fields. `extra_columns` maps a column name to a SQL
    expression, which may use `filename`. Returns the row count written.
    """
    con = duckdb.connect()
    source = f"read_csv({sql_list(csv_paths)}, header = true, all_varchar = true, filename = true)"
    columns = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    data_columns = {c for c in columns if not c.startswith(":") and c != "filename"}
    if data_columns != expected_fields:
        raise ValueError(
            f"{dataset_id}: CSV columns differ from the pinned schema. "
            f"Unexpected: {sorted(data_columns - expected_fields)}; "
            f"missing: {sorted(expected_fields - data_columns)}"
        )
    select = ", ".join(f'"{c}" AS "{system_column_name(c)}"' for c in columns if c != "filename")
    extras = "".join(f", {expr} AS {name}" for name, expr in extra_columns.items())
    dedupe = (
        'QUALIFY row_number() OVER (PARTITION BY ":id" ORDER BY filename) = 1'
        if ":id" in columns
        else ""
    )
    con.execute(
        f"COPY (SELECT {select}, {sql_str(dataset_id)} AS _dataset_id{extras} "
        f"FROM {source} {dedupe}) TO {sql_str(str(dest))} (FORMAT parquet, COMPRESSION zstd)"
    )
    return con.execute(f"SELECT count(*) FROM read_parquet({sql_str(str(dest))})").fetchone()[0]
